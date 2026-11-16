"""비용 근거 후보의 범위와 검토 이력을 검증한다.

이 기준은 사용자 모형의 비용 비교 정책이며 법령의 원가 기준 해석이 아니다.
원자료의 출처 등급과 모형에 적용할 수 있는 비용 근거의 검증 상태를 구분한다.
"""
from collections.abc import Mapping
from math import isclose, isfinite
from urllib.parse import urlsplit


CANDIDATE_FIELDS = (
    "candidate_id", "source_id", "source_url", "reference_year", "price_year",
    "geography", "scope", "process_stage", "material_type", "contract_id",
    "amount_krw", "amount_basis", "throughput_t", "throughput_basis",
    "computed_krw_per_t", "includes_labor", "includes_transport",
    "includes_disposal", "includes_capital", "includes_transfer", "overlap_risk",
    "evidence_grade", "validation_status", "review_note",
)
CSV_FIELDS = CANDIDATE_FIELDS
INCLUSION_FIELDS = (
    "includes_labor", "includes_transport", "includes_disposal",
    "includes_capital", "includes_transfer",
)
MATCH_FIELDS = (
    "service_period", "reference_year", "geography", "scope",
    "process_stage", "material_type",
)
STATUSES = frozenset({"candidate", "proxy", "validated", "rejected"})


def _missing(value):
    return value is None or (isinstance(value, str) and value.strip().lower() in ("", "미확인", "자료 미입력", "미입력", "unknown", "null", "none"))


def _finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return isfinite(value)
    except (OverflowError, TypeError):
        return False


def _text_issue(field, value):
    if _missing(value):
        return f"{field}: 자료 미입력"
    if not isinstance(value, str):
        return f"{field}: 문자열이어야 합니다."
    return None


def _source_issues(record, label):
    issues = []
    for field in ("source_id", "source_url"):
        value = record.get(field)
        issue = _text_issue(f"{label}.{field}", value)
        if issue:
            issues.append(issue)
        elif field == "source_url":
            try:
                parsed = urlsplit(value)
                valid = parsed.scheme in ("http", "https") and bool(parsed.netloc)
            except ValueError:
                valid = False
            if not valid:
                issues.append(f"{label}.source_url: HTTP(S) 출처 URL이 필요합니다.")
    return issues


def _metadata_issues(candidate):
    """단가 계산 전에 충족되어야 하는 항목만 반환한다."""
    issues = []
    for field in (
        "candidate_id", "geography", "scope", "process_stage", "material_type",
        "contract_id", "amount_basis", "throughput_basis",
    ):
        issue = _text_issue(field, candidate.get(field))
        if issue:
            issues.append(issue)
    issues.extend(_source_issues(candidate, "candidate"))
    for field in ("reference_year", "price_year"):
        value = candidate.get(field)
        if value is None:
            issues.append(f"{field}: 자료 미입력")
        elif isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 9999:
            issues.append(f"{field}: 명시적인 정수 연도가 필요합니다.")
    for field, positive in (("amount_krw", False), ("throughput_t", True)):
        value = candidate.get(field)
        if value is None:
            issues.append(f"{field}: 자료 미입력")
        elif not _finite_number(value) or value < 0 or (positive and value == 0):
            bound = "0보다 큰" if positive else "0 이상의"
            issues.append(f"{field}: {bound} 유한한 숫자가 필요합니다(참/거짓 제외).")
    for field in (*INCLUSION_FIELDS, "overlap_risk"):
        value = candidate.get(field)
        if value is None:
            issues.append(f"{field}: 자료 미입력; 미확인을 거짓으로 대체할 수 없습니다.")
        elif not isinstance(value, bool):
            issues.append(f"{field}: 참/거짓이어야 합니다.")
    if candidate.get("includes_transfer") is True:
        issues.append("includes_transfer: 이전지출이 포함되어 실물비용 단가로 사용할 수 없습니다.")
    if candidate.get("overlap_risk") is True:
        issues.append("overlap_risk: 비용 중복 위험을 해소해야 합니다.")
    if not _missing(candidate.get("duplicate_of")):
        issues.append("duplicate_of: 동일 근거의 중복 후보입니다.")

    evidence = {}
    for label in ("contract_evidence", "throughput_evidence"):
        record = candidate.get(label)
        if not isinstance(record, Mapping):
            issues.append(f"{label}: 기간·범위·출처 대조 자료 미입력")
            continue
        evidence[label] = record
        issues.extend(_source_issues(record, label))
        for field in MATCH_FIELDS:
            value = record.get(field)
            if field == "reference_year":
                if value is None:
                    issues.append(f"{label}.{field}: 자료 미입력")
                elif isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 9999:
                    issues.append(f"{label}.{field}: 명시적인 정수 연도가 필요합니다.")
            else:
                issue = _text_issue(f"{label}.{field}", value)
                if issue:
                    issues.append(issue)
    contract = evidence.get("contract_evidence")
    throughput = evidence.get("throughput_evidence")
    if contract is not None:
        for field in (*MATCH_FIELDS, "source_id", "source_url", "contract_id", "amount_krw", "amount_basis", "price_year", *INCLUSION_FIELDS):
            # service_period is audit metadata beyond the generic CSV columns.
            if candidate.get(field) != contract.get(field):
                issues.append(f"contract_evidence.{field}: 후보 값과 불일치합니다.")
    if throughput is not None:
        for field in ("throughput_t", "throughput_basis"):
            if candidate.get(field) != throughput.get(field):
                issues.append(f"throughput_evidence.{field}: 후보 값과 불일치합니다.")
    if contract is not None and throughput is not None:
        for field in MATCH_FIELDS:
            if not _missing(contract.get(field)) and not _missing(throughput.get(field)):
                if contract[field] != throughput[field]:
                    issues.append(f"{field}: 계약금액과 처리량의 대상이 불일치합니다.")
        contract_id = throughput.get("contract_id")
        if not _missing(contract_id) and contract_id != candidate.get("contract_id"):
            issues.append("contract_id: 처리량이 다른 계약의 자료입니다.")
    return list(dict.fromkeys(issues))


def has_explicit_review(candidate):
    """검토자 표시 또는 검토 의견과 명시 승인 모두를 요구한다."""
    reviewer = candidate.get("reviewed_by")
    note = candidate.get("review_note")
    return (
        isinstance(reviewer, str) and not _missing(reviewer)
    ) or (
        isinstance(note, str) and not _missing(note)
        and candidate.get("explicit_approval") is True
    )


def validate_evidence(candidate):
    """후보를 변경하지 않고 미입력·불일치·검토 오류를 반환한다.

    빈 목록은 범위 확인의 통과를 의미한다. 모델 입력 적용 권한은 부여하지 않는다.
    일반 CSV 열 외의 두 evidence 자료도 보존해야 검증을 재현할 수 있다.
    """
    if not isinstance(candidate, Mapping):
        return ["candidate: 객체(dict)가 필요합니다."]
    metadata_issues = _metadata_issues(candidate)
    issues = list(metadata_issues)
    computed = candidate.get("computed_krw_per_t")
    if computed is not None:
        if not _finite_number(computed) or computed < 0:
            issues.append("computed_krw_per_t: 0 이상의 유한한 숫자가 필요합니다(참/거짓 제외).")
        elif metadata_issues:
            issues.append("computed_krw_per_t: 기간·범위·출처·포함항목이 확인되지 않아 단가를 산출할 수 없습니다.")
        else:
            try:
                expected = candidate["amount_krw"] / candidate["throughput_t"]
            except OverflowError:
                expected = float("inf")
            if not _finite_number(expected) or not isclose(computed, expected, rel_tol=1e-12, abs_tol=1e-12):
                issues.append("computed_krw_per_t: 금액/처리량과 불일치하거나 유한하지 않습니다.")
    status = candidate.get("validation_status")
    if not isinstance(status, str) or status not in STATUSES:
        issues.append("validation_status: candidate/proxy/validated/rejected 중 하나여야 합니다.")
    if status in ("candidate", "rejected") and computed is not None:
        issues.append("computed_krw_per_t: candidate/rejected에는 산출 단가를 부여할 수 없습니다.")
    if status in ("proxy", "validated") and computed is None:
        issues.append("computed_krw_per_t: proxy/validated에는 확인 가능한 단가가 필요합니다.")
    if status == "validated" and not has_explicit_review(candidate):
        issues.append("validation_status: validated에는 외부의 명시적인 검토가 필요합니다.")
    if candidate.get("explicit_approval") is not None and not isinstance(candidate["explicit_approval"], bool):
        issues.append("explicit_approval: 참/거짓이어야 합니다.")
    for field in ("review_note", "reviewed_by"):
        value = candidate.get(field)
        if value is not None and not isinstance(value, str):
            issues.append(f"{field}: 문자열이어야 합니다.")
    return list(dict.fromkeys(issues))


def validate_candidate_set(candidates):
    """동일 후보·계약을 합산하지 않도록 중복을 보고한다(자동 합산 없음)."""
    issues = []
    seen_ids = set()
    seen_contracts = set()
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            issues.append(f"row {index}: 객체(dict)가 필요합니다.")
            continue
        candidate_id = candidate.get("candidate_id")
        if isinstance(candidate_id, str) and candidate_id:
            if candidate_id in seen_ids:
                issues.append(f"row {index}: candidate_id 중복: {candidate_id}")
            seen_ids.add(candidate_id)
        # 같은 계약의 서로 다른 금액기준도 동시에 합산하지 않는다.
        contract_id = candidate.get("contract_id")
        if isinstance(contract_id, str) and contract_id:
            key = tuple(candidate.get(field) for field in (
                "contract_id", "service_period", "geography", "scope", "process_stage", "material_type",
            ))
            try:
                if key in seen_contracts:
                    issues.append(f"row {index}: 동일 계약·기간·범위 중복: {contract_id}")
                seen_contracts.add(key)
            except TypeError:
                issues.append(f"row {index}: 계약 중복 검사 필드는 단일 값이어야 합니다.")
    return issues

