"""비용 후보의 결측 보존·대상 일치·명시 검토와 중복 방지를 검증한다."""
from copy import deepcopy

import pytest

from src.cost_candidate import CANDIDATE_FIELDS, create_cost_candidate
from src.evidence_validation import MATCH_FIELDS, validate_candidate_set, validate_evidence


@pytest.fixture
def contract():
    return dict(
        source_id="CONTRACT_SERVICE", source_url="https://example.org/contracts/123",
        contract_id="123", reference_year=2024, price_year=2024,
        service_period="2024-01-01/2024-12-31", geography="서울특별시 구로구",
        scope="생활폐기물 분리배출 재활용품", process_stage="sorting", material_type="폐합성수지류",
        amount_krw=2000, amount_basis="contract_amount",
        includes_labor=True, includes_transport=False, includes_disposal=True,
        includes_capital=False, includes_transfer=False, overlap_risk=False,
    )


@pytest.fixture
def throughput(contract):
    return {
        **{field: contract[field] for field in MATCH_FIELDS},
        "source_id": "OPERATION_RECORD", "source_url": "https://example.org/operations/123",
        "contract_id": "123", "throughput_t": 10.0, "throughput_basis": "actual_processed_t",
    }


def test_empty_and_contract_only_remain_candidates_without_zero_replacement(contract):
    empty = create_cost_candidate({})
    assert empty["validation_status"] == "candidate"
    for field in ("amount_krw", "throughput_t", "computed_krw_per_t", "includes_labor", "overlap_risk"):
        assert empty[field] is None
    assert any("자료 미입력" in item for item in empty["validation_issues"])
    amount_only = create_cost_candidate(contract)
    assert amount_only["amount_krw"] == 2000
    assert amount_only["throughput_t"] is None
    assert amount_only["computed_krw_per_t"] is None
    assert amount_only["validation_status"] == "candidate"
    assert set(CANDIDATE_FIELDS) <= set(amount_only)


def test_matching_evidence_is_only_a_proxy_until_explicit_review(contract, throughput):
    result = create_cost_candidate(contract, throughput)
    assert result["computed_krw_per_t"] == 200
    assert result["validation_status"] == "proxy"
    assert result["evidence_grade"] == "C"
    assert validate_evidence(result) == []
    assert result["throughput_evidence"]["source_id"] == "OPERATION_RECORD"
    assert result["contract_evidence"]["amount_basis"] == "contract_amount"


def test_observed_zero_amount_is_distinct_from_missing(contract, throughput):
    contract["amount_krw"] = 0
    result = create_cost_candidate(contract, throughput)
    assert result["amount_krw"] == 0
    assert result["computed_krw_per_t"] == 0
    assert result["validation_status"] == "proxy"
    contract["amount_krw"] = None
    unknown = create_cost_candidate(contract, throughput)
    assert unknown["amount_krw"] is None
    assert unknown["computed_krw_per_t"] is None


@pytest.mark.parametrize("value", [True, False, float("nan"), float("inf"), -float("inf"), -1, "100"])
@pytest.mark.parametrize("field", ["amount_krw", "throughput_t"])
def test_numeric_inputs_require_finite_numbers_without_bool(contract, throughput, field, value):
    record = contract if field == "amount_krw" else throughput
    record[field] = value
    with pytest.raises(ValueError, match=field):
        create_cost_candidate(contract, throughput)


def test_zero_throughput_is_invalid(contract, throughput):
    throughput["throughput_t"] = 0
    with pytest.raises(ValueError, match="throughput_t"):
        create_cost_candidate(contract, throughput)


@pytest.mark.parametrize("field", ["includes_labor", "includes_transport", "includes_disposal", "includes_capital", "includes_transfer", "overlap_risk"])
@pytest.mark.parametrize("invalid", [0, 1, "false"])
def test_inclusion_flags_require_actual_booleans(contract, throughput, field, invalid):
    contract[field] = invalid
    with pytest.raises(ValueError, match=field):
        create_cost_candidate(contract, throughput)


@pytest.mark.parametrize("field", MATCH_FIELDS)
def test_every_scope_dimension_must_match(contract, throughput, field):
    throughput[field] = 2023 if field == "reference_year" else "다른 범위"
    result = create_cost_candidate(contract, throughput)
    assert result["computed_krw_per_t"] is None
    assert result["validation_status"] == "rejected"
    assert any(field in issue and "불일치" in issue for issue in result["validation_issues"])


@pytest.mark.parametrize("field", MATCH_FIELDS)
def test_missing_scope_is_not_treated_as_a_match(contract, throughput, field):
    contract[field] = None
    throughput[field] = None
    result = create_cost_candidate(contract, throughput)
    assert result["computed_krw_per_t"] is None
    assert result["validation_status"] == "candidate"
    assert any(field in issue and "미입력" in issue for issue in result["validation_issues"])


@pytest.mark.parametrize("field", ["source_id", "source_url"])
@pytest.mark.parametrize("side", ["contract", "throughput"])
def test_both_sources_need_identity_and_url(contract, throughput, side, field):
    (contract if side == "contract" else throughput)[field] = None
    result = create_cost_candidate(contract, throughput)
    assert result["validation_status"] == "candidate"
    assert result["computed_krw_per_t"] is None


@pytest.mark.parametrize("field", ["price_year", "amount_basis", "includes_capital", "overlap_risk"])
def test_unconfirmed_cost_basis_or_inclusion_blocks_ratio(contract, throughput, field):
    contract[field] = None
    result = create_cost_candidate(contract, throughput)
    assert result["computed_krw_per_t"] is None
    assert result["validation_status"] == "candidate"


@pytest.mark.parametrize("field,value", [("includes_transfer", True), ("overlap_risk", True), ("duplicate_of", "another-id")])
def test_transfer_and_duplicate_costs_cannot_be_promoted(contract, throughput, field, value):
    contract[field] = value
    result = create_cost_candidate(contract, throughput, review={"status": "validated", "reviewed_by": "검토자"})
    assert result["validation_status"] == "rejected"
    assert result["computed_krw_per_t"] is None
    assert any(field in issue for issue in result["validation_issues"])


@pytest.mark.parametrize("review", [
    {"status": "validated"},
    {"status": "validated", "review_note": "검토 요청"},
    {"status": "validated", "review_note": "검토 요청", "explicit_approval": False},
])
def test_validated_cannot_be_granted_without_external_explicit_review(contract, throughput, review):
    result = create_cost_candidate(contract, throughput, review)
    assert result["validation_status"] == "proxy"
    assert any("명시적인 검토" in issue for issue in result["validation_issues"])


@pytest.mark.parametrize("review", [
    {"status": "validated", "reviewed_by": "외부 검토자"},
    {"validation_status": "validated", "review_note": "기간·범위·포함항목 대조 완료", "explicit_approval": True},
])
def test_external_review_allows_validation_but_does_not_change_inputs(contract, throughput, review):
    originals = deepcopy((contract, throughput, review))
    result = create_cost_candidate(contract, throughput, review)
    assert result["validation_status"] == "validated"
    assert result["evidence_grade"] == "B"
    assert result["computed_krw_per_t"] == 200
    assert validate_evidence(result) == []
    assert (contract, throughput, review) == originals


def test_reviewer_name_without_validation_request_stays_proxy(contract, throughput):
    result = create_cost_candidate(contract, throughput, {"reviewed_by": "담당자"})
    assert result["validation_status"] == "proxy"


def test_api_registration_query_period_is_never_service_period_or_year():
    result = create_cost_candidate({
        "source_id": "G2B", "source_url": "https://example.org/contract",
        "unified_contract_id": "UNIFIED-123", "registered_at": "2024-01-01",
        "reference_period": "2024-01-01/2024-12-31", "contract_period": "계약일로부터 1년",
        "total_amount_krw": 0, "current_amount_krw": 2000,
        "total_contract_amount": 0, "current_contract_amount": 2000,
    })
    assert result["contract_id"] == "UNIFIED-123"
    assert result["service_period"] is None
    assert result["reference_year"] is None
    assert result["price_year"] is None
    assert result["amount_krw"] is None
    assert result["amount_basis"] is None
    assert result["computed_krw_per_t"] is None
    assert result["validation_status"] == "candidate"


def test_explicit_service_dates_supported_without_registration_date_inference(contract, throughput):
    for record in (contract, throughput):
        record.pop("service_period")
        record.update(period_start="2024-01-01", period_end="2024-12-31")
    result = create_cost_candidate(contract, throughput)
    assert result["service_period"] == "2024-01-01/2024-12-31"
    assert result["computed_krw_per_t"] == 200


def test_same_contract_multiple_sources_or_amount_bases_are_duplicates(contract, throughput):
    first = create_cost_candidate(contract, throughput)
    alternate = deepcopy(contract)
    alternate.update(source_id="SECONDARY", amount_basis="executed_amount")
    second = create_cost_candidate(alternate, throughput)
    assert first["candidate_id"] != second["candidate_id"]
    assert any("동일 계약" in issue for issue in validate_candidate_set([first, second]))
    assert any("candidate_id 중복" in issue for issue in validate_candidate_set([first, first]))


def test_tampered_or_nonfinite_computed_ratio_fails_validation(contract, throughput):
    result = create_cost_candidate(contract, throughput)
    for invalid in (True, float("inf"), float("nan"), -1, 999):
        tampered = deepcopy(result)
        tampered["computed_krw_per_t"] = invalid
        assert any("computed_krw_per_t" in issue for issue in validate_evidence(tampered))
    result["amount_basis"] = "executed_amount"
    assert any("불일치" in issue for issue in validate_evidence(result))


def test_csv_alone_cannot_recreate_validated_evidence(contract, throughput):
    complete = create_cost_candidate(contract, throughput, {"status": "validated", "reviewed_by": "검토자"})
    csv_row = {field: complete[field] for field in CANDIDATE_FIELDS}
    issues = validate_evidence(csv_row)
    assert any("명시적인 검토" in issue for issue in issues)
    assert any("대조 자료 미입력" in issue for issue in issues)


def test_source_period_not_replaced_when_only_query_reference_period_matches(contract, throughput):
    for record in (contract, throughput):
        record.pop("service_period")
        record["reference_period"] = "2024-01-01/2024-12-31"
    result = create_cost_candidate(contract, throughput)
    assert result["computed_krw_per_t"] is None
    assert result["validation_status"] == "candidate"


def test_review_rejection_clears_ratio(contract, throughput):
    result = create_cost_candidate(contract, throughput, {"status": "rejected", "review_note": "별도 운송 단가와 중복"})
    assert result["validation_status"] == "rejected"
    assert result["computed_krw_per_t"] is None


def test_boolean_year_and_approval_are_rejected(contract, throughput):
    contract["price_year"] = True
    with pytest.raises(ValueError, match="price_year"):
        create_cost_candidate(contract, throughput)
    contract["price_year"] = 2024
    with pytest.raises(ValueError, match="explicit_approval"):
        create_cost_candidate(contract, throughput, {"explicit_approval": "true"})


def test_validator_reports_wrong_status_type_without_crashing(contract, throughput):
    result = create_cost_candidate(contract, throughput)
    result["validation_status"] = []
    assert any("validation_status" in issue for issue in validate_evidence(result))


def test_unknown_placeholder_is_not_an_external_reviewer(contract, throughput):
    result = create_cost_candidate(contract, throughput)
    result.update(validation_status="validated", reviewed_by="미확인")
    assert any("명시적인 검토" in issue for issue in validate_evidence(result))


def test_nullable_contract_id_uses_unified_identifier():
    result = create_cost_candidate({"contract_id": None, "unified_contract_id": "UNIFIED-1"})
    assert result["contract_id"] == "UNIFIED-1"


def test_modified_contract_identity_cannot_pass_audit(contract, throughput):
    result = create_cost_candidate(contract, throughput)
    result["contract_id"] = "OTHER-CONTRACT"
    assert any("contract_id" in issue for issue in validate_evidence(result))
