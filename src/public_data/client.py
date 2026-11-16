"""공식 명세 기반 공공데이터 HTTP 클라이언트와 비밀정보 없는 응답 처리."""
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, quote_plus, unquote, urlencode, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
import xml.etree.ElementTree as ET
from src.model import ROOT

MAX_RESPONSE_BYTES = 20_000_000
CREDENTIAL_NAME = "DATA_GO_KR_SERVICE_KEY"
PRIVATE_FIELD = re.compile(r"(service.?key|api.?key|authorization|password|token|ofcl|rprsntv|reprsnt|charger|contact|phone|telno|fax|email|mobile)", re.I)
DROP_FIELDS = {"corpList", "dminsttList", "dmndInsttList"}
FACILITY_FIELDS = {"bzentyId","bzentyNm","fcltTypeCd","fcltTypeNm","fcltSeCd","fcltSeNm","lctnCtpyCd","lctnCtpyNm","lctnSggCd","lctnSggNm"}
CONTRACT_FIELDS = {"untyCntrctNo","dcsnCntrctNo","cntrctRefNo","cntrctNm","cnstwkNm","cntrctInsttCd","cntrctInsttNm","cntrctCnclsDate","cntrctPrd","totCntrctAmt","thtmCntrctAmt","rgstDt","chgDt","dltDt","chgDivNm","wbgnDate","thtmScmpltDate","ttalScmpltDate","bsnsDivNm","lngtrmCtnuDivNm","cntrctInfoUrl","cntrctDtlInfoUrl"}

class PublicDataError(RuntimeError):
    pass
class MissingServiceKey(PublicDataError):
    pass
class ResponseSchemaError(PublicDataError):
    pass

def load_service_key(root=ROOT, name=CREDENTIAL_NAME):
    if name not in (CREDENTIAL_NAME,"JODAL"):
        raise ValueError("Unsupported public data credential variable.")
    raw = os.environ.get(name, "").strip()
    path = Path(root)/".env"
    if not raw and path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            entry_name, separator, value = line.partition("=")
            if separator and entry_name.strip() == name:
                raw = value.strip().strip('"').strip("'")
                break
    if not raw or raw in ("YOUR_KEY","발급받은키","여기에_발급받은_키"):
        raise MissingServiceKey(name+"가 없습니다. 공공데이터포털의 별도 서비스키를 .env에 설정하세요.")
    if raw.startswith(("http:","https:")) or any(c.isspace() for c in raw):
        raise MissingServiceKey("URL 대신 발급된 서비스키 값만 설정하세요.")
    return raw  # plus는 공백으로 바꾸지 않는다. 요청에서 정확히 한 번 인코딩한다.

def secret_variants(key):
    variants = {key, unquote(key), quote(key,safe=""), quote_plus(key)}
    variants.update(quote(v,safe="") for v in tuple(variants))
    return sorted((v for v in variants if v), key=len, reverse=True)

def redact_text(value, key):
    output = str(value)
    for secret in secret_variants(key):
        output = output.replace(secret, "[REDACTED]")
    return output

def safe_parameters(parameters):
    if any(PRIVATE_FIELD.search(str(k)) for k in parameters):
        raise PublicDataError("조회 설정에는 인증정보를 넣지 않습니다.")
    return dict(parameters)

def validate_endpoint(endpoint):
    parsed = urlsplit(endpoint)
    if parsed.scheme != "https" or parsed.hostname != "apis.data.go.kr" or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.port not in (None,443):
        raise PublicDataError("공식 apis.data.go.kr HTTPS 엔드포인트만 허용합니다.")
    if ".." in parsed.path.split("/"):
        raise PublicDataError("잘못된 API 경로입니다.")

class SameHostRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_endpoint(newurl.split("?",1)[0])
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def _xml_value(element):
    children = list(element)
    if not children:
        return (element.text or "").strip()
    result = {}
    for child in children:
        name = child.tag.split("}")[-1]
        value = _xml_value(child)
        if name in result:
            if not isinstance(result[name], list):
                result[name] = [result[name]]
            result[name].append(value)
        else:
            result[name] = value
    return result

def decode_payload(raw):
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ResponseSchemaError("응답이 최대 보존 크기를 초과했습니다.")
    text = raw.decode("utf-8-sig", errors="strict").strip()
    try:
        if text.startswith(("{","[")):
            value = json.loads(text)
            kind = "json"
        elif text.startswith("<"):
            if "<!doctype" in text.lower() or "<!entity" in text.lower():
                raise ResponseSchemaError("외부 엔티티를 포함한 XML은 처리하지 않습니다.")
            root = ET.fromstring(text)
            value = {root.tag.split("}")[-1]: _xml_value(root)}
            kind = "xml"
        else:
            raise ResponseSchemaError("JSON/XML API 응답이 아닙니다.")
    except (json.JSONDecodeError, ET.ParseError):
        raise ResponseSchemaError("공공데이터 응답을 해석하지 못했습니다.") from None
    if not isinstance(value, dict):
        raise ResponseSchemaError("API 응답 루트가 객체가 아닙니다.")
    return value, kind

def _integer(value, name):
    if isinstance(value,bool) or not re.fullmatch(r"\d+",str(value)):
        raise ResponseSchemaError(name+"가 0 이상의 정수가 아닙니다.")
    return int(value)

@dataclass
class Page:
    items: list
    total_count: int
    page_no: int
    page_size: int
    meta: dict = field(default_factory=dict)

def parse_page(raw, requested_page=1, requested_size=10, success_codes=("00",), no_data_codes=()):
    if any(isinstance(v,bool) or not isinstance(v,int) or v < 1 for v in (requested_page,requested_size)):
        raise ResponseSchemaError("Requested pagination must be positive integers.")
    try:
        payload, kind = decode_payload(raw)
    except UnicodeError:
        raise ResponseSchemaError("UTF-8 응답이 아닙니다.") from None
    gateway = payload.get("OpenAPI_ServiceResponse")
    if gateway is not None:
        raise PublicDataError("공공데이터 게이트웨이가 인증·접근을 거부했습니다. 키와 활용신청 상태를 확인하세요.")
    if "response" in payload:
        envelope = payload["response"]
        shape = "response"
    else:
        envelope = payload
        shape = "root"
    if not isinstance(envelope,dict) or not isinstance(envelope.get("header"),dict):
        raise ResponseSchemaError("명세의 header/body 응답 구조가 아닙니다.")
    header = envelope["header"]
    code = str(header.get("resultCode",""))
    if code in set(no_data_codes):
        return Page([],0,requested_page,requested_size,{"format":kind,"envelope":shape,"result_code":code,"explicit_no_data":True})
    if code not in set(success_codes):
        known = {"06":"조회 날짜 형식을 확인하세요.","07":"조회기간이 허용범위를 초과했습니다.","08":"필수 요청값을 확인하세요."}
        raise PublicDataError("공공데이터 서비스 오류: "+known.get(code,"인증·활용신청·요청 조건을 확인하세요."))
    body = envelope.get("body")
    if not isinstance(body,dict):
        raise ResponseSchemaError("명세의 body 객체가 없습니다.")
    if "totalCount" not in body:
        raise ResponseSchemaError("페이지 완결성을 검증할 totalCount가 없습니다.")
    total = _integer(body["totalCount"],"totalCount")
    page_no = _integer(body.get("pageNo",requested_page),"pageNo")
    size = _integer(body.get("numOfRows",requested_size),"numOfRows")
    if requested_page < 1 or requested_size < 1 or page_no != requested_page or size != requested_size:
        raise ResponseSchemaError("응답 페이지 번호·크기가 요청과 맞지 않습니다.")
    items = body.get("items")
    if isinstance(items,dict) and set(items) == {"item"}:
        items = items["item"]
    if items in (None,""):
        items = []
    elif isinstance(items,dict):
        items = [items]
    if not isinstance(items,list) or not all(isinstance(item,dict) for item in items):
        raise ResponseSchemaError("items/item이 관측 레코드 목록이 아닙니다.")
    if len(items) > size or len(items) > total or (total == 0 and items) or (total > 0 and (not items or (page_no-1)*size + len(items) > total)):
        raise ResponseSchemaError("관측 행수와 페이지 합계가 일치하지 않습니다.")
    return Page(items,total,page_no,size,{"format":kind,"envelope":shape,"result_code":code,
        "server_page_no":"pageNo" in body,"server_page_size":"numOfRows" in body})

def public_snapshot(page, dataset, key):
    """민감/미검토 필드를 제외한 응답 보존본. 원본 바이트 해시는 별도 기록한다."""
    allowed = FACILITY_FIELDS if dataset == "facilities" else CONTRACT_FIELDS
    removed = set()
    rows = []
    for item in page.items:
        row = {}
        for name,value in item.items():
            if name not in allowed or name in DROP_FIELDS or PRIVATE_FIELD.search(name):
                removed.add(name)
                continue
            if isinstance(value,(dict,list)):
                removed.add(name)
                continue
            row[name] = redact_text(value,key) if isinstance(value,str) else value
        rows.append(row)
    return {"schema":"privacy-redacted-api-snapshot-v1","items":rows,"totalCount":page.total_count,
            "pageNo":page.page_no,"numOfRows":page.page_size,"response_meta":page.meta,
            "excluded_fields":sorted(removed)}

class PublicDataClient:
    def __init__(self,service_key,*,timeout=20,retries=2,interval=.35,sleep=time.sleep,opener=None):
        if not service_key:
            raise MissingServiceKey("공공데이터포털 서비스키가 필요합니다.")
        if isinstance(retries,bool) or not isinstance(retries,int) or not 0 <= retries <= 5:
            raise ValueError("retries must be an integer from 0 to 5.")
        if isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not 0 < timeout <= 120:
            raise ValueError("timeout must be positive and at most 120 seconds.")
        if isinstance(interval,bool) or not isinstance(interval,(int,float)) or not 0 <= interval <= 60:
            raise ValueError("interval must be between 0 and 60 seconds.")
        self.key = unquote(service_key)
        self.timeout,self.retries,self.interval = timeout,retries,interval
        self.sleep = sleep
        self.opener = opener or build_opener(SameHostRedirect())
        self.last_request = None

    def fetch(self,endpoint,parameters,*,success_codes=("00",),no_data_codes=()):
        validate_endpoint(endpoint)
        clean = safe_parameters(parameters)
        for name in ("pageNo","numOfRows"):
            value = clean.get(name,1 if name=="pageNo" else 10)
            if isinstance(value,bool) or not isinstance(value,int) or value < 1:
                raise PublicDataError("Request pagination must be positive integers.")
        query = dict(clean,serviceKey=self.key)
        request = Request(endpoint+"?"+urlencode(query),headers={"User-Agent":"RecyclingPolicyLab/4.0","Accept":"application/json, application/xml"})
        raw = None
        for attempt in range(self.retries+1):
            if self.last_request is not None:
                self.sleep(max(0,self.interval-(time.monotonic()-self.last_request)))
            self.last_request = time.monotonic()
            try:
                with self.opener.open(request,timeout=self.timeout) as response:
                    raw = response.read(MAX_RESPONSE_BYTES+1)
                break
            except HTTPError as error:
                retry = error.code in (429,500,502,503,504)
                if retry and attempt < self.retries:
                    self.sleep(2**attempt)
                    continue
                raise PublicDataError("공공데이터 HTTP 오류 "+str(error.code)+"; 인증·신청·서비스 상태를 확인하세요.") from None
            except (URLError,TimeoutError,OSError):
                if attempt < self.retries:
                    self.sleep(2**attempt)
                    continue
                raise PublicDataError("공공데이터 서버에 연결하지 못했습니다.") from None
        page = parse_page(raw,int(clean.get("pageNo",1)),int(clean.get("numOfRows",10)),success_codes,no_data_codes)
        return page, raw
