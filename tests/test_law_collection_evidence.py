"""Local legal-source integrity checks use synthetic API-shaped records only."""
import copy
import hashlib
import json

import pandas as pd
import pytest

from src.regional_data import law_client


def _record(serial="10017", law_id="17"):
    return {"자치법규일련번호": serial, "자치법규ID": law_id,
            "자치법규명": "가상 재활용 조례", "지자체기관명": "서울특별시 가상구",
            "공포일자": "20240101", "시행일자": "20240201"}


@pytest.fixture
def collection(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(law_client, "load_law_oc", lambda root: "synthetic_oc")
    monkeypatch.setattr(law_client, "load_law_domain", lambda root: "")

    def fetch(endpoint, params, oc, **kwargs):
        calls.append((endpoint, dict(params)))
        if endpoint == law_client.LAW_SEARCH_ENDPOINT:
            payload = [_record(), _record("10018", "18")]
        else:
            payload = dict(_record(), 조내용="제1조 이 조례는 가상 시험 자료다.")
        return json.dumps(payload, ensure_ascii=False).encode("utf-8"), payload

    monkeypatch.setattr(law_client, "_fetch_json", fetch)
    args = {"root": tmp_path, "keywords": ["재활용"], "limit_pages": 1,
            "detail_budget": 1, "delay_seconds": 0}
    manifest = law_client.collect_ordinances(**args)
    return tmp_path, manifest, args, calls


def test_recorded_collection_and_same_scope_cache_validate_without_network(collection, monkeypatch):
    root, manifest, args, calls = collection
    assert law_client.validate_collection_evidence(root, manifest) is None
    assert len(calls) == 2
    monkeypatch.setattr(law_client, "_fetch_json", lambda *a, **kw: pytest.fail("cache contacted API"))
    assert law_client.collect_ordinances(**args) == manifest


@pytest.mark.parametrize("source_index", [0, 1], ids=["list", "detail"])
@pytest.mark.parametrize("change", ["deleted", "modified"])
def test_changed_raw_evidence_revokes_cache_and_triggers_recollection(collection, source_index, change):
    root, manifest, args, calls = collection
    source = root / manifest["requests"][source_index]["raw_file"]
    if change == "deleted":
        source.unlink()
    else:
        source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="LAW_COLLECTION_(SOURCE_CHANGED|SOURCE_MISSING_OR_OUTSIDE_ROOT)"):
        law_client.validate_collection_evidence(root, manifest)
    fresh = law_client.collect_ordinances(**args)
    assert len(calls) == 4
    assert fresh["status"] == "complete_within_page_budget"
    assert law_client.validate_collection_evidence(root, fresh) is None


def test_candidate_csv_must_match_recorded_hash(collection):
    root, manifest, _, _ = collection
    path = root / manifest["candidate_csv"]
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="LAW_COLLECTION_CANDIDATE_CHANGED"):
        law_client.validate_collection_evidence(root, manifest)


@pytest.mark.parametrize("contents", ["{invalid", "[]"])
def test_malformed_cache_manifest_is_recollected(collection, contents):
    root, _, args, calls = collection
    cached = sorted((root / "data/raw/regional_2024/law_ordinances").glob("*/manifest.json"))[-1]
    cached.write_text(contents, encoding="utf-8")
    fresh = law_client.collect_ordinances(**args)
    assert len(calls) == 4
    assert law_client.validate_collection_evidence(root, fresh) is None


@pytest.mark.parametrize("change", ["missing_hash", "outside_root", "duplicate_source"])
def test_missing_or_unsafe_source_binding_is_rejected(collection, change):
    root, manifest, _, _ = collection
    changed = copy.deepcopy(manifest)
    if change == "missing_hash":
        changed["requests"][0].pop("sha256")
    elif change == "outside_root":
        changed["requests"][0]["raw_file"] = "../unrelated.json"
    else:
        changed["requests"].append(copy.deepcopy(changed["requests"][0]))
    with pytest.raises(ValueError, match="LAW_COLLECTION_"):
        law_client.validate_collection_evidence(root, changed)


def _rewrite_candidates(root, manifest, transform):
    path = root / manifest["candidate_csv"]
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    transform(frame)
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    manifest["candidate_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()


def test_candidate_reference_must_be_bound_to_its_list_page(collection):
    root, manifest, _, _ = collection
    changed = copy.deepcopy(manifest)
    _rewrite_candidates(root, changed, lambda frame: frame.loc.__setitem__(
        (0, "raw_list_page"), changed["requests"][1]["raw_file"]))
    with pytest.raises(ValueError, match="LAW_COLLECTION_CANDIDATE_SOURCE_UNBOUND"):
        law_client.validate_collection_evidence(root, changed)


def test_hash_valid_detail_still_requires_matching_identity_and_body(collection):
    root, manifest, _, _ = collection
    changed = copy.deepcopy(manifest)
    detail_request = changed["requests"][1]
    path = root / detail_request["raw_file"]
    path.write_text(json.dumps(_record()), encoding="utf-8")
    detail_request["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="LAW_API_DETAIL_BODY_UNVERIFIED"):
        law_client.validate_collection_evidence(root, changed)


@pytest.mark.parametrize("field", ["candidate_count", "pages_used", "detail_count", "detail_rejected_count"])
def test_manifest_counts_must_reconcile_to_sources_and_candidate_rows(collection, field):
    root, manifest, _, _ = collection
    changed = copy.deepcopy(manifest)
    changed[field] += 1
    with pytest.raises(ValueError, match="LAW_COLLECTION_COUNT_MISMATCH"):
        law_client.validate_collection_evidence(root, changed)


def test_partial_detail_failure_preserves_valid_list_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(law_client, "load_law_oc", lambda root: "synthetic_oc")
    monkeypatch.setattr(law_client, "load_law_domain", lambda root: "")

    def fetch(endpoint, params, oc, **kwargs):
        payload = [_record()] if endpoint == law_client.LAW_SEARCH_ENDPOINT else {"error": "synthetic failure"}
        return json.dumps(payload).encode("utf-8"), payload

    monkeypatch.setattr(law_client, "_fetch_json", fetch)
    manifest = law_client.collect_ordinances(root=tmp_path, keywords=["재활용"], limit_pages=1,
                                             detail_budget=1, delay_seconds=0)
    assert manifest["status"] == "partial_detail_validation_failed"
    assert manifest["detail_count"] == 0 and manifest["detail_rejected_count"] == 1
    assert law_client.validate_collection_evidence(tmp_path, manifest) is None


@pytest.mark.parametrize("field,value", [
    ("자치법규명", "다른 조례"), ("지자체기관명", "부산광역시 가상구"),
    ("공포일자", "20230101"), ("시행일자", "20250101"),
])
def test_detail_metadata_cannot_explicitly_disagree_with_list_candidate(field, value):
    record = dict(_record(), 조내용="가상 본문")
    record[field] = value
    candidate = {"ordinance_serial": "10017", "ordinance_id": "17", "policy_name": "가상 재활용 조례",
                 "locality": "서울특별시 가상구", "promulgation_date": "20240101", "effective_date": "20240201"}
    with pytest.raises(ValueError, match="LAW_API_DETAIL_METADATA_MISMATCH"):
        law_client._validate_detail(record, candidate)


def test_detail_metadata_allows_missing_optional_fields_and_equivalent_date_format():
    candidate = {"ordinance_serial": "10017", "ordinance_id": "17", "policy_name": "가상 재활용 조례",
                 "locality": "서울특별시 가상구", "effective_date": "20240201"}
    record = dict(_record(), 조내용="가상 본문")
    record["시행일자"] = "2024. 2. 1."
    assert law_client._validate_detail(record, candidate) is None
    record.pop("시행일자")
    record.pop("지자체기관명")
    assert law_client._validate_detail(record, candidate) is None


def test_legal_title_middle_dot_variants_match_without_rewriting_source():
    candidate = {"ordinance_serial": "10017", "ordinance_id": "17",
                 "policy_name": "가상 재활용·자원순환 조례"}
    record = dict(_record(), 조내용="가상 본문")
    record["자치법규명"] = "가상 재활용ㆍ자원순환 조례"
    original = copy.deepcopy(record)
    assert law_client._validate_detail(record, candidate) is None
    assert record == original
    assert candidate["policy_name"] == "가상 재활용·자원순환 조례"
    assert law_client.normalize_legal_title(" \u1100\u1161상   재활용ㆍ자원순환 조례 ") == candidate["policy_name"]


@pytest.mark.parametrize("body_title", ["가상 폐기물ㆍ자원순환 조례", "가상 재활용자원순환 조례"])
def test_legal_title_normalization_preserves_substantive_differences(body_title):
    candidate = {"ordinance_serial": "10017", "ordinance_id": "17",
                 "policy_name": "가상 재활용·자원순환 조례"}
    record = dict(_record(), 조내용="가상 본문")
    record["자치법규명"] = body_title
    with pytest.raises(ValueError, match="LAW_API_DETAIL_METADATA_MISMATCH"):
        law_client._validate_detail(record, candidate)


def test_title_normalization_does_not_fuzz_locality_matching():
    candidate = {"ordinance_serial": "10017", "ordinance_id": "17",
                 "policy_name": "가상 재활용 조례", "locality": "가상·기관"}
    record = dict(_record(), 조내용="가상 본문")
    record["지자체기관명"] = "가상ㆍ기관"
    with pytest.raises(ValueError, match="LAW_API_DETAIL_METADATA_MISMATCH"):
        law_client._validate_detail(record, candidate)
