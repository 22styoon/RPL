"""Match reviewed programs to the operating metrics reported for their scope."""

from dataclasses import dataclass
from datetime import date
from math import isfinite
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import yaml


MATCH_FIELDS = (
    "policy_id",
    "geography_id",
    "population_id",
    "material_id",
    "channel_id",
    "period_start",
    "period_end",
    "period_type",
)
POLICY_FIELDS = (
    *MATCH_FIELDS,
    "policy_name",
    "geography",
    "coverage",
    "material",
    "collection_channel",
    "operating_entity",
    "operation_source_url",
    "operation_source_locator",
    "reviewed_on",
)
PERFORMANCE_FIELDS = (
    "cups_sold",
    "cups_returned",
    "cup_count_reported_unit",
    "cup_return_rate_percent",
    "performance_source_url",
    "performance_source_locator",
)
EXCLUSION_FIELDS = (*MATCH_FIELDS, "policy_name", "reason", "description")


@dataclass(frozen=True)
class OperatingPolicyEvidence:
    policies: pd.DataFrame
    performance: pd.DataFrame
    household_join_exclusions: pd.DataFrame


def _required_text(record, field):
    value = record.get(field)
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"운영정책 근거의 {field} 값은 비어 있지 않은 문자열이어야 합니다.")
    return value


def _source(record, prefix):
    field = f"{prefix}_source_url"
    url = urlparse(_required_text(record, field))
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError(f"{field}에 공개 HTTPS 출처를 지정하세요.")
    _required_text(record, f"{prefix}_source_locator")


def _case_key(record, reference_year):
    key = tuple(_required_text(record, field) for field in MATCH_FIELDS)
    start = date.fromisoformat(record["period_start"])
    end = date.fromisoformat(record["period_end"])
    if (str(start) != record["period_start"] or str(end) != record["period_end"]
            or start > end or not start.year <= reference_year <= end.year):
        raise ValueError("운영정책 근거에 기준연도를 포함하는 관측기간을 지정하세요.")
    return key


def _check_cup_metrics(record):
    sold = record.get("cups_sold")
    returned = record.get("cups_returned")
    count_unit = record.get("cup_count_reported_unit")
    rate = record.get("cup_return_rate_percent")
    if (type(sold) is not int or type(returned) is not int or type(count_unit) is not int
            or count_unit <= 0 or not 0 <= returned <= sold or sold == 0
            or sold % count_unit or returned % count_unit):
        raise ValueError("컵 판매·반환 수량의 범위와 원자료 집계 단위를 확인하세요.")
    if type(rate) not in (int, float) or not isfinite(rate) or not 0 <= rate <= 100:
        raise ValueError("컵 반환율은 0~100의 유한한 값이어야 합니다.")


def load_operating_policy_evidence(path: Path) -> OperatingPolicyEvidence:
    """Load manually reviewed sources and match exact program observation keys.

    Cup counts retain the reporting precision in cup_count_reported_unit. The
    published return rate is retained independently of those rounded counts.
    """
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("reference_year") != 2024:
        raise ValueError("운영정책 근거의 기준연도는 2024년이어야 합니다.")
    reference_year = document["reference_year"]
    policies = {}
    exclusions = []
    for record in document["policies"]:
        key = _case_key(record, reference_year)
        if key in policies:
            raise ValueError(f"운영정책 근거의 중복 키: {key}")
        policy = {field: _required_text(record, field) for field in POLICY_FIELDS}
        _source(record, "operation")
        date.fromisoformat(policy["reviewed_on"])
        policies[key] = policy
        reasons = record.get("household_join_exclusions")
        if not isinstance(reasons, dict) or not reasons:
            raise ValueError(f"시군구 생활폐기물 통계 결합 제외 근거가 없습니다: {key}")
        for reason in reasons:
            exclusions.append({
                **{field: policy[field] for field in MATCH_FIELDS},
                "policy_name": policy["policy_name"],
                "reason": reason,
                "description": _required_text(reasons, reason),
            })

    performance = {}
    for record in document["performance"]:
        key = _case_key(record, reference_year)
        if key in performance or key not in policies:
            raise ValueError(f"성과 근거의 정책 키가 중복되었거나 일치하지 않습니다: {key}")
        _source(record, "performance")
        _check_cup_metrics(record)
        performance[key] = {**policies[key], **{field: record[field] for field in PERFORMANCE_FIELDS}}
    if performance.keys() != policies.keys():
        raise ValueError("운영정책 근거 중 같은 범위와 기간의 성과가 빠진 기록이 있습니다.")

    return OperatingPolicyEvidence(
        policies=pd.DataFrame(policies.values(), columns=POLICY_FIELDS),
        performance=pd.DataFrame(performance.values(), columns=(*POLICY_FIELDS, *PERFORMANCE_FIELDS)),
        household_join_exclusions=pd.DataFrame(exclusions, columns=EXCLUSION_FIELDS),
    )
