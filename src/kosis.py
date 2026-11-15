"""KOSIS 공식 OpenAPI 수집. 인증키는 환경변수/.env에서만 읽는다."""
import json
import os
import re
import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError
import pandas as pd
import yaml
from src.model import ROOT

BASE = "https://kosis.kr/openapi/"
GUIDE = "https://kosis.kr/openapi/devGuide/devGuide_0201List.do"

class KosisError(RuntimeError):
    pass

def load_api_key(root=ROOT):
    key = os.environ.get("KOSIS_API_KEY", "").strip()
    env_path = Path(root) / ".env"
    if not key and env_path.exists():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            name, separator, value = line.partition("=")
            if separator and name.strip() == "KOSIS_API_KEY":
                key = value.strip().strip('"').strip("'")
                break
    if not key or key in ("발급받은키", "YOUR_KEY"):
        raise KosisError("KOSIS_API_KEY가 없습니다. 프로젝트 .env에 발급된 키를 설정하세요.")
    return key

def decode_response(raw):
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeError):
        raise KosisError("KOSIS가 JSON 대신 다른 응답을 반환했습니다.") from None
    if isinstance(payload, dict) and ("err" in payload or "errMsg" in payload):
        code = str(payload.get("err", ""))
        known = {
            "10":"인증키를 확인하세요.", "11":"인증키 상태·만료를 확인하세요.", "12":"인증키 상태·만료를 확인하세요.",
            "30":"선택한 분류·시점에 데이터가 없습니다.", "31":"4만 셀을 초과했습니다. 분류 또는 기간을 줄이세요.",
            "40":"호출 제한에 도달했습니다.", "41":"자료 수 제한에 도달했습니다.", "42":"키 또는 접속 제한을 확인하세요.",
            "50":"KOSIS 서버 오류입니다."
        }
        # 서버 메시지나 완성 URL을 그대로 노출하지 않는다.
        raise KosisError("KOSIS 요청 실패: " + known.get(code, "요청 조건과 서비스 상태를 확인하세요."))
    if not isinstance(payload, list) or not payload or not all(isinstance(r, dict) for r in payload):
        raise KosisError("KOSIS 응답이 비어 있거나 예상 표 형식이 아닙니다.")
    return payload

def request_api(endpoint, parameters, api_key):
    if endpoint not in ("Param/statisticsParameterData.do", "statisticsData.do", "statisticsSearch.do"):
        raise KosisError("허용되지 않은 KOSIS 경로입니다.")
    if any("key" in k.lower() for k in parameters):
        raise KosisError("인증키는 조회 설정에 넣지 않습니다.")
    query = dict(parameters, apiKey=api_key, format="json", jsonVD="Y")
    try:
        with urlopen(Request(BASE + endpoint + "?" + urlencode(query), headers={"User-Agent":"RecyclingPolicyLab/2.0"}), timeout=45) as response:
            raw = response.read()
    except (URLError, TimeoutError, OSError):
        raise KosisError("KOSIS에 연결하지 못했습니다. 네트워크와 인증 설정을 확인하세요.") from None
    if api_key.encode("utf-8") in raw:
        raise KosisError("인증정보가 응답에 포함되어 저장하지 않았습니다.")
    return decode_response(raw), raw

def load_tables():
    with (ROOT / "configs/kosis.yaml").open(encoding="utf-8-sig") as stream:
        return yaml.safe_load(stream)["tables"]

def validate_table(table):
    for field in ("org_id", "table_id"):
        if not re.fullmatch(r"[A-Za-z0-9_]+", str(table[field])):
            raise KosisError("기관·통계표 식별자 형식이 잘못되었습니다.")
    if not re.fullmatch(r"\d{4}", str(table["year"])):
        raise KosisError("현재 수집기는 연간 자료(YYYY)만 지원합니다.")
    allowed = {"itmId"} | {f"objL{i}" for i in range(1,9)}
    if not set(table["selection"]) <= allowed or not {"itmId", "objL1"} <= set(table["selection"]):
        raise KosisError("선택 설정에는 항목과 첫 분류가 필요하며 인증키는 넣을 수 없습니다.")

def parse_value(value):
    text = "" if value is None else str(value).strip()
    if text in ("", "-", "...", "…", "X", "x", "*", ".."):
        return None, "통계부호·결측"
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?", text.replace(",", "")):
        return None, "원표 해석 필요"
    return float(text.replace(",", "")), "수치"

def normalize_records(records, table, retrieved_at):
    output = []
    expected_org, expected_table = str(table["org_id"]), table["table_id"]
    for record in records:
        required = ("ORG_ID", "TBL_ID", "PRD_DE", "ITM_ID", "ITM_NM", "DT", "UNIT_NM")
        if any(key not in record for key in required):
            raise KosisError("필수 응답 필드가 없습니다. 원표 스키마를 확인하세요.")
        if str(record["ORG_ID"]) != expected_org or record["TBL_ID"] != expected_table or str(record["PRD_DE"]) != str(table["year"]):
            raise KosisError("응답의 기관·통계표·시점이 요청과 다릅니다.")
        value, status = parse_value(record["DT"])
        row = dict(value=value, reported_value=record["DT"], data_status=status,
                   item_id=record["ITM_ID"], item_name=record["ITM_NM"],
                   source_url="https://kosis.kr/statHtml/statHtml.do?" + urlencode({"orgId":expected_org,"tblId":expected_table}),
                   source_title=record.get("TBL_NM", table["name"]), retrieved_at=retrieved_at,
                   reference_year=str(record["PRD_DE"]), geography=table.get("geography", "지역은 원표 분류 확인"),
                   waste_scope=table["scope"], unit=record["UNIT_NM"], evidence_grade="A",
                   table_id=expected_table, last_changed=record.get("LST_CHN_DE", ""))
        for i in range(1,9):
            if f"C{i}" in record:
                row[f"class_{i}_id"] = record[f"C{i}"]
                row[f"class_{i}_name"] = record.get(f"C{i}_NM", "")
                row[f"class_{i}_type"] = record.get(f"C{i}_OBJ_NM", "")
        output.append(row)
    return pd.DataFrame(output)

def fetch_metadata(table, api_key, root=ROOT):
    validate_table(table)
    records, raw = request_api("statisticsData.do", dict(method="getMeta", type="ITM", orgId=table["org_id"], tblId=table["table_id"]), api_key)
    path = Path(root) / "data/raw/kosis"
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{table['table_id']}_metadata.json").write_bytes(raw)
    return records

def collect_table(table, api_key, root=ROOT):
    validate_table(table)
    parameters = dict(method="getList", orgId=table["org_id"], tblId=table["table_id"],
                      prdSe="Y", startPrdDe=str(table["year"]), endPrdDe=str(table["year"]), **table["selection"])
    records, raw = request_api("Param/statisticsParameterData.do", parameters, api_key)
    stamp = datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")
    frame = normalize_records(records, table, stamp)
    raw_dir, processed_dir = Path(root)/"data/raw/kosis", Path(root)/"data/processed/kosis"
    raw_dir.mkdir(parents=True, exist_ok=True); processed_dir.mkdir(parents=True, exist_ok=True)
    name = f"{table['table_id']}_{table['year']}"
    (raw_dir / f"{name}.json").write_bytes(raw)
    frame.to_csv(processed_dir / f"{name}.csv", index=False, encoding="utf-8-sig")
    manifest = dict(source="KOSIS OpenAPI", endpoint=BASE+"Param/statisticsParameterData.do",
                    parameters=parameters, retrieved_at=stamp, rows=len(frame),
                    sha256=hashlib.sha256(raw).hexdigest(), evidence_grade="A")
    (raw_dir / f"{name}_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return frame

def collect_all():
    key = load_api_key()
    return [collect_table(table, key) for table in load_tables()]

def display_table(frame):
    names = {"value":"수치", "reported_value":"원표 표기", "data_status":"수치 상태", "item_id":"항목 코드",
             "item_name":"항목", "source_url":"KOSIS 원표", "source_title":"통계표명", "retrieved_at":"수집일",
             "reference_year":"기준연도", "geography":"지역", "waste_scope":"대상 범위", "unit":"단위",
             "evidence_grade":"근거등급", "table_id":"통계표 식별자", "last_changed":"최종 수정일", "collection_method":"수집 경로"}
    for i in range(1,9):
        names.update({f"class_{i}_id":f"분류{i} 코드", f"class_{i}_name":f"분류{i} 값", f"class_{i}_type":f"분류{i} 종류"})
    return frame.rename(columns=names)
