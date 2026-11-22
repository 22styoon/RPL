"""인증키를 저장 URL·로그에 넣지 않는 지역 자료 수집기."""
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlsplit,urlencode,unquote
from urllib.error import HTTPError,URLError
import hashlib,json,os,time
from src.model import ROOT
from .registry import sources

MAX_BYTES=100_000_000
ROOT_CODES=["11","26","27","28","29","30","31","36","41","43","44","46","47","48","50","51","52"]
MOIS_ENDPOINT="https://apis.data.go.kr/1741000/admmPpltnHhStus/selectAdmmPpltnHhStus"

def stamp():
    return datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")

def dump(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+".tmp")
    temp.write_bytes((json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode("utf-8"));temp.replace(path)

def load_mois_key(root=ROOT):
    value=os.environ.get("MOIS_API_KEY","").strip()
    if not value:
        for line in (Path(root)/".env").read_text(encoding="utf-8-sig").splitlines() if (Path(root)/".env").exists() else []:
            name,sep,entry=line.partition("=")
            if sep and name.strip()=="MOIS_API_KEY":
                value=entry.strip().strip('"').strip("'");break
    if not value:
        raise ValueError("MOIS_API_KEY 미설정")
    return unquote(value)

def load_law_oc(root=ROOT):
    value=os.environ.get("LAW_OC","").strip()
    if not value:
        for line in (Path(root)/".env").read_text(encoding="utf-8-sig").splitlines() if (Path(root)/".env").exists() else []:
            name,sep,entry=line.partition("=")
            if sep and name.strip()=="LAW_OC":
                value=entry.strip().strip('"').strip("'");break
    if not value:
        raise ValueError("LAW_OC 미설정")
    return value

def load_law_domain(root=ROOT):
    value=os.environ.get("LAW_API_DOMAIN","").strip()
    if not value:
        for line in (Path(root)/".env").read_text(encoding="utf-8-sig").splitlines() if (Path(root)/".env").exists() else []:
            name,sep,entry=line.partition("=")
            if sep and name.strip()=="LAW_API_DOMAIN":
                value=entry.strip().strip('"').strip("'");break
    return value.rstrip("/")

def safe_url(url):
    parts=urlsplit(url)
    if parts.scheme!="https" or parts.hostname not in {"kwaste.or.kr","www.kwaste.or.kr","www.law.go.kr","law.go.kr","www.mois.go.kr","www.data.go.kr","apis.data.go.kr","kosis.kr"}:
        raise ValueError("등록된 공식 HTTPS 출처만 허용합니다.")
    if any(term in parts.query.lower() for term in ("servicekey=","apikey=","token=")):
        raise ValueError("인증 URL은 보존하지 않습니다.")

def fetch_bytes(url,*,timeout=30,attempt_budget=1):
    safe_url(url)
    for attempt in range(attempt_budget):
        try:
            with urlopen(Request(url,headers={"User-Agent":"RPL regional statistics/1.0"}),timeout=timeout) as response:
                raw=response.read(MAX_BYTES+1)
            if len(raw)>MAX_BYTES:
                raise ValueError("원본 파일 100MB 상한 초과")
            return raw
        except HTTPError as error:
            if error.code in (429,500,502,503,504) and attempt+1<attempt_budget:
                time.sleep(2**attempt)
                continue
            raise ValueError("HTTP_"+str(error.code)) from None
        except URLError:
            raise ValueError("network_error") from None

def collect_file(source,*,root=ROOT,year=2024,refresh=False,resume=False,timeout=30,page_budget=1,region=None):
    if year!=2024 or page_budget<1:
        raise ValueError("2024년과 양의 페이지 예산이 필요합니다.")
    spec=sources()[source]
    url=spec["resource_url"]
    safe_url(url)
    directory=Path(root)/"data/raw/regional_2024"/source
    previous=sorted(directory.glob("*/manifest.json"))
    if previous and not refresh:
        manifest=json.loads(previous[-1].read_text(encoding="utf-8"))
        file=Path(root)/manifest["raw_file"]
        if not file.exists() or hashlib.sha256(file.read_bytes()).hexdigest()!=manifest["sha256"]:
            raise ValueError("로컬 캐시 해시 불일치")
        return manifest
    run_id=datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%dT%H%M%S")
    run=directory/run_id
    manifest=dict(source_id=source,source_url=url,landing_url=spec["source_url"],
        resource_id=spec.get("resource_id"),reference_year=year,requested_region=region,
        request_parameters={},retrieved_at=stamp(),source_revision=spec.get("source_revision"),
        license=spec["license"],methods="official_file_download",completeness="failed",
        row_count=0,raw_file=None,sha256=None,code_version="regional_pipeline_1")
    try:
        probe=directory/"probe/official_2024.zip"
        raw=probe.read_bytes() if source=="kr_waste_2024_detail" and probe.exists() and not refresh else fetch_bytes(url,timeout=timeout,attempt_budget=page_budget)
        run.mkdir(parents=True,exist_ok=True)
        path=run/spec["filename"]
        path.write_bytes(raw)
        manifest.update(sha256=hashlib.sha256(raw).hexdigest(),raw_file=path.relative_to(root).as_posix(),
            response_type="ZIP" if raw.startswith(b"PK") else "HTML",completeness="archive_received" if raw.startswith(b"PK") else "metadata_only",
            bytes=len(raw))
    except ValueError as error:
        manifest["failure_reason"]=str(error)
    dump(run/"manifest.json",manifest)
    dump(directory/"latest.json",manifest)
    return manifest

def parse_mois(payload,*,page,year):
    response=payload.get("Response")
    if not isinstance(response,dict) or not isinstance(response.get("head"),dict):
        raise ValueError("MOIS_response_schema_changed")
    head=response["head"]
    if str(head.get("resultCode"))=="3":
        return [],0,"no_data"
    if str(head.get("resultCode"))!="0":
        raise ValueError("MOIS_service_error")
    if int(head["pageNo"])!=page:
        raise ValueError("MOIS_page_mismatch")
    rows=response.get("items",{})
    rows=rows.get("item",[]) if isinstance(rows,dict) else rows
    if isinstance(rows,dict):rows=[rows]
    if not isinstance(rows,list):
        raise ValueError("MOIS_items_schema_changed")
    if any(str(row.get("statsYm"))!=f"{year}12" for row in rows):
        raise ValueError("MOIS_reference_month_mismatch")
    return rows,int(head["totalCount"]),"success"

def collect_mois(*,root=ROOT,year=2024,page_budget=20,timeout=30,resume=False,refresh=False,region=None):
    if year!=2024 or page_budget<1:
        raise ValueError("2024년과 양의 페이지 예산이 필요합니다.")
    key=load_mois_key(root)
    directory=Path(root)/"data/raw/regional_2024/kr_admin_codes_2024"
    checkpoint=directory/"checkpoint.json"
    state=json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.exists() and not refresh else {"requests":[],"records":[],"completed_roots":[]}
    if not resume and not refresh and checkpoint.exists() and len(state["completed_roots"])==17:
        return state
    used=0
    roots=ROOT_CODES if region is None else [region]
    for code in roots:
        if resume and code in state["completed_roots"]:continue
        page=1;received=0;total=None;fingerprints=set()
        while used<page_budget:
            params=dict(admmCd=code+"00000000",srchFrYm="202412",srchToYm="202412",lv="2",regSeCd="1",type="JSON",numOfRows=100,pageNo=page)
            used+=1
            try:
                with urlopen(Request(MOIS_ENDPOINT+"?"+urlencode(dict(params,serviceKey=key))),timeout=timeout) as response:
                    raw=response.read(5_000_001)
                if len(raw)>5_000_000 or key.encode() in raw:
                    raise ValueError("MOIS_response_size_or_secret_echo")
                rows,current,status=parse_mois(json.loads(raw),page=page,year=year)
                digest=hashlib.sha256(raw).hexdigest()
                if digest in fingerprints or (total is not None and current!=total):
                    raise ValueError("MOIS_pagination_unstable")
                fingerprints.add(digest);total=current
                saved=directory/"pages"/f"{code}-{page}.json"
                saved.parent.mkdir(parents=True,exist_ok=True);saved.write_bytes(raw)
                state["requests"].append(dict(parameters=params,result=status,sha256=digest,raw_file=saved.relative_to(root).as_posix(),retrieved_at=stamp()))
                # Aggregate county fields only. No dong/tong/ban rows are requested.
                for row in rows:
                    state["records"].append({field:row.get(field) for field in ("admmCd","ctpvNm","sggNm","statsYm","totNmprCnt","hhCnt")})
                received+=len(rows)
                if received>=total:
                    state["completed_roots"].append(code);break
                if not rows:raise ValueError("MOIS_premature_empty_page")
                page+=1
            except (ValueError,HTTPError,URLError) as error:
                state["requests"].append(dict(parameters=params,result="failed",error_type=type(error).__name__,http_status=getattr(error,"code",None)))
                break
            finally:
                dump(checkpoint,state)
            time.sleep(.35)
        if used>=page_budget:break
    state.update(source_id="kr_admin_codes_2024",source_url="https://www.data.go.kr/data/15108065/openapi.do",
        endpoint=MOIS_ENDPOINT,reference_year=year,reference_month="202412",retrieved_at=stamp(),
        completeness="complete" if len(set(state["completed_roots"]))==17 else "partial",
        note="2024-12 말 행정기관 코드 스냅샷; 연중 경계 변경의 자동 검증과 구별")
    dump(checkpoint,state)
    return state
