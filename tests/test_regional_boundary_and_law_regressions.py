"""Regression checks for credential handling and revocation of audit claims."""
import json
from urllib.parse import urlsplit, parse_qs

import pandas as pd
import pytest

from src.regional_data import boundary_audit, law_client


def test_law_response_redacts_secret_suffix_in_embedded_text_and_url_queries(monkeypatch):
    # Starts with s, which the old over-escaped whitespace class excluded.
    oc = "secretUser_123"
    payload = {
        "text": f"retry OC={oc} status=temporary; next=allowed",
        "quoted_text": f'parameter OC="{oc}" is unavailable',
        "nested": [{"OC": oc}, {"note": f"request oc=alpha{oc}&target=ordin"}],
        "link": f"https://www.law.go.kr/DRF/lawService.do?OC={oc}&ID=123&target=ordin",
    }

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, size): return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr(law_client, "urlopen", lambda *args, **kwargs: Response())
    safe_raw, safe = law_client._fetch_json(law_client.LAW_SEARCH_ENDPOINT, {"target": "ordin"}, oc)
    assert oc not in safe_raw.decode("utf-8")
    assert safe["text"] == "retry OC=[REDACTED] status=temporary; next=allowed"
    assert safe["quoted_text"] == "parameter OC=[REDACTED] is unavailable"
    assert safe["nested"][0]["OC"] == "[REDACTED]"
    assert safe["nested"][1]["note"] == "request OC=[REDACTED]&target=ordin"
    query = parse_qs(urlsplit(safe["link"]).query)
    assert "OC" not in query and query["ID"] == ["123"]


def _detail(serial="10017", law_id="17", *, body=True):
    # Only field names documented by the official ordinInfoGuide are used.
    result = {"자치법규ID": law_id, "자치법규일련번호": serial, "자치법규명": "가상 재활용 조례"}
    if body:
        result["조내용"] = "제1조(목적) 이 조례는 가상 시험을 위한 예시다."
    return result


@pytest.mark.parametrize("payload,code", [
    ({"error": "사용자 정보 검증 실패"}, "LAW_API_AUTH_OR_SERVICE_ERROR"),
    (_detail(serial="999"), "LAW_API_DETAIL_IDENTITY_MISMATCH"),
    (_detail(law_id="99"), "LAW_API_DETAIL_IDENTITY_MISMATCH"),
    (_detail(body=False), "LAW_API_DETAIL_BODY_UNVERIFIED"),
    ({"조내용": "본문만 있고 요청한 법규의 신원이 확인되지 않음"}, "LAW_API_DETAIL_IDENTITY_MISSING"),
])
def test_law_details_require_requested_identity_and_documented_body(payload, code):
    with pytest.raises(ValueError, match=code):
        law_client._validate_detail(payload, {"ordinance_serial": "10017", "ordinance_id": "17"})


def test_error_detail_json_is_not_persisted_or_counted_as_collected_body(tmp_path, monkeypatch):
    monkeypatch.setattr(law_client, "load_law_oc", lambda root: "fixture_oc")
    monkeypatch.setattr(law_client, "load_law_domain", lambda root: "")
    records = [_detail(), _detail(serial="10018", law_id="18")]

    def fake_fetch(endpoint, params, oc, **kwargs):
        if endpoint == law_client.LAW_SEARCH_ENDPOINT:
            payload = records
        elif params.get("MST") == "10017":
            payload = _detail()
        else:
            payload = {"error": "사용자 정보 검증 실패"}
        return json.dumps(payload, ensure_ascii=False).encode("utf-8"), payload

    monkeypatch.setattr(law_client, "_fetch_json", fake_fetch)
    manifest = law_client.collect_ordinances(root=tmp_path, keywords=["재활용"], limit_pages=1,
                                             detail_budget=2, delay_seconds=0)
    assert manifest["candidate_count"] == 2
    assert manifest["detail_count"] == 1
    assert manifest["detail_rejected_count"] == 1
    assert manifest["status"] == "partial_detail_validation_failed"
    candidates = pd.read_csv(tmp_path / manifest["candidate_csv"], dtype=str).fillna("")
    good, rejected = candidates.iloc[0], candidates.iloc[1]
    assert good.detail_raw_file and "operational_policy_unverified" in good.detail_status
    assert rejected.detail_raw_file == ""
    assert rejected.detail_status == "LAW_API_AUTH_OR_SERVICE_ERROR"
    assert len(list((tmp_path / "data/raw/regional_2024/law_ordinances").glob("*/details/*.json"))) == 1
    assert all(row.candidate_status == "ordinance_history_only_operational_policy_unverified"
               for row in candidates.itertuples(index=False))


def _mock_successful_collection(monkeypatch):
    monkeypatch.setattr(law_client, "load_law_oc", lambda root: "fixture_oc")
    monkeypatch.setattr(law_client, "load_law_domain", lambda root: "")
    calls = []

    def fake_fetch(endpoint, params, oc, **kwargs):
        calls.append((endpoint, dict(params)))
        payload = [_detail()] if endpoint == law_client.LAW_SEARCH_ENDPOINT else _detail()
        return json.dumps(payload).encode("utf-8"), payload

    monkeypatch.setattr(law_client, "_fetch_json", fake_fetch)
    return calls


def test_list_only_cache_cannot_hide_later_requested_details(tmp_path, monkeypatch):
    calls = _mock_successful_collection(monkeypatch)
    first = law_client.collect_ordinances(root=tmp_path, keywords=["재활용"], limit_pages=1,
                                        detail_budget=0, delay_seconds=0)
    assert first["detail_count"] == 0 and len(calls) == 1
    second = law_client.collect_ordinances(root=tmp_path, keywords=["재활용"], limit_pages=1,
                                         detail_budget=1, delay_seconds=0)
    assert second["detail_count"] == 1 and len(calls) == 3
    reused = law_client.collect_ordinances(root=tmp_path, keywords=["재활용"], limit_pages=1,
                                         detail_budget=1, delay_seconds=0)
    assert reused == second and len(calls) == 3


@pytest.mark.parametrize("change", ["keywords", "page_budget", "failed_manifest", "modified_csv"])
def test_changed_or_failed_collection_scope_is_not_reused(tmp_path, monkeypatch, change):
    calls = _mock_successful_collection(monkeypatch)
    args = {"root": tmp_path, "keywords": ["재활용"], "limit_pages": 1,
            "detail_budget": 1, "delay_seconds": 0}
    first = law_client.collect_ordinances(**args)
    assert first["status"] == "complete_within_page_budget" and len(calls) == 2
    if change == "keywords":
        args["keywords"] = ["폐기물"]
    elif change == "page_budget":
        args["limit_pages"] = 2
    elif change == "failed_manifest":
        path = sorted((tmp_path / "data/raw/regional_2024/law_ordinances").glob("*/manifest.json"))[-1]
        failed = json.loads(path.read_text(encoding="utf-8"))
        failed["status"] = "partial_detail_validation_failed"
        path.write_text(json.dumps(failed), encoding="utf-8")
    else:
        path = tmp_path / first["candidate_csv"]
        path.write_bytes(path.read_bytes() + b"\n")
    refreshed = law_client.collect_ordinances(**args)
    assert refreshed["status"] == "complete_within_page_budget"
    assert len(calls) == 4


def test_review_required_refresh_revokes_previous_roster_success(tmp_path, monkeypatch):
    processed = tmp_path / "data/processed/regional_2024"
    processed.mkdir(parents=True)
    units = pd.DataFrame([
        {"sido_name": "서울", "sigungu_name": f"가상구{i:03d}", "sigungu_code": f"11{i:04d}0000"}
        for i in range(1, 230)
    ])
    waste_path = processed / "sigungu_2024_materials_verified.csv"
    units.to_csv(waste_path, index=False, encoding="utf-8-sig")
    preparation = processed / "manifest.json"
    preparation.write_text(json.dumps({"reference_year": 2024}), encoding="utf-8")
    monkeypatch.setattr(boundary_audit, "ROOT_CODES", ("11",))
    monkeypatch.setattr(boundary_audit, "load_mois_key", lambda root: "fixture_key")
    altered = {"enabled": False}

    def fake_fetch(key, params, *, timeout):
        rows = []
        for month in range(int(params["srchFrYm"][-2:]), int(params["srchToYm"][-2:]) + 1):
            for unit in units.to_dict("records"):
                name = unit["sigungu_name"]
                if altered["enabled"] and month == 7 and unit["sigungu_code"] == units.iloc[0].sigungu_code:
                    name = "가상구변경"
                rows.append({"admmCd": unit["sigungu_code"], "statsYm": f"2024{month:02d}",
                             "ctpvNm": "서울특별시", "sggNm": name})
        start = (params["pageNo"] - 1) * params["numOfRows"]
        payload = {"Response": {"head": {"resultCode": "0", "pageNo": params["pageNo"], "totalCount": len(rows)},
                                "items": {"item": rows[start:start + params["numOfRows"]]}}}
        return json.dumps(payload).encode("utf-8"), payload

    monkeypatch.setattr(boundary_audit, "_fetch_page", fake_fetch)
    first = boundary_audit.run_boundary_audit(root=tmp_path, delay_seconds=0)
    assert first["status"] == "complete"
    assert json.loads(preparation.read_text(encoding="utf-8"))["administrative_boundary_audit_status"] == "code_name_roster_stable"
    issues = pd.read_csv(processed / "boundary_audit_issues.csv")
    assert issues.empty and {"reference_month", "sigungu_code", "issue"}.issubset(issues.columns)

    altered["enabled"] = True
    refreshed = boundary_audit.run_boundary_audit(root=tmp_path, delay_seconds=0, refresh=True)
    assert refreshed["status"] == "review_required"
    assert refreshed["summary"]["monthly_name_mismatches"] == 1
    metadata = json.loads(preparation.read_text(encoding="utf-8"))
    assert metadata["administrative_boundary_audit_status"] == "review_required"
    assert metadata["metadata_code_snapshot"] == "current_bound_monthly_audit_not_verified"
    assert metadata["boundary_input_binding_verified"] is False
    assert metadata["policy_join_boundary_input_verified"] is False
    assert metadata["administrative_boundary_audit_geometry_assessed"] is False
    updated = pd.read_csv(waste_path)
    assert updated.compatibility_status.str.contains("review_required").all()
    assert not updated.compatibility_status.str.contains("roster_stable").any()
