"""Synthetic offline collector tests; no network access or .env reads."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path

import pytest

from src.public_data.client import Page, PublicDataError
from src.public_data.collector import (
    CollectionFailure, build_queries, collect_dataset, date_windows, prepare_saved_run,
)

FACILITY = {
    "bzentyId": "SYNTHETIC-BUSINESS-001",
    "bzentyNm": "SYNTHETIC_REGISTRY_BUSINESS",
    "fcltTypeCd": "SYNTHETIC_TYPE",
    "fcltTypeNm": "SYNTHETIC_TYPE_NAME",
    "fcltSeCd": "SYNTHETIC_CATEGORY",
    "fcltSeNm": "SYNTHETIC_CATEGORY_NAME",
    "lctnCtpyCd": "SYNTHETIC_PROVINCE",
    "lctnCtpyNm": "SYNTHETIC_PROVINCE_NAME",
    "lctnSggCd": "SYNTHETIC_DISTRICT",
    "lctnSggNm": "SYNTHETIC_DISTRICT_NAME",
}
CONTRACT = {
    "untyCntrctNo": "SYNTHETIC-UNIFIED-001",
    "dcsnCntrctNo": "SYNTHETIC-DECISION-001",
    "cntrctRefNo": "SYNTHETIC-REFERENCE-001",
    "cntrctNm": "SYNTHETIC 재활용 선별시설 위탁운영",
    "cntrctInsttNm": "SYNTHETIC_PUBLIC_AGENCY",
    "cntrctCnclsDate": "2024-01-15",
    "cntrctPrd": "착수 후 365일",
    "totCntrctAmt": "1000000",
    "thtmCntrctAmt": "250000",
    "rgstDt": "2024-01-15 10:00:00",
    "chgDt": "2024-01-16 10:00:00",
}
CURRENT = "getCntrctInfoListServc"
CHANGE = CURRENT + "ChgHstry"
DELETE = CURRENT + "DltHstry"
PERIOD = {"begin": date(2024, 1, 1), "end": date(2024, 1, 1)}


class ScriptedClient:
    key = "test-key"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def fetch(self, endpoint, parameters, **options):
        self.calls.append((endpoint, deepcopy(parameters), deepcopy(options)))
        if not self.responses:
            raise AssertionError("Unexpected synthetic API call.")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        items, total = response
        page_no = int(parameters["pageNo"])
        page_size = int(parameters["numOfRows"])
        items = deepcopy(items)
        raw = json.dumps({
            "synthetic": True,
            "response": {
                "header": {"resultCode": "00"},
                "body": {
                    "items": items, "totalCount": total,
                    "pageNo": page_no, "numOfRows": page_size,
                },
            },
        }, ensure_ascii=False).encode("utf-8")
        return Page(
            items, total, page_no, page_size,
            {"format": "json", "envelope": "response", "result_code": "00"},
        ), raw


def artifact(root, name, run_id=None):
    matches = [
        path for path in Path(root).rglob(name)
        if (run_id is None or run_id in path.parts)
        and (name != "manifest.json" or "raw" in path.parts)
    ]
    assert len(matches) == 1, f"Expected one {name}, found {matches}"
    return matches[0]


def read_artifact(root, name, run_id=None):
    return json.loads(artifact(root, name, run_id).read_text(encoding="utf-8-sig"))


def collect_facilities(root, responses, run_id="synthetic_facilities", **options):
    client = ScriptedClient(responses)
    manifest = collect_dataset(
        "facilities", client=client, output_root=root, run_id=run_id,
        data_kind="synthetic", **options,
    )
    return manifest, client


def test_date_windows_cover_leap_days_without_gaps_or_overlap():
    begin, end = date(2024, 2, 25), date(2024, 3, 5)
    windows = date_windows(begin, end)
    assert windows == [(date(2024, 2, 25), date(2024, 3, 2)), (date(2024, 3, 3), end)]
    assert sum((right - left).days + 1 for left, right in windows) == (end - begin).days + 1
    assert all(0 <= (right - left).days <= 6 for left, right in windows)


def test_date_windows_include_a_single_requested_day():
    day = date(2024, 1, 1)
    assert date_windows(day, day) == [(day, day)]


def test_reversed_date_range_is_rejected():
    with pytest.raises((ValueError, PublicDataError)):
        date_windows(date(2024, 1, 2), date(2024, 1, 1))


def test_facility_query_uses_official_getlist_and_returntype_without_date_filter():
    query, = build_queries(
        "facilities", begin=date(2024, 1, 1), end=date(2024, 12, 31),
        page_size=25, response_format="xml",
    )
    assert query["endpoint"] == "https://apis.data.go.kr/B552584/rwBzentyInfoService/getList"
    assert query["operation"] == "getList"
    assert query["parameters"]["returnType"] == "xml"
    assert int(query["parameters"]["numOfRows"]) == 25
    assert int(query["parameters"]["pageNo"]) == 1
    assert "inqryBgnDt" not in query["parameters"]
    assert "inqryEndDt" not in query["parameters"]
    assert query["query_period"] is None


def test_contract_queries_partition_each_history_operation_into_seven_day_windows():
    queries = build_queries("contracts", begin=date(2024, 1, 1), end=date(2024, 1, 8))
    assert len(queries) == 6
    observed = set()
    for query in queries:
        parameters = query["parameters"]
        assert query["endpoint"].endswith("/" + query["operation"])
        assert query["parameters"]["type"] == "json"
        assert str(parameters["inqryDiv"]) == "1"
        assert "returnType" not in parameters
        assert query["query_period"] is not None
        observed.add((query["operation"], str(parameters["inqryBgnDt"]), str(parameters["inqryEndDt"])))
    assert observed == {
        (operation, begin, end)
        for operation in (CURRENT, CHANGE, DELETE)
        for begin, end in (
            ("202401010000", "202401072359"),
            ("202401080000", "202401082359"),
        )
    }


def test_contract_operation_selection_is_explicit():
    queries = build_queries("contracts", **PERIOD, operations=[CHANGE])
    assert len(queries) == 1
    assert queries[0]["operation"] == CHANGE


@pytest.mark.parametrize("kwargs", [
    {},
    {"begin": date(2024, 1, 1)},
    {"end": date(2024, 1, 1)},
])
def test_contract_query_requires_both_dates(kwargs):
    with pytest.raises((ValueError, PublicDataError)):
        build_queries("contracts", **kwargs)


@pytest.mark.parametrize("dataset,kwargs", [
    ("unknown", {}),
    ("facilities", {"page_size": 0}),
    ("facilities", {"response_format": "csv"}),
    ("facilities", {"operations": ["../../unapproved"]}),
])
def test_invalid_query_parameters_are_rejected_before_collection(dataset, kwargs):
    with pytest.raises((ValueError, PublicDataError)):
        build_queries(dataset, **kwargs)


def test_complete_facility_collection_writes_records_manifest_and_complete_pointer(tmp_path):
    manifest, client = collect_facilities(
        tmp_path, [([FACILITY], 1)], limit_pages=3, page_size=1,
    )
    assert manifest["status"] == "complete"
    assert manifest["complete"] is True
    assert manifest["record_count"] == 1
    assert len(manifest["pages"]) == 1
    assert len(client.calls) == 1
    assert read_artifact(tmp_path, "manifest.json")["status"] == "complete"
    records = read_artifact(tmp_path, "records.json")
    assert len(records) == 1
    assert records[0]["business_id"] == FACILITY["bzentyId"]
    assert records[0]["facility_name"] is None
    assert records[0]["data_kind"] == "synthetic"
    assert artifact(tmp_path, "records.csv").stat().st_size > 0
    assert read_artifact(tmp_path, "latest_complete.json")["run_id"] == manifest["run_id"]
    assert not list(tmp_path.rglob("latest_sample.json"))


def test_page_limit_produces_partial_sample_without_a_complete_pointer(tmp_path):
    manifest, client = collect_facilities(
        tmp_path, [([FACILITY], 2)], limit_pages=1, page_size=1,
    )
    assert manifest["status"] == "partial"
    assert manifest["complete"] is False
    assert manifest["record_count"] == 1
    assert len(client.calls) == 1
    assert read_artifact(tmp_path, "latest_sample.json")["run_id"] == manifest["run_id"]
    assert not list(tmp_path.rglob("latest_complete.json"))


def test_limit_pages_is_a_single_budget_across_contract_operations(tmp_path):
    client = ScriptedClient([([CONTRACT], 1)])
    manifest = collect_dataset(
        "contracts", client=client, **PERIOD, output_root=tmp_path,
        run_id="synthetic_global_budget", data_kind="synthetic",
        limit_pages=1, page_size=1,
    )
    assert manifest["query_count"] == 3
    assert manifest["completed_queries"] == 1
    assert manifest["status"] == "partial"
    assert manifest["complete"] is False
    assert len(client.calls) == 1
    assert not list(tmp_path.rglob("latest_complete.json"))


def test_all_required_pages_are_collected_when_budget_allows(tmp_path):
    second = {**FACILITY, "bzentyId": "SYNTHETIC-BUSINESS-002"}
    manifest, client = collect_facilities(
        tmp_path, [([FACILITY], 2), ([second], 2)], limit_pages=2, page_size=1,
    )
    assert manifest["status"] == "complete"
    assert manifest["record_count"] == 2
    assert [int(parameters["pageNo"]) for _, parameters, _ in client.calls] == [1, 2]


def test_contract_collection_writes_unapproved_cost_candidate_artifacts(tmp_path):
    client = ScriptedClient([([CONTRACT], 1)])
    manifest = collect_dataset(
        "contracts", client=client, **PERIOD, operations=[CURRENT],
        output_root=tmp_path, run_id="synthetic_contract", data_kind="synthetic",
        limit_pages=1, page_size=1,
    )
    assert manifest["status"] == "complete"
    assert manifest["record_count"] == 1
    records = read_artifact(tmp_path, "records.json")
    assert records[0]["amount_aggregation"] == "not_summed"
    assert records[0]["current_contract_amount"] == 250000
    candidates = read_artifact(tmp_path, "cost_candidates.json")
    assert len(candidates) == 1
    assert candidates[0]["validation_status"] == "candidate"
    assert candidates[0]["computed_krw_per_t"] is None
    assert artifact(tmp_path, "cost_candidates.csv").stat().st_size > 0


def test_explicit_no_data_completes_without_fabricating_a_record(tmp_path):
    manifest, client = collect_facilities(tmp_path, [([], 0)], limit_pages=1, page_size=5)
    assert manifest["status"] == "complete"
    assert manifest["record_count"] == 0
    assert read_artifact(tmp_path, "records.json") == []
    assert len(client.calls) == 1


@pytest.mark.parametrize("responses", [
    [([FACILITY], 2), ([{**FACILITY, "bzentyId": "SYNTHETIC-002"}], 3)],
    [([FACILITY], 2), ([FACILITY], 2)],
    [([], 1)],
    [([FACILITY], 2), PublicDataError("SYNTHETIC_MID_COLLECTION_FAILURE")],
])
def test_invalid_or_interrupted_pagination_leaves_failed_manifest(tmp_path, responses):
    client = ScriptedClient(responses)
    with pytest.raises(CollectionFailure) as captured:
        collect_dataset(
            "facilities", client=client, output_root=tmp_path,
            run_id="synthetic_failure", data_kind="synthetic",
            limit_pages=3, page_size=1,
        )
    failure = captured.value
    assert isinstance(failure, PublicDataError)
    assert failure.manifest["status"] == "failed"
    assert failure.manifest["complete"] is False
    assert Path(failure.manifest_path).is_file()
    assert read_artifact(tmp_path, "manifest.json")["status"] == "failed"
    assert not list(tmp_path.rglob("latest_complete.json"))
    assert not list(tmp_path.rglob("latest_sample.json"))


def test_failure_keeps_previous_complete_pointer_unchanged(tmp_path):
    collect_facilities(
        tmp_path, [([FACILITY], 1)], run_id="synthetic_prior", limit_pages=1, page_size=1,
    )
    pointer = artifact(tmp_path, "latest_complete.json")
    previous_bytes = pointer.read_bytes()
    client = ScriptedClient([([FACILITY], 2), PublicDataError("SYNTHETIC_FAILURE")])
    with pytest.raises(CollectionFailure):
        collect_dataset(
            "facilities", client=client, output_root=tmp_path,
            run_id="synthetic_later_failed", data_kind="synthetic",
            limit_pages=2, page_size=1,
        )
    assert pointer.read_bytes() == previous_bytes
    assert read_artifact(tmp_path, "manifest.json", "synthetic_later_failed")["status"] == "failed"


def test_facility_requested_2024_period_does_not_label_current_registry_as_2024(tmp_path):
    manifest, client = collect_facilities(
        tmp_path, [([FACILITY], 1)],
        begin=date(2024, 1, 1), end=date(2024, 12, 31),
        limit_pages=1, page_size=1,
    )
    assert manifest["requested_period"] is not None
    assert "inqryBgnDt" not in client.calls[0][1]
    record, = read_artifact(tmp_path, "records.json")
    assert record["reference_period"] is None
    assert record["historical_performance_verified"] is False


def test_facility_region_substring_filters_registry_locations(tmp_path):
    second = {
        **FACILITY, "bzentyId": "SYNTHETIC-SECOND",
        "lctnCtpyNm": "SYNTHETIC_OTHER_PROVINCE",
        "lctnSggNm": "SYNTHETIC_OTHER_DISTRICT",
    }
    manifest, _ = collect_facilities(
        tmp_path, [([FACILITY, second], 2)], region="SYNTHETIC_PROVINCE_NAME",
        limit_pages=1, page_size=2,
    )
    assert manifest["record_count"] == 1
    record, = read_artifact(tmp_path, "records.json")
    assert record["business_id"] == FACILITY["bzentyId"]


def test_unknown_contact_payloads_and_credentials_are_absent_from_all_saved_files(tmp_path):
    sentinel = "SYNTHETIC_PRIVATE_PAYLOAD_NOT_A_PERSON"
    sensitive = {
        **FACILITY,
        "bzentyNm": "SYNTHETIC_REGISTRY_test-key",
        "telNo": sentinel,
        "corpList": sentinel,
        "unreviewedField": sentinel,
    }
    collect_facilities(tmp_path, [([sensitive], 1)], limit_pages=1, page_size=1)
    for path in tmp_path.rglob("*"):
        if path.is_file():
            saved = path.read_text(encoding="utf-8-sig")
            assert sentinel not in saved
            assert ScriptedClient.key not in saved



def test_saved_public_snapshots_reproduce_records_without_a_client(tmp_path):
    collect_facilities(tmp_path, [([FACILITY], 1)], limit_pages=1, page_size=1)
    original_records = read_artifact(tmp_path, "records.json")
    pointer = artifact(tmp_path, "latest_complete.json")
    pointer_bytes = pointer.read_bytes()
    directory = prepare_saved_run(artifact(tmp_path, "manifest.json"), output_root=tmp_path)
    rebuilt = json.loads((directory / "records.json").read_text(encoding="utf-8-sig"))
    assert rebuilt == original_records
    assert pointer.read_bytes() == pointer_bytes


def test_saved_snapshot_hash_mismatch_is_rejected(tmp_path):
    collect_facilities(tmp_path, [([FACILITY], 1)], limit_pages=1, page_size=1)
    manifest_path = artifact(tmp_path, "manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    snapshot_path = manifest_path.parent / manifest["pages"][0]["file"]
    snapshot_path.write_bytes(snapshot_path.read_bytes() + b" ")
    with pytest.raises(ValueError):
        prepare_saved_run(manifest_path, output_root=tmp_path)


def test_saved_manifest_cannot_change_run_id_into_a_relative_output_path(tmp_path):
    collect_facilities(tmp_path, [([FACILITY], 1)], limit_pages=1, page_size=1)
    manifest_path = artifact(tmp_path, "manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    # This path stays within pytest's temporary area even in a vulnerable
    # implementation, while exercising a forbidden escape of the dataset path.
    manifest["run_id"] = "../synthetic_escape"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        prepare_saved_run(manifest_path, output_root=tmp_path / "rebuild")
