"""Offline adapter checks using synthetic records in official item field shapes.

No record below is a real facility or contract observation. Contact/vendor
payload tests contain only a sentinel, never a person's name or contact detail.
"""
from copy import deepcopy
import json

import pytest

from src.public_data.facilities import PublicDataSchemaError, normalize_facilities
from src.public_data.contracts import (
    classify_contract_title, contract_key, merge_contract_versions, normalize_contracts,
)

SYNTHETIC_CONTEXT = {
    "data_kind": "synthetic",
    "retrieved_at": "2026-11-16T09:00:00+09:00",
    "reference_period": "2024",
    "region": "SYNTHETIC_REGION",
}
SYNTHETIC_FACILITY = {
    "bzentyId": "SYNTHETIC-BUSINESS-001",
    "bzentyNm": "SYNTHETIC_PUBLIC_REGISTRY_BUSINESS",
    "fcltTypeCd": "SYNTHETIC_TYPE",
    "fcltTypeNm": "SYNTHETIC_TYPE_NAME",
    "fcltSeCd": "SYNTHETIC_CATEGORY",
    "fcltSeNm": "SYNTHETIC_CATEGORY_NAME",
    "lctnCtpyCd": "SYNTHETIC_PROVINCE",
    "lctnCtpyNm": "SYNTHETIC_PROVINCE_NAME",
    "lctnSggCd": "SYNTHETIC_DISTRICT",
    "lctnSggNm": "SYNTHETIC_DISTRICT_NAME",
}
SYNTHETIC_CONTRACT = {
    "untyCntrctNo": "SYNTHETIC-UNIFIED-001",
    "dcsnCntrctNo": "SYNTHETIC-DECISION-003",
    "cntrctRefNo": "SYNTHETIC-REFERENCE-XYZ",
    "cntrctNm": "SYNTHETIC 재활용 선별시설 위탁운영",
    "bsnsDivNm": "일반용역",
    "lngtrmCtnuDivNm": "장기계속",
    "cntrctInsttCd": "SYNTHETIC_PUBLIC_AGENCY_CODE",
    "cntrctInsttNm": "SYNTHETIC_PUBLIC_AGENCY",
    "cntrctCnclsDate": "2024-01-15",
    "cntrctPrd": "착수 후 365일",
    "totCntrctAmt": "1,000,000",
    "thtmCntrctAmt": "250000",
    "rgstDt": "2024-01-15 10:00:00",
    "chgDt": "2024-01-16 11:00:00",
    "wbgnDate": "2024-02-01",
    "thtmScmpltDate": "2024-12-31",
    "ttalScmpltDate": "2027-12-31",
}


def context(operation="getCntrctInfoListServc", **overrides):
    return {**SYNTHETIC_CONTEXT, "operation": operation, **overrides}


def contract(changes=None, **context_overrides):
    item = {**SYNTHETIC_CONTRACT, **(changes or {})}
    return normalize_contracts([item], context(**context_overrides))[0]


def test_facility_business_name_is_not_promoted_to_a_facility_name():
    row = normalize_facilities([SYNTHETIC_FACILITY], SYNTHETIC_CONTEXT)[0]
    assert row["business_id"] == "SYNTHETIC-BUSINESS-001"
    assert row["business_name"] == "SYNTHETIC_PUBLIC_REGISTRY_BUSINESS"
    assert row["facility_id"] is None
    assert row["facility_name"] is None
    assert row["province_name"] == "SYNTHETIC_PROVINCE_NAME"
    assert row["district_name"] == "SYNTHETIC_DISTRICT_NAME"
    assert row["data_kind"] == "synthetic"


def test_facility_capacity_address_and_registration_date_are_not_invented():
    item = {**SYNTHETIC_FACILITY, "capacity": "100", "regDate": "2024-01-01"}
    row = normalize_facilities([item], SYNTHETIC_CONTEXT)[0]
    for key in ("address", "facility_capacity", "facility_capacity_unit", "registration_date"):
        assert row[key] is None
    assert "won_per_ton" not in row
    assert row["reference_period"] is None
    assert row["requested_reference_period"] == "2024"
    assert row["historical_performance_verified"] is False


def test_facility_unknown_schema_fails_closed():
    with pytest.raises(PublicDataSchemaError, match="business_id"):
        normalize_facilities([{"facilityName": "SYNTHETIC", "facilityId": "001"}], SYNTHETIC_CONTEXT)


def test_facility_extension_requires_reviewable_mapping_source():
    ctx = {**SYNTHETIC_CONTEXT, "field_mapping": {"facility_name": "verifiedFacilityName"}}
    item = {**SYNTHETIC_FACILITY, "verifiedFacilityName": "SYNTHETIC_FACILITY"}
    with pytest.raises(PublicDataSchemaError, match="source URL"):
        normalize_facilities([item], ctx)
    ctx["field_mapping_source"] = "https://www.data.go.kr/data/15172490/openapi.do"
    row = normalize_facilities([item], ctx)[0]
    assert row["facility_name"] == "SYNTHETIC_FACILITY"
    assert row["facility_name_status"] == "explicit_verified_mapping"


def test_explicit_mapping_typo_does_not_silently_become_missing_data():
    ctx = {
        **SYNTHETIC_CONTEXT,
        "field_mapping": {"facility_name": "missingVerifiedField"},
        "field_mapping_source": "https://www.data.go.kr/data/15172490/openapi.do",
    }
    with pytest.raises(PublicDataSchemaError, match="mapped field"):
        normalize_facilities([SYNTHETIC_FACILITY], ctx)


def test_personal_and_unknown_fields_are_not_copied_from_response_or_context():
    sentinel = "SYNTHETIC_PRIVATE_PAYLOAD_NOT_A_PERSON"
    item = {**SYNTHETIC_FACILITY, "telNo": sentinel, "unreviewedPayload": sentinel}
    ctx = {**SYNTHETIC_CONTEXT, "private_note": sentinel}
    encoded = json.dumps(normalize_facilities([item], ctx))
    assert sentinel not in encoded


def test_personal_field_cannot_be_used_as_an_explicit_extension():
    ctx = {
        **SYNTHETIC_CONTEXT,
        "field_mapping": {"address": "contactPhone"},
        "field_mapping_source": "https://www.data.go.kr/data/15172490/openapi.do",
    }
    with pytest.raises(PublicDataSchemaError, match="Personal"):
        normalize_facilities([SYNTHETIC_FACILITY], ctx)


def test_context_source_url_has_query_credentials_removed():
    ctx = {
        **SYNTHETIC_CONTEXT,
        "source_url": "https://www.data.go.kr/data/15172490/openapi.do?serviceKey=SYNTHETIC_CREDENTIAL&pageNo=1",
    }
    row = normalize_facilities([SYNTHETIC_FACILITY], ctx)[0]
    assert row["source_url"].endswith("?pageNo=1")
    assert "SYNTHETIC_CREDENTIAL" not in json.dumps(row)


def test_contract_official_fields_keep_different_amount_meanings():
    row = contract()
    assert row["total_contract_amount"] == 1_000_000
    assert row["current_contract_amount"] == 250_000
    assert row["contract_agency_name"] == "SYNTHETIC_PUBLIC_AGENCY"
    assert row["contract_period"] == "착수 후 365일"
    assert row["start_date"] == "2024-02-01"
    assert row["cost_interpretation"] == "public_contract_amount_not_actual_cost"
    assert row["amount_aggregation"] == "not_summed"
    assert row["change_order"] is None
    assert row["contract_id"] == "SYNTHETIC-DECISION-003"


def test_general_contract_zero_total_is_not_replaced_by_current_amount():
    row = contract({"totCntrctAmt": "0", "lngtrmCtnuDivNm": "신규"})
    assert row["total_contract_amount"] == 0
    assert row["current_contract_amount"] == 250_000


def test_registration_year_is_not_contract_performance_year():
    row = contract({"cntrctCnclsDate": "2023-12-29", "rgstDt": "2024-01-03 10:00:00"})
    assert row["contract_year"] == 2023
    assert row["reference_period"] is None
    assert row["requested_reference_period"] == "2024"


def test_contract_operation_and_schema_are_explicit():
    with pytest.raises(PublicDataSchemaError, match="operation"):
        normalize_contracts([SYNTHETIC_CONTRACT], SYNTHETIC_CONTEXT)
    with pytest.raises(PublicDataSchemaError, match="title"):
        normalize_contracts([SYNTHETIC_CONTRACT], context("getCntrctInfoListCnstwk"))


def test_construction_uses_cnstwk_name_and_construction_completion_dates():
    item = dict(SYNTHETIC_CONTRACT)
    del item["cntrctNm"]
    item.update({
        "cnstwkNm": "SYNTHETIC 재활용 선별시설 신설공사",
        "cbgnDate": "2024-03-01",
        "thtmCcmpltDate": "2024-12-01",
        "ttalCcmpltDate": "2025-12-01",
    })
    row = normalize_contracts([item], context("getCntrctInfoListCnstwk"))[0]
    assert row["business_type"] == "construction"
    assert row["start_date"] == "2024-03-01"
    assert row["current_completion_date"] == "2024-12-01"
    assert row["total_completion_date"] == "2025-12-01"


def test_contract_vendor_and_demand_contact_strings_are_discarded():
    sentinel = "SYNTHETIC_PRIVATE_PAYLOAD_NOT_A_PERSON"
    row = contract({
        "corpList": sentinel, "dminsttList": sentinel, "cntrctInsttChrgpsnNm": sentinel,
    })
    assert sentinel not in json.dumps(row)
    assert "corpList" not in row
    assert "dminsttList" not in row


@pytest.mark.parametrize("value", ["-1", "NaN", "1,23", "100원", True, {"amount": 100}])
def test_invalid_money_fails_closed_without_zero_filling(value):
    with pytest.raises(PublicDataSchemaError):
        contract({"thtmCntrctAmt": value})


def test_invalid_calendar_date_fails_closed():
    with pytest.raises(PublicDataSchemaError, match="calendar"):
        contract({"cntrctCnclsDate": "2024-02-30"})


def test_deletion_history_accepts_its_minimal_official_schema():
    item = {
        "untyCntrctNo": "SYNTHETIC-UNIFIED-001",
        "dcsnCntrctNo": "SYNTHETIC-DECISION-003",
        "cntrctRefNo": "SYNTHETIC-REFERENCE-XYZ",
        "dltDt": "2024-02-01 10:00:00",
        "chgDivNm": "SYNTHETIC_DELETION",
        "rgstDt": "2024-01-15 10:00:00",
        "chgDt": "2024-02-01 10:00:00",
    }
    row = normalize_contracts([item], context("getCntrctInfoListServcDltHstry"))[0]
    assert row["record_status"] == "deleted"
    assert row["deleted_at"] == "2024-02-01T10:00:00"
    assert row["title"] is None
    assert row["current_contract_amount"] is None


def test_contract_key_requires_documented_unified_identifier():
    assert contract_key(contract()) == ("15129427", "SYNTHETIC-UNIFIED-001")
    with pytest.raises(PublicDataSchemaError, match="unified"):
        contract_key({"title": "SYNTHETIC", "contract_id": "SYNTHETIC-DECISION"})


def test_duplicate_observations_collapse_without_adding_amounts():
    first = contract()
    second = contract(retrieved_at="2026-11-16T10:00:00+09:00")
    row = merge_contract_versions([first, second])[0]
    assert row["version_count"] == 1
    assert row["observation_count"] == 2
    assert row["current_contract_amount"] == 250_000
    assert row["version_history"][0]["duplicate_count"] == 2
    assert len(row["version_history"][0]["observed_retrieval_times"]) == 2
    assert row["has_conflict"] is False


def test_current_and_change_endpoint_same_state_are_one_version():
    first = contract()
    second = contract(operation="getCntrctInfoListServcChgHstry")
    row = merge_contract_versions([first, second])[0]
    assert row["version_count"] == 1
    assert len(row["version_history"][0]["observed_operations"]) == 2
    assert row["has_conflict"] is False


def test_changed_long_term_contract_preserves_history_and_latest_not_sum():
    first = contract()
    second = contract(
        {"chgDt": "2024-02-01 11:00:00", "thtmCntrctAmt": "300000", "totCntrctAmt": "1100000"},
        operation="getCntrctInfoListServcChgHstry",
    )
    row = merge_contract_versions([second, first])[0]
    assert row["version_count"] == 2
    assert row["current_contract_amount"] == 300_000
    assert row["total_contract_amount"] == 1_100_000
    assert [version["current_contract_amount"] for version in row["version_history"]] == [250_000, 300_000]
    assert row["has_conflict"] is False
    assert row["amount_aggregation"] == "not_summed"


def test_same_version_amount_conflict_does_not_choose_a_value():
    row = merge_contract_versions([contract(), contract({"thtmCntrctAmt": "300000"})])[0]
    assert row["version_count"] == 2
    assert row["has_conflict"] is True
    assert "same_version_has_conflicting_public_fields" in row["conflict_reasons"]
    assert row["current_contract_amount"] is None
    assert row["total_contract_amount"] is None


def test_unknown_version_order_remains_a_conflict():
    first = contract({"rgstDt": "", "chgDt": ""})
    second = contract({
        "rgstDt": "", "chgDt": "", "dcsnCntrctNo": "SYNTHETIC-OTHER",
        "thtmCntrctAmt": "300000",
    })
    row = merge_contract_versions([first, second])[0]
    assert "version_order_unverified" in row["conflict_reasons"]
    assert row["current_contract_amount"] is None


def test_different_unified_contracts_are_not_deduplicated_by_title():
    rows = merge_contract_versions([
        contract(), contract({"untyCntrctNo": "SYNTHETIC-UNIFIED-002"}),
    ])
    assert len(rows) == 2


def test_latest_deletion_keeps_old_amount_only_in_history():
    first = contract()
    deleted = normalize_contracts([{
        "untyCntrctNo": first["unified_contract_id"],
        "dcsnCntrctNo": first["contract_id"],
        "cntrctRefNo": first["contract_reference_id"],
        "dltDt": "2024-02-01 10:00:00",
        "chgDivNm": "SYNTHETIC_DELETION",
        "rgstDt": "2024-01-15 10:00:00",
        "chgDt": "2024-02-01 10:00:00",
    }], context("getCntrctInfoListServcDltHstry"))[0]
    row = merge_contract_versions([deleted, first])[0]
    assert row["is_deleted"] is True
    assert row["current_contract_amount"] is None
    assert any(version["current_contract_amount"] == 250_000 for version in row["version_history"])


def test_merge_does_not_mutate_input_or_retain_unreviewed_fields():
    first = contract()
    first["corpList"] = "SYNTHETIC_PRIVATE_PAYLOAD_NOT_A_PERSON"
    before = deepcopy(first)
    merged = merge_contract_versions([first])
    assert first == before
    assert "SYNTHETIC_PRIVATE_PAYLOAD_NOT_A_PERSON" not in json.dumps(merged)


@pytest.mark.parametrize(
    ("title", "category", "review"),
    [
        ("재활용 선별시설 신설공사", "facility_construction", False),
        ("재활용 선별기 구매", "equipment_purchase", False),
        ("재활용 선별시설 위탁운영", "operation_maintenance", False),
        ("생활폐기물 수집운반 용역", "waste_collection_transport", False),
        ("생활폐기물 위탁처리 용역", "waste_treatment_service", False),
        ("생활폐기물 수집운반 및 위탁처리", "mixed_scope", True),
        ("재활용 선별시설 실시설계용역", "professional_service", True),
        ("SYNTHETIC 제목", "unclassified", True),
        (None, "unclassified", True),
    ],
)
def test_title_categories_are_conservative(title, category, review):
    assert classify_contract_title(title) == (category, review)

