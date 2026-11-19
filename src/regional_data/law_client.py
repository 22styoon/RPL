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
import unicodedata
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
            value = re.sub(r'''\bOC\s*=\s*(?:"[^"]*"|'[^']*'|[^&"'<>\s]*)''',
                           "OC=[REDACTED]", value, flags=re.IGNORECASE)
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
        "detail_status": "not_requested",
        "candidate_status": "ordinance_history_only_operational_policy_unverified",
        "retrieved_at": retrieved_at,
    }


def _validate_detail(payload, candidate):
    """Validate documented fields without assuming an undocumented JSON wrapper.

    Field names: open.law.go.kr/LSO/openApi/guideResult.do?htmlName=ordinInfoGuide.
    Matching legal identity and body text confirms a retrieved ordinance
    document, never implementation or exposure of an operational policy.
    """
    if not isinstance(payload, (dict, list)):
        raise ValueError("LAW_API_DETAIL_SCHEMA_CHANGED")
    nodes = [node for node in _walk(payload) if isinstance(node, dict)]
    if any(str(key).lower() in {"error", "errormsg", "errormessage"}
           and value not in (None, "", False, 0) for node in nodes for key, value in node.items()):
        raise ValueError("LAW_API_AUTH_OR_SERVICE_ERROR")
    identities = [node for node in nodes if _get(node, "name") and (_get(node, "serial") or _get(node, "id"))]
    if not identities:
        raise ValueError("LAW_API_DETAIL_IDENTITY_MISSING")
    expected_serial = str(candidate.get("ordinance_serial") or "").strip()
    expected_id = str(candidate.get("ordinance_id") or "").strip()
    matching = [node for node in identities
                if (not expected_serial or _get(node, "serial") == expected_serial)
                and (not expected_id or _get(node, "id") == expected_id)]
    if not matching:
        raise ValueError("LAW_API_DETAIL_IDENTITY_MISMATCH")
    if any(not _metadata_matches(node, candidate) for node in matching):
        raise ValueError("LAW_API_DETAIL_METADATA_MISMATCH")
    content_fields = {"조내용", "부칙내용", "개정문내용", "제개정이유내용"}
    if not any(key in content_fields and isinstance(value, str) and value.strip()
               for node in nodes for key, value in node.items()):
        raise ValueError("LAW_API_DETAIL_BODY_UNVERIFIED")


def _metadata_matches(record, candidate):
    """Reject explicit metadata disagreement; missing optional fields stay missing."""
    for field, column in (("name", "policy_name"), ("locality", "locality"),
                          ("promulgated", "promulgation_date"), ("effective", "effective_date")):
        expected = " ".join(str(candidate.get(column) or "").split())
        actual = " ".join(_get(record, field).split())
        if not expected or not actual:
            continue
        if field == "name":
            expected, actual = normalize_legal_title(expected), normalize_legal_title(actual)
        elif field in {"promulgated", "effective"}:
            expected, actual = _date_key(expected), _date_key(actual)
        if actual != expected:
            return False
    return True


def normalize_legal_title(value):
    """Compare title typography while preserving stored source strings.

    The list/body APIs use U+00B7 and U+318D for the same title separator.
    This narrow equivalence is for legal titles only, never locality matching.
    """
    text = unicodedata.normalize("NFC", str(value or "")).replace("ㆍ", "·")
    return " ".join(text.split())


def _date_key(value):
    if re.fullmatch(r"\d{8}", value):
        return value
    parts = re.fullmatch(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})\D*", value)
    return "".join((parts[1], parts[2].zfill(2), parts[3].zfill(2))) if parts else value


def _collection_path(root, value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("LAW_COLLECTION_SOURCE_PATH_INVALID")
    path = (root / value).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("LAW_COLLECTION_SOURCE_MISSING_OR_OUTSIDE_ROOT")
    return path


def validate_collection_evidence(root, manifest, candidate_csv=None):
    """Validate locally stored collection inputs without credentials or network.

    Successful and partial collections can supply legal document candidates.
    File hashes prove that these are the recorded inputs, not that a policy was
    implemented. ``candidate_csv`` may select a current CSV path inside root.
    Missing, changed, legacy, or contradictory evidence raises a safe code.
    """
    root = Path(root).resolve()
    try:
        if not isinstance(manifest, dict):
            raise ValueError("LAW_COLLECTION_MANIFEST_INVALID")
        csv_path = _collection_path(root, str(candidate_csv) if candidate_csv is not None
                                    else manifest.get("candidate_csv"))
        if (not re.fullmatch(r"[0-9a-f]{64}", str(manifest.get("candidate_sha256", "")))
                or hashlib.sha256(csv_path.read_bytes()).hexdigest() != manifest["candidate_sha256"]):
            raise ValueError("LAW_COLLECTION_CANDIDATE_CHANGED")
        candidates = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        required = {"ordinance_id", "ordinance_serial", "policy_name", "promulgation_date",
                    "effective_date", "locality", "raw_list_page", "detail_raw_file", "detail_status"}
        if not required.issubset(candidates.columns):
            raise ValueError("LAW_COLLECTION_CANDIDATE_SCHEMA_INVALID")
        if manifest.get("candidate_count") != len(candidates):
            raise ValueError("LAW_COLLECTION_COUNT_MISMATCH")
        requests = manifest.get("requests")
        if not isinstance(requests, list):
            raise ValueError("LAW_COLLECTION_REQUESTS_INVALID")
        sources, list_records, details = {}, {}, {}
        pages_count = rejected_count = 0
        for request in requests:
            if not isinstance(request, dict) or not isinstance(request.get("parameters"), dict):
                raise ValueError("LAW_COLLECTION_REQUESTS_INVALID")
            params = request["parameters"]
            if request.get("result") == "detail_rejected":
                if request.get("raw_file") or request.get("record_count") != 0:
                    raise ValueError("LAW_COLLECTION_REQUESTS_INVALID")
                rejected_count += 1
                continue
            source = request.get("raw_file")
            path = _collection_path(root, source)
            digest = request.get("sha256")
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("LAW_COLLECTION_SOURCE_HASH_INVALID")
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError("LAW_COLLECTION_SOURCE_CHANGED")
            if source in sources:
                raise ValueError("LAW_COLLECTION_DUPLICATE_SOURCE")
            payload = json.loads(raw.decode("utf-8-sig"))
            sources[source] = request
            if "query" in params:
                records = _extract_records(payload)
                if request.get("record_count") != len(records):
                    raise ValueError("LAW_COLLECTION_COUNT_MISMATCH")
                list_records[source] = records
                pages_count += 1
            elif params.get("MST") or params.get("ID"):
                if request.get("record_count") != 1:
                    raise ValueError("LAW_COLLECTION_COUNT_MISMATCH")
                details[source] = payload
            else:
                raise ValueError("LAW_COLLECTION_REQUESTS_INVALID")
        accepted = rejected_rows = 0
        seen_identities, used_details = set(), set()
        for candidate in candidates.to_dict("records"):
            serial, law_id = candidate["ordinance_serial"], candidate["ordinance_id"]
            identity = serial or law_id
            if not identity or identity in seen_identities:
                raise ValueError("LAW_COLLECTION_CANDIDATE_IDENTITY_INVALID")
            seen_identities.add(identity)
            page = candidate["raw_list_page"]
            records = list_records.get(page, [])
            if not any((not serial or _get(record, "serial") == serial)
                       and (not law_id or _get(record, "id") == law_id)
                       and _metadata_matches(record, candidate) for record in records):
                raise ValueError("LAW_COLLECTION_CANDIDATE_SOURCE_UNBOUND")
            detail = candidate["detail_raw_file"]
            if detail:
                if detail not in details or detail in used_details:
                    raise ValueError("LAW_COLLECTION_DETAIL_SOURCE_UNBOUND")
                if candidate["detail_status"] != "document_identity_and_body_validated_operational_policy_unverified":
                    raise ValueError("LAW_COLLECTION_DETAIL_STATUS_INVALID")
                params = sources[detail]["parameters"]
                if ((params.get("MST") and str(params["MST"]) != serial)
                        or (params.get("ID") and str(params["ID"]) != law_id)):
                    raise ValueError("LAW_COLLECTION_DETAIL_SOURCE_UNBOUND")
                _validate_detail(details[detail], candidate)
                used_details.add(detail)
                accepted += 1
            elif candidate["detail_status"].startswith("LAW_API_"):
                rejected_rows += 1
            elif candidate["detail_status"] != "not_requested":
                raise ValueError("LAW_COLLECTION_DETAIL_STATUS_INVALID")
        if (manifest.get("pages_used") != pages_count
                or manifest.get("detail_count") != accepted
                or manifest.get("detail_rejected_count", 0) != rejected_count
                or rejected_count != rejected_rows or len(details) != accepted):
            raise ValueError("LAW_COLLECTION_COUNT_MISMATCH")
    except (ValueError, TypeError, KeyError, AttributeError, OSError) as error:
        code = str(error)
        if not re.fullmatch(r"LAW_(?:COLLECTION|API)_[A-Z_]+", code):
            code = "LAW_COLLECTION_EVIDENCE_INVALID"
        raise ValueError(code) from None


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
    request_scope = {
        "target": "ordin", "history_mode": True, "search": 1, "display": 100,
        "keywords": list(terms), "effective_date_filter": DATE_RANGE,
        "page_budget": limit_pages, "detail_budget": detail_budget,
        "detail_validation_version": 1,
    }
    source_root = root / "data/raw/regional_2024/law_ordinances"
    prior = sorted(path for path in source_root.iterdir() if path.is_dir()) if source_root.exists() else []
    if prior and not refresh:
        cached_manifest = prior[-1] / "manifest.json"
        candidate_csv = root / "data/processed/regional_2024/policy_ordinance_candidates.csv"
        if cached_manifest.exists() and candidate_csv.exists():
            try:
                cached = json.loads(cached_manifest.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                cached = {}
            if not isinstance(cached, dict):
                cached = {}
            reusable = (cached.get("status") == "complete_within_page_budget"
                    and cached.get("request_scope") == request_scope
                    and cached.get("candidate_sha256") == hashlib.sha256(candidate_csv.read_bytes()).hexdigest())
            if reusable:
                try:
                    validate_collection_evidence(root, cached, candidate_csv=candidate_csv)
                except ValueError:
                    reusable = False
            if reusable:
                return cached
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
    details_rejected = 0
    for row in candidates[:detail_budget]:
        params = {"target": "ordin", "type": "JSON"}
        if row["ordinance_serial"]:
            params["MST"] = row["ordinance_serial"]
        else:
            params["ID"] = row["ordinance_id"]
        try:
            raw, payload = _fetch_json(LAW_SERVICE_ENDPOINT, params, oc, timeout=timeout, referer=referer)
            _validate_detail(payload, row)
        except ValueError as error:
            # Error JSON and unknown detail shapes are not ordinance evidence.
            # Preserve the list candidate but do not persist/count a detail body.
            row["detail_status"] = str(error)
            details_rejected += 1
            request_log.append({"parameters": params, "result": "detail_rejected",
                                "record_count": 0, "error_code": str(error),
                                "ordinance_serial": row["ordinance_serial"]})
            if delay_seconds:
                sleep(delay_seconds)
            continue
        detail_id = re.sub(r"[^A-Za-z0-9_-]", "_", row["ordinance_serial"] or row["ordinance_id"])
        path = details_dir / f"{detail_id}.json"
        path.write_bytes(raw)
        row["detail_raw_file"] = path.relative_to(root).as_posix()
        row["detail_status"] = "document_identity_and_body_validated_operational_policy_unverified"
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
               "raw_list_page", "detail_raw_file", "detail_status", "candidate_status", "retrieved_at"]
    pd.DataFrame(candidates, columns=columns).to_csv(candidate_path, index=False, encoding="utf-8-sig")
    manifest = {
        "source_id": "lawgo_ordinance_history",
        "source_url": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=ordinListGuide",
        "reference_year": 2024,
        "effective_date_filter": DATE_RANGE,
        "history_mode": True,
        "retrieved_at": retrieved_at,
        "status": ("partial_page_budget_reached" if stopped_by_budget
                   else "partial_detail_validation_failed" if details_rejected else "complete_within_page_budget"),
        "pages_used": pages_used,
        "detail_count": details_received,
        "detail_rejected_count": details_rejected,
        "detail_validation": "documented legal identity and body fields; operational policy remains unverified",
        "candidate_count": len(candidates),
        "candidate_csv": candidate_path.relative_to(root).as_posix(),
        "candidate_sha256": hashlib.sha256(candidate_path.read_bytes()).hexdigest(),
        "request_scope": request_scope,
        "limitation": "ordinance text is a legal source candidate; it does not establish implementation, coverage, operating method, or outcome",
        "credential_handling": "OC query parameter redacted from locally stored response JSON and source links",
        "requests": request_log,
    }
    dump(run_dir / "manifest.json", manifest)
    dump(source_root / "latest.json", manifest)
    return manifest
