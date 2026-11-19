"""Synthetic source documents test legal citations, never operational exposure."""
from copy import deepcopy
import json

import pandas as pd
import pytest

from src.regional_data import law_client, ordinance_evidence as evidence


def _record():
    return {"자치법규ID": "77", "자치법규일련번호": "7001",
            "자치법규명": "가상 자원순환 조례", "지자체기관명": "서울특별시 중구",
            "시행일자": "20240701", "공포일자": "20240620",
            "제개정구분명": "일부개정", "자치법규종류": "조례"}


def _payload():
    # '/' and '~' exercise RFC 6901 escaping in the emitted JSON pointer.
    return {"root/key~": {**_record(), "조문": [
        {"조문번호": ["1", "2"], "조제목": ["분리배출", "수거"],
         "조내용": "  제1조 종이류와 플라스틱은 분리배출한다.\n원문 공백을 보존한다.  "},
        {"조문번호": "3", "조제목": "폐지", "조내용": "제3조 이 조례의 종전 규정을 폐지한다."}],
        "부칙": {"부칙내용": "이 조례는 2024년 7월 1일부터 시행한다."}}}


def _candidate():
    return {"ordinance_id": "77", "ordinance_serial": "7001",
            "policy_name": "가상 자원순환 조례", "locality": "서울특별시 중구",
            "effective_date": "20240701", "promulgation_date": "20240620",
            "amendment_type": "일부개정", "detail_raw_file": "fixture/detail.json",
            "source_locator": "MST=7001", "source_url": "https://www.law.go.kr/자치법규/test"}


def _resolve_pointer(payload, pointer):
    node = payload
    for token in pointer.split("/")[1:]:
        token = token.replace("~1", "/").replace("~0", "~")
        node = node[int(token)] if isinstance(node, list) else node[token]
    return node


@pytest.fixture
def linked_sources(tmp_path, monkeypatch):
    """Use the real collector and provenance validator with synthetic responses."""
    monkeypatch.setattr(law_client, "load_law_oc", lambda root: "fixture_oc")
    monkeypatch.setattr(law_client, "load_law_domain", lambda root: "")

    def fake_fetch(endpoint, params, oc, **kwargs):
        payload = [_record()] if endpoint == law_client.LAW_SEARCH_ENDPOINT else _payload()
        return (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"), payload

    monkeypatch.setattr(law_client, "_fetch_json", fake_fetch)
    manifest = law_client.collect_ordinances(root=tmp_path, keywords=["재활용"], limit_pages=1,
                                            detail_budget=1, delay_seconds=0)
    law_client.validate_collection_evidence(tmp_path, manifest)
    directory = tmp_path / evidence.DIRECTORY
    codes = pd.DataFrame([{"sido_name": "서울", "sigungu_name": "중구", "sido_code": "11",
                           "sigungu_code": "1114000000", "code_reference_month": "202412",
                           "reference_year": 2024}])
    codes.to_csv(directory / "admin_codes_202412.csv", index=False, encoding="utf-8-sig")
    waste = pd.concat([codes.assign(material=material, generated_t=100, material_recycling_t=50)
                       for material in ("paper", "glass", "metal", "plastic")], ignore_index=True)
    waste.to_csv(directory / "sigungu_2024_materials_verified.csv", index=False, encoding="utf-8-sig")
    summary = evidence.link_ordinance_evidence(tmp_path)
    return {"root": tmp_path, "directory": directory, "manifest": manifest, "summary": summary}


def _assert_counts_suppressed(root):
    assessment = evidence.assess_ordinance_linkage(root)
    assert assessment["verified"] is False
    cached = {key: 9 for key in evidence.COUNT_FIELDS}
    fields = evidence.current_ordinance_fields(root, cached_summary=cached)
    assert fields["law_linkage_verified"] is False
    for key in evidence.COUNT_FIELDS:
        assert fields[key] == 0
        assert fields["cached_" + key] == 9
    return assessment


def test_article_text_and_json_pointer_identify_exact_returned_source():
    payload, candidate = _payload(), _candidate()
    before = deepcopy(payload)
    rows, status = evidence.extract_article_evidence(payload, candidate, raw_sha256="a" * 64)
    assert status == "version_metadata_matched"
    assert len(rows) == 3
    assert rows[0]["article_number"] == "1;2"
    assert rows[0]["article_title"] == "분리배출;수거"
    assert rows[0]["materials_mentioned"] == "paper;plastic"
    assert "~1" in rows[0]["json_pointer"] and "~0" in rows[0]["json_pointer"]
    for row in rows:
        assert _resolve_pointer(payload, row["json_pointer"]) == row["article_text"]
        assert row["raw_detail_sha256"] == "a" * 64
        assert row["source_locator"] == "MST=7001"
        assert row["raw_detail_file"] == candidate["detail_raw_file"]
    assert payload == before


def test_repeal_word_is_not_classified_as_paper_material():
    rows, _ = evidence.extract_article_evidence(_payload(), _candidate(), raw_sha256="b" * 64)
    repeal = next(row for row in rows if row["article_number"] == "3")
    assert "폐지" in repeal["article_text"]
    assert repeal["materials_mentioned"] == ""


def test_public_viewer_is_pinned_to_history_serial_without_api_credentials(linked_sources):
    directory = linked_sources["directory"]
    crosswalk = pd.read_csv(directory / "policy_ordinance_geography_crosswalk.csv", dtype=str)
    articles = pd.read_csv(directory / "policy_ordinance_article_evidence.csv", dtype=str)
    expected = "https://www.law.go.kr/LSW/ordinInfoP.do?ordinSeq=7001"
    assert crosswalk.source_url.eq(expected).all()
    assert articles.source_url.eq(expected).all()
    assert articles.api_source_url.eq(crosswalk.iloc[0].api_source_url).all()
    assert "DRF/lawService.do" in crosswalk.iloc[0].api_source_url
    assert "OC=" not in expected
    assert evidence.assess_ordinance_linkage(linked_sources["root"])["verified"]


@pytest.mark.parametrize("serial", ["", "../77", "77&OC=secret", "<script>"])
def test_invalid_serial_does_not_create_a_public_viewer_link(serial):
    assert evidence.public_ordinance_url(serial) == ""


@pytest.mark.parametrize("missing", ["locality", "effective_date", "promulgation_date", "policy_name"])
def test_incomplete_candidate_metadata_does_not_verify_a_legal_version(missing):
    candidate = _candidate()
    candidate[missing] = ""
    rows, status = evidence.extract_article_evidence(_payload(), candidate, raw_sha256="c" * 64)
    assert status != "version_metadata_matched"
    assert rows and all(row["legal_version_status"] == status for row in rows)


def test_id_only_detail_does_not_claim_a_specific_historical_version():
    candidate = _candidate()
    candidate["ordinance_serial"] = ""
    _, status = evidence.extract_article_evidence(_payload(), candidate, raw_sha256="d" * 64)
    assert status == "id_only_version_unresolved"


@pytest.mark.parametrize("date", ["20230101", "20240230", "2024-07-01"])
def test_invalid_or_out_of_scope_effective_start_does_not_verify_version(date):
    payload, candidate = _payload(), _candidate()
    payload["root/key~"]["시행일자"] = date
    candidate["effective_date"] = date
    _, status = evidence.extract_article_evidence(payload, candidate, raw_sha256="e" * 64)
    assert status != "version_metadata_matched"


def test_source_bound_linkage_exposes_legal_citations_without_policy_upgrading(linked_sources):
    root, summary = linked_sources["root"], linked_sources["summary"]
    assessment = evidence.assess_ordinance_linkage(root)
    assert assessment["verified"] is True
    fields = evidence.current_ordinance_fields(root)
    assert fields["law_linkage_verified"] is True
    assert fields["law_ordinance_version_candidates"] == 1
    assert fields["law_ordinance_detail_json_count"] == 1
    assert fields["law_verified_document_version_rows"] == 1
    assert fields["law_article_evidence_rows"] == 3
    assert fields["law_citation_regions"] == 1
    assert summary["operational_policy_verified_rows"] == summary["verified_outcome_join_rows"] == 0
    crosswalk = pd.read_csv(linked_sources["directory"] / "policy_ordinance_geography_crosswalk.csv")
    assert crosswalk.legal_effect_interval_status.eq("effective_start_only_end_and_transitions_unverified").all()
    raw = _payload()
    articles = pd.read_csv(linked_sources["directory"] / "policy_ordinance_article_evidence.csv", dtype=str).fillna("")
    for row in articles.to_dict("records"):
        assert _resolve_pointer(raw, row["json_pointer"]) == row["article_text"]


@pytest.mark.parametrize("artifact", ["raw_detail", "raw_list", "candidate", "crosswalk", "articles",
                                       "december", "waste", "source_manifest"])
def test_changed_source_or_linkage_artifact_invalidates_current_counts(linked_sources, artifact):
    root, directory, manifest = (linked_sources[key] for key in ("root", "directory", "manifest"))
    paths = {
        "raw_detail": root / next(request["raw_file"] for request in manifest["requests"]
                                  if request["parameters"].get("MST")),
        "raw_list": root / next(request["raw_file"] for request in manifest["requests"]
                                if request["parameters"].get("query")),
        "candidate": directory / "policy_ordinance_candidates.csv",
        "crosswalk": directory / "policy_ordinance_geography_crosswalk.csv",
        "articles": directory / "policy_ordinance_article_evidence.csv",
        "december": directory / "admin_codes_202412.csv",
        "waste": directory / "sigungu_2024_materials_verified.csv",
        "source_manifest": root / evidence.LATEST,
    }
    path = paths[artifact]
    if artifact in {"december", "waste"}:
        frame = pd.read_csv(path, dtype=str).fillna("")
        frame["sigungu_name"] = "이름변경구"
        frame.to_csv(path, index=False, encoding="utf-8-sig")
    else:
        path.write_bytes(path.read_bytes() + b"\n")
    _assert_counts_suppressed(root)


def test_row_order_material_outcome_and_population_changes_preserve_logical_geography(linked_sources):
    directory = linked_sources["directory"]
    waste_path = directory / "sigungu_2024_materials_verified.csv"
    waste = pd.read_csv(waste_path, dtype=str).iloc[::-1].copy()
    waste["generated_t"] = 999
    waste["material_recycling_t"] = 1
    waste.to_csv(waste_path, index=False, encoding="utf-8-sig")
    codes_path = directory / "admin_codes_202412.csv"
    codes = pd.read_csv(codes_path, dtype=str)
    codes["population"] = 12345
    codes.to_csv(codes_path, index=False, encoding="utf-8-sig")
    assert evidence.assess_ordinance_linkage(linked_sources["root"])["verified"] is True
    assert evidence.current_ordinance_fields(linked_sources["root"])["law_article_evidence_rows"] == 3


@pytest.mark.parametrize("filename", ["admin_codes_202412.csv", "sigungu_2024_materials_verified.csv"])
def test_wrong_code_month_is_not_hidden_by_identical_logical_roster(linked_sources, filename):
    path = linked_sources["directory"] / filename
    frame = pd.read_csv(path, dtype=str)
    frame["code_reference_month"] = "202501"
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    _assert_counts_suppressed(linked_sources["root"])


@pytest.mark.parametrize("filename", ["policy_ordinance_geography_crosswalk.csv",
                                      "policy_ordinance_article_evidence.csv",
                                      "policy_ordinance_candidates.csv", "admin_codes_202412.csv",
                                      "sigungu_2024_materials_verified.csv"])
def test_missing_required_artifacts_fail_closed(linked_sources, filename):
    (linked_sources["directory"] / filename).unlink()
    _assert_counts_suppressed(linked_sources["root"])


def test_missing_raw_legal_body_withholds_past_verified_document_counts(linked_sources):
    manifest = linked_sources["manifest"]
    detail = next(request["raw_file"] for request in manifest["requests"]
                  if request["parameters"].get("MST"))
    (linked_sources["root"] / detail).unlink()
    _assert_counts_suppressed(linked_sources["root"])


@pytest.mark.parametrize("raw", ["null", "[]", "{invalid JSON"])
def test_malformed_source_manifest_withholds_current_counts(linked_sources, raw):
    (linked_sources["root"] / evidence.LATEST).write_text(raw, encoding="utf-8")
    _assert_counts_suppressed(linked_sources["root"])


def test_missing_linkage_summary_withholds_cached_counts(linked_sources):
    (linked_sources["directory"] / "policy_ordinance_candidate_summary.json").unlink()
    assert _assert_counts_suppressed(linked_sources["root"])["status"] == "not_linked"


def test_legacy_linkage_without_source_binding_withholds_cached_counts(linked_sources):
    path = linked_sources["directory"] / "policy_ordinance_candidate_summary.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    summary.pop("input_binding")
    path.write_text(json.dumps(summary), encoding="utf-8")
    assert _assert_counts_suppressed(linked_sources["root"])["status"] == "input_binding_missing"


@pytest.mark.parametrize("invalid", [None, [], "legacy summary", {"input_binding": []}])
def test_malformed_summary_does_not_crash_or_restore_cached_counts(linked_sources, invalid):
    path = linked_sources["directory"] / "policy_ordinance_candidate_summary.json"
    path.write_text(json.dumps(invalid), encoding="utf-8")
    _assert_counts_suppressed(linked_sources["root"])


def test_saved_summary_counts_cannot_override_bound_artifacts(linked_sources):
    path = linked_sources["directory"] / "policy_ordinance_candidate_summary.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    summary["article_evidence_rows"] = 999
    path.write_text(json.dumps(summary), encoding="utf-8")
    _assert_counts_suppressed(linked_sources["root"])
