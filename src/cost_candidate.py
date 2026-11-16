"""정규화된 공공 계약·처리량을 비용 근거 후보로 연결한다.

API 등록일·공고일에서 서비스 연도나 가격 연도를 추정하지 않는다.
확인되지 않은 금액·처리량·포함항목은 None으로 보존한다.
현재 정책 모형의 단가 설정이나 모델 입력을 변경하는 기능은 제공하지 않는다.
"""
from collections.abc import Mapping
from copy import deepcopy
import hashlib
import json

from src.evidence_validation import (
    CANDIDATE_FIELDS, CSV_FIELDS, INCLUSION_FIELDS, MATCH_FIELDS, STATUSES,
    _finite_number, _metadata_issues, has_explicit_review, validate_evidence,
)


_ALIASES = {
    "scope": ("scope", "waste_scope"),
    "material_type": ("material_type", "material"),
    "amount_krw": ("amount_krw", "contract_amount_krw"),
    "contract_id": ("contract_id", "unified_contract_id", "decision_contract_id"),
}
_TEXT_FIELDS = (
    "candidate_id", "source_id", "source_url", "geography", "scope",
    "process_stage", "material_type", "contract_id", "amount_basis",
    "throughput_basis", "service_period", "duplicate_of", "review_note",
    "reviewed_by", "period_start", "period_end", "service_start", "service_end",
)


def _get(record, field):
    for alias in _ALIASES.get(field, (field,)):
        if alias in record and record[alias] is not None:
            return record[alias]
    return None


def _text(value):
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.lower() in ("", "미확인", "자료 미입력", "미입력", "unknown", "null", "none"):
            return None
        return stripped
    return value


def _typed_record(record, label):
    if not isinstance(record, Mapping):
        raise ValueError(f"{label}: 객체(dict)가 필요합니다.")
    result = deepcopy(dict(record))
    for field in _TEXT_FIELDS:
        value = _get(record, field)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{label}.{field}: 문자열이어야 합니다.")
        result[field] = _text(value)
    for field in ("reference_year", "price_year"):
        value = record.get(field)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 9999):
            raise ValueError(f"{label}.{field}: 명시적인 정수 연도가 필요합니다.")
        result[field] = value
    for field in ("amount_krw", "throughput_t"):
        value = _get(record, field)
        if value is not None and (not _finite_number(value) or value < 0 or (field == "throughput_t" and value == 0)):
            raise ValueError(f"{label}.{field}: 금액은 0 이상, 처리량은 0보다 큰 유한한 숫자가 필요합니다(참/거짓 제외).")
        result[field] = value
    for field in (*INCLUSION_FIELDS, "overlap_risk", "explicit_approval"):
        value = record.get(field)
        if value is not None and not isinstance(value, bool):
            raise ValueError(f"{label}.{field}: 참/거짓이어야 합니다.")
        result[field] = value
    if result["service_period"] is None:
        start = result.get("period_start") or result.get("service_start")
        end = result.get("period_end") or result.get("service_end")
        if start is not None and end is not None:
            result["service_period"] = f"{start}/{end}"
    return result


def _evidence(record):
    if record is None:
        return None
    fields = (
        "source_id", "source_url", *MATCH_FIELDS, "contract_id", "price_year",
        "amount_krw", "amount_basis", "throughput_t", "throughput_basis", *INCLUSION_FIELDS,
    )
    return {field: deepcopy(record.get(field)) for field in fields}


def create_cost_candidate(contract, throughput=None, review=None):
    """단가 후보를 작성하며 호출자의 객체와 기존 모델 설정은 변경하지 않는다.

    contract와 throughput에는 각자의 source_id/source_url, service_period,
    reference_year, geography, scope, process_stage, material_type이 필요하다.
    contract에는 price_year, amount_krw, amount_basis, includes_* 다섯 항목과
    overlap_risk=False가, throughput에는 throughput_t와 throughput_basis가 필요하다.
    모든 범위가 일치한 후보만 proxy 단가를 갖는다. validated는 status 요청과
    reviewed_by 또는 review_note+explicit_approval=True가 있을 때만 부여한다.
    잘못된 자료형·비유한 수치·0 처리량은 ValueError, 미입력은 None으로 구분한다.
    """
    contract = _typed_record(contract, "contract")
    throughput = None if throughput is None else _typed_record(throughput, "throughput")
    raw_review = {} if review is None else review
    review = _typed_record(raw_review, "review")
    requested = raw_review.get("validation_status", raw_review.get("status"))
    if requested is not None and (not isinstance(requested, str) or requested not in STATUSES):
        raise ValueError("review.validation_status: candidate/proxy/validated/rejected 중 하나여야 합니다.")

    candidate = {field: deepcopy(contract.get(field)) for field in CANDIDATE_FIELDS}
    candidate.update(
        throughput_t=None if throughput is None else throughput.get("throughput_t"),
        throughput_basis=None if throughput is None else throughput.get("throughput_basis"),
        computed_krw_per_t=None,
        service_period=contract.get("service_period"),
        contract_evidence=_evidence(contract),
        throughput_evidence=_evidence(throughput),
        duplicate_of=contract.get("duplicate_of"),
        reviewed_by=review.get("reviewed_by"),
        explicit_approval=review.get("explicit_approval"),
        review_note=review.get("review_note") or contract.get("review_note"),
        evidence_grade="미확인",
        validation_status="candidate",
    )
    if candidate["candidate_id"] is None:
        identity = {field: contract.get(field) for field in (
            "source_id", "contract_id", "service_period", "geography", "scope",
            "process_stage", "material_type", "amount_basis",
        )}
        payload = json.dumps(identity, ensure_ascii=False, sort_keys=True, allow_nan=False)
        candidate["candidate_id"] = "cost-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]

    issues = _metadata_issues(candidate)
    rejected = (
        candidate.get("includes_transfer") is True
        or candidate.get("overlap_risk") is True
        or candidate.get("duplicate_of") is not None
        or any("불일치" in issue or "다른 계약" in issue for issue in issues)
        or requested == "rejected"
    )
    if rejected:
        candidate["validation_status"] = "rejected"
    elif not issues and requested != "candidate":
        try:
            computed = candidate["amount_krw"] / candidate["throughput_t"]
        except OverflowError:
            computed = float("inf")
        if _finite_number(computed):
            candidate.update(computed_krw_per_t=computed, validation_status="proxy", evidence_grade="C")
            if requested == "validated" and has_explicit_review(candidate):
                candidate.update(validation_status="validated", evidence_grade="B")
        else:
            issues.append("computed_krw_per_t: 계산 결과가 유한하지 않아 후보 단가를 산출할 수 없습니다.")
    issues.extend(validate_evidence(candidate))
    if requested == "validated" and not has_explicit_review(candidate):
        issues.append("validation_status: validated에는 외부의 명시적인 검토가 필요합니다.")
    if requested == "rejected" and not candidate.get("review_note"):
        issues.append("review_note: 검토에 따른 배제 사유 자료 미입력")
    candidate["validation_issues"] = list(dict.fromkeys(issues))
    return candidate


