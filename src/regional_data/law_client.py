"""법제처 자치법규 연혁을 안전하게 수집하는 보조 모듈.

수집 결과는 조례 후보 목록이며, 실제 정책 집행·대상 지역·성과를 입증하지 않는다.
"""
from datetime import datetime
from pathlib import Path
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
import hashlib
import json
import re
import pandas as pd
from zoneinfo import ZoneInfo

from src.model import ROOT
from .clients import dump, load_law_domain, load_law_oc

LAW_SEARCH_ENDPOINT = "https://www.law.go.kr/DRF/lawSearch.do"
LAW_SERVICE_ENDPOINT = "https://www.law.go.kr/DRF/lawService.do"
DEFAULT_KEYWORDS = ("재활용", "분리수거", "폐기물", "자원순환", "생활폐기물", "재활용가능자원")
DATE_RANGE = "20240101~20241231"
MAX_RESPONSE_BYTES = 5_000_000

FIELD_NAMES = {
    "serial": ("자치법규일련번호", "자치법규 일련번호", "일련번호", "MST", "mst"),
    "id": ("자치법규ID", "자치법규 ID", "ID", "id", "ordinId"),
    "name": ("자치법규명", "자치법규 명", "자치법규명칭", "ordinNm"),
    "promulgated": ("공포일자", "공포 일자", "ancYd"),
    "effective": ("시행일자", "시행 일자", "efYd"),
    "amendment": ("제개정구분명", "제·개정구분명", "rrClsNm"),
    "locality": ("지자체기관명", "지자체 기관명", "기관명", "orgNm"),
    "kind": ("자치법규종류", "자치법규 종류", "kndNm"),
    "detail_url": ("자치법규상세링크", "상세링크", "link"),
}
ROW_KEYS = {alias for aliases in FIELD_NAMES.values() for alias in aliases}
COUNT_KEYS = {"totalCnt", "totalCount", "검색건수", "전체검색건수", "총건수"}


def _stamp():
    return datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")


def _get(record, field):
    for key in FIELD_NAMES[field]:
        if key in record and record[key] is not None:
            return str(record[key]).strip()
    return ""


def _walk(value):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _extract_records(payload):
    candidates = []
    for node in _walk(payload):
        if isinstance(node, list) and node and all(isinstance(row, dict) for row in node):
            score = sum(bool(set(row) & ROW_KEYS) for row in node)
            if score:
                candidates.append((score, len(node), node))
    if candidates:
        return max(candidates, key=lambda item: (item[0], item[1]))[2]
    single_rows = []
    for node in _walk(payload):
        if isinstance(node, dict) and _get(node, "name") and (_get(node, "serial") or _get(node, "id")):
            single_rows.append(node)
    if single_rows:
        return single_rows
    total = None
    for node in _walk(payload):
        if isinstance(node, dict):
            for key in COUNT_KEYS & node.keys():
                try:
                    total = int(str(node[key]).replace(",", ""))
                except (TypeError, ValueError):
                    pass
    if total == 0:
        return []
    flattened = json.dumps(payload, ensure_ascii=False).lower()
    if any(term in flattened for term in ("사용자 정보 검증", "사용자정보 검증", "error", "오류", "실패")):
        raise ValueError("LAW_API_AUTH_OR_SERVICE_ERROR")
    raise ValueError("LAW_API_RECORD_SCHEMA_CHANGED")


def _fetch_json(endpoint, params, oc, *, timeout=30, referer=""):
    url = endpoint + "?" + urlencode(dict(params, OC=oc))
    headers = {"User-Agent": "RPL regional policy research/1.0"}
    if referer:
        if not re.fullmatch(r"(?:https?://)?[A-Za-z0-9.-]+(?::\d+)?(?:/[^\s]*)?", referer):
            raise ValueError("LAW_API_DOMAIN_INVALID")
        headers["Referer"] = referer if "://" in referer else "https://" + referer
    try:
        with urlopen(Request(url, headers=headers), timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as error:
        raise ValueError("LAW_API_HTTP_" + str(error.code)) from None
    except URLError:
        raise ValueError("LAW_API_NETWORK_ERROR") from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("LAW_API_RESPONSE_SIZE_LIMIT")
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("LAW_API_INVALID_JSON") from None
    # The official list response embeds OC in every detail link. Redact that
    # parameter before either persisting the JSON or normalizing source URLs.
    def redact(value):
        if isinstance(value, dict):
            return {key: ("[REDACTED]" if str(key).lower() == "oc" else redact(item))
                    for key, item in value.items()}
        if isinstance(value, list):
            return [redact(item) for item in value]
        if isinstance(value, str):
            parts = urlsplit(value)
            pairs = parse_qsl(parts.query, keep_blank_values=True)
            if any(key.lower() == "oc" for key, _ in pairs):
                pairs = [(key, item) for key, item in pairs if key.lower() != "oc"]
                value = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(pairs), parts.fragment))
            value = re.sub(r"\bOC=[^&\"'<>\\s]*", "OC=[REDACTED]", value, flags=re.IGNORECASE)
        return value
    payload = redact(payload)
    safe_raw = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    return safe_raw, payload


def _normalize_record(record, keyword, page_file, retrieved_at):
    serial = _get(record, "serial")
    law_id = _get(record, "id")
    name = _get(record, "name")
    if not (serial or law_id) or not name:
        return None
    locator = "MST=" + serial if serial else "ID=" + law_id
    detail_url = _get(record, "detail_url")
    if detail_url.startswith("/"):
        detail_url = "https://www.law.go.kr" + detail_url
    elif not detail_url.startswith("https://www.law.go.kr/"):
        detail_url = ("https://www.law.go.kr/DRF/lawService.do?target=ordin&" + locator + "&type=JSON")
    return {
        "ordinance_id": law_id,
        "ordinance_serial": serial,
        "policy_name": name,
        "promulgation_date": _get(record, "promulgated"),
        "effective_date": _get(record, "effective"),
        "amendment_type": _get(record, "amendment"),
        "locality": _get(record, "locality"),
        "ordinance_type": _get(record, "kind"),
        "searched_terms": keyword,
        "source_url": detail_url,
        "source_locator": locator,
        "raw_list_page": page_file,
        "detail_raw_file": "",
        "candidate_status": "ordinance_history_only_operational_policy_unverified",
        "retrieved_at": retrieved_at,
    }


def collect_ordinances(*, root=ROOT, keywords=DEFAULT_KEYWORDS, limit_pages=30, detail_budget=0,
                       timeout=30, delay_seconds=0.2, refresh=False):
    if limit_pages < 1 or detail_budget < 0:
        raise ValueError("페이지 예산은 1 이상, 본문 예산은 0 이상이어야 합니다.")
    terms = tuple(dict.fromkeys(term.strip() for term in keywords if term.strip()))
    if not terms:
        raise ValueError("검색어를 한 개 이상 지정하세요.")
    root = Path(root).resolve()
    oc = load_law_oc(root)
    referer = load_law_domain(root)
    source_root = root / "data/raw/regional_2024/law_ordinances"
    prior = sorted(path for path in source_root.iterdir() if path.is_dir()) if source_root.exists() else []
    if prior and not refresh:
        cached_manifest = prior[-1] / "manifest.json"
        candidate_csv = root / "data/processed/regional_2024/policy_ordinance_candidates.csv"
        if cached_manifest.exists() and candidate_csv.exists():
            return json.loads(cached_manifest.read_text(encoding="utf-8"))
    run_id = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%dT%H%M%S_%f")
    run_dir = source_root / run_id
    pages_dir, details_dir = run_dir / "pages", run_dir / "details"
    pages_dir.mkdir(parents=True, exist_ok=True)
    rows_by_id = {}
    request_log = []
    pages_used = 0
    retrieved_at = _stamp()
    stopped_by_budget = False

    for keyword in terms:
        page = 1
        while pages_used < limit_pages:
            params = {"target": "ordin", "type": "JSON", "nw": 2, "search": 1,
                      "query": keyword, "efYd": DATE_RANGE, "display": 100, "page": page}
            raw, payload = _fetch_json(LAW_SEARCH_ENDPOINT, params, oc, timeout=timeout, referer=referer)
            records = _extract_records(payload)
            path = pages_dir / f"{len(request_log)+1:04d}_{page}_{hashlib.sha256(keyword.encode()).hexdigest()[:8]}.json"
            path.write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest()
            relative_page = path.relative_to(root).as_posix()
            request_log.append({"parameters": params, "sha256": digest, "raw_file": relative_page,
                                "record_count": len(records), "keyword": keyword})
            pages_used += 1
            for record in records:
                normalized = _normalize_record(record, keyword, relative_page, retrieved_at)
                if normalized is None:
                    continue
                identity = normalized["ordinance_serial"] or normalized["ordinance_id"]
                old = rows_by_id.get(identity)
                if old:
                    old["searched_terms"] = ";".join(dict.fromkeys(old["searched_terms"].split(";") + [keyword]))
                else:
                    rows_by_id[identity] = normalized
            if len(records) < params["display"]:
                break
            page += 1
            if pages_used >= limit_pages:
                stopped_by_budget = True
                break
            if delay_seconds:
                sleep(delay_seconds)
        if pages_used >= limit_pages:
            if keyword != terms[-1] or len(records) == 100:
                stopped_by_budget = True
            break
        if delay_seconds:
            sleep(delay_seconds)

    candidates = list(rows_by_id.values())
    details_dir.mkdir(parents=True, exist_ok=True)
    details_received = 0
    for row in candidates[:detail_budget]:
        params = {"target": "ordin", "type": "JSON"}
        if row["ordinance_serial"]:
            params["MST"] = row["ordinance_serial"]
        else:
            params["ID"] = row["ordinance_id"]
        raw, payload = _fetch_json(LAW_SERVICE_ENDPOINT, params, oc, timeout=timeout, referer=referer)
        if not isinstance(payload, (dict, list)):
            raise ValueError("LAW_API_DETAIL_SCHEMA_CHANGED")
        detail_id = re.sub(r"[^A-Za-z0-9_-]", "_", row["ordinance_serial"] or row["ordinance_id"])
        path = details_dir / f"{detail_id}.json"
        path.write_bytes(raw)
        row["detail_raw_file"] = path.relative_to(root).as_posix()
        request_log.append({"parameters": params, "sha256": hashlib.sha256(raw).hexdigest(),
                            "raw_file": row["detail_raw_file"], "record_count": 1,
                            "ordinance_serial": row["ordinance_serial"]})
        details_received += 1
        if delay_seconds:
            sleep(delay_seconds)

    candidate_path = root / "data/processed/regional_2024/policy_ordinance_candidates.csv"
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    columns = ["ordinance_id", "ordinance_serial", "policy_name", "promulgation_date", "effective_date",
               "amendment_type", "locality", "ordinance_type", "searched_terms", "source_url", "source_locator",
               "raw_list_page", "detail_raw_file", "candidate_status", "retrieved_at"]
    pd.DataFrame(candidates, columns=columns).to_csv(candidate_path, index=False, encoding="utf-8-sig")
    manifest = {
        "source_id": "lawgo_ordinance_history",
        "source_url": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=ordinListGuide",
        "reference_year": 2024,
        "effective_date_filter": DATE_RANGE,
        "history_mode": True,
        "retrieved_at": retrieved_at,
        "status": "complete_within_page_budget" if not stopped_by_budget else "partial_page_budget_reached",
        "pages_used": pages_used,
        "detail_count": details_received,
        "candidate_count": len(candidates),
        "candidate_csv": candidate_path.relative_to(root).as_posix(),
        "limitation": "ordinance text is a legal source candidate; it does not establish implementation, coverage, operating method, or outcome",
        "credential_handling": "OC query parameter redacted from locally stored response JSON and source links",
        "requests": request_log,
    }
    dump(run_dir / "manifest.json", manifest)
    dump(source_root / "latest.json", manifest)
    return manifest
