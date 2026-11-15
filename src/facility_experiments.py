"""설비 대안의 수율·예산·용량을 명시적으로 바꾸는 조건부 실험.

comparison_cost는 수거·선별 예산과 추가 투자비 연금액의 합이다.
가계·재처리·별도 처분비가 없어 총사회적비용이나 확정 경제성으로 해석하지 않는다.
기존 model.py의 평가식과 기본 명령 동작은 변경하지 않는다.
"""
from collections.abc import Mapping
from copy import deepcopy

import pandas as pd

from .model import best, evaluate, number


COST_SCOPE = "알려진 수거·선별 예산+추가 투자 연금액(총사회적비용 아님)"


def copy_with_alternatives(config, alternatives=None):
    """원본을 보존하며 완전한 시나리오 사전을 추가한 실험 설정을 반환한다."""
    sample = deepcopy(config)
    if alternatives is not None:
        sample["scenarios"].extend(deepcopy(list(alternatives)))
    ids = [scenario["id"] for scenario in sample["scenarios"]]
    if len(set(ids)) != len(ids) or ids.count("A") != 1:
        raise ValueError("기준선 A가 하나이고 시나리오 식별자가 중복되지 않아야 합니다.")
    return sample


def evaluate_facility(config, scenario, processing_yield=None):
    """별도 수율로 한 대안을 평가한다. 설정과 시나리오는 변경하지 않는다.

    우선순위는 명시 인수, scenario.processing_yield, common.processing_yield다.
    수율은 관측 선별량 이후의 최종 재처리 수율이며 선별률과 구분한다.
    """
    sample = deepcopy(config)
    candidate = deepcopy(scenario)
    if processing_yield is not None:
        sample["common"]["processing_yield"] = number(
            processing_yield, "최종 재처리 수율 가정", 1
        )
    elif "processing_yield" in candidate:
        sample["common"]["processing_yield"] = number(
            candidate["processing_yield"], "대안별 최종 재처리 수율 가정", 1
        )
    return evaluate(sample, candidate)


def _yield_overrides(value, scenario_ids):
    if value is None:
        return {}
    alternative_ids = set(scenario_ids) - {"A"}
    if isinstance(value, Mapping):
        overrides = dict(value)
        if "A" in overrides:
            raise ValueError("기준선 A의 수율은 대안 수율 실험에서 변경할 수 없습니다.")
        if set(overrides) - alternative_ids:
            raise ValueError("수율 지정에 존재하지 않는 대안 식별자가 있습니다.")
        for assumed_yield in overrides.values():
            number(assumed_yield, "대안 최종 재처리 수율 가정", 1)
        return overrides
    assumed_yield = number(value, "대안 최종 재처리 수율 가정", 1)
    return {scenario_id: assumed_yield for scenario_id in alternative_ids}


def compare_facilities(
    config,
    target=None,
    annual_budget_cap=None,
    alternatives=None,
    alternative_processing_yield=None,
    require_known_capacity=False,
):
    """기준선 재생원료율 하한과 예산·용량 제약을 적용한 비교표를 반환한다.

    alternative_processing_yield는 A를 제외한 모든 대안에 쓸 숫자 또는
    대안 ID별 사전이다. A의 수율과 하한은 원래 설정에서 고정된다.
    예산 상한의 단위는 KRW/year, scenario.capacity_t는 t/year이다.
    용량 미확인은 기본적으로 조건부 후보에 남되 검증 완료로 표시하지 않는다.
    require_known_capacity=True이면 용량 미확인 후보도 제외한다.
    """
    if target is not None:
        number(target, "목표비율", 1)
    if annual_budget_cap is not None:
        number(annual_budget_cap, "연간 비교비용 상한")
    if not isinstance(require_known_capacity, bool):
        raise ValueError("require_known_capacity는 참 또는 거짓이어야 합니다.")
    sample = copy_with_alternatives(config, alternatives)
    overrides = _yield_overrides(
        alternative_processing_yield, [scenario["id"] for scenario in sample["scenarios"]]
    )
    records = []
    for scenario in sample["scenarios"]:
        result, _ = evaluate_facility(sample, scenario, overrides.get(scenario["id"]))
        records.append(result)
    table = pd.DataFrame(records)
    row_a = table.loc[table.id == "A"].iloc[0]
    floor = row_a.final_rate if target is None else max(row_a.final_rate, target)
    table["baseline_final_rate"] = row_a.final_rate
    table["requested_target"] = 0.0 if target is None else target
    table["effective_target"] = floor
    table["annual_budget_cap"] = annual_budget_cap
    table["comparison_cost_scope"] = COST_SCOPE
    table["recycling_ok"] = table.final_rate + 1e-12 >= floor
    table["budget_ok"] = (
        True if annual_budget_cap is None else table.comparison_cost <= annual_budget_cap
    )
    table["capacity_verified"] = table.capacity_status != "미확인"
    table["capacity_ok"] = table.capacity_status != "초과"
    if require_known_capacity:
        table["capacity_ok"] &= table.capacity_verified
    table["feasible"] = table.recycling_ok & table.budget_ok & table.capacity_ok
    table["verified_feasible"] = table.feasible & table.capacity_verified
    table["savings_vs_a"] = row_a.comparison_cost - table.comparison_cost

    def reasons(row):
        rejected = []
        if not row.recycling_ok:
            rejected.append("재생원료율 하한 미달")
        if not row.budget_ok:
            rejected.append("연간 비교비용 상한 초과")
        if row.capacity_status == "초과":
            rejected.append("연간 처리용량 초과")
        elif require_known_capacity and not row.capacity_verified:
            rejected.append("연간 처리용량 미확인")
        return "; ".join(rejected)

    table["rejection_reasons"] = table.apply(reasons, axis=1)
    table["verification_note"] = table.capacity_status.map(
        {"미확인": "용량 미확인: 조건부 결과", "충족": "명시 용량 충족", "초과": "명시 용량 초과"}
    )
    # 비용 일부가 결측이고 수율은 가정이므로 용량이 알려져도 전체 검증은 아니다.
    table["fully_verified"] = False
    return table


def minimum_cost_curve(
    config,
    targets,
    annual_budget_cap=None,
    alternatives=None,
    alternative_processing_yield=None,
    require_known_capacity=False,
):
    """목표 재생원료율별 조건부 최소 비교비용을 반환한다.

    후보가 없으면 feasible=False, selected_id=None, 최소비용은 결측이다.
    곡선은 주어진 이산 대안의 하한 외피이며 연속 설비 최적화가 아니다.
    """
    columns = [
        "requested_target", "effective_target", "baseline_final_rate",
        "selected_id", "selected_name", "minimum_comparison_cost",
        "savings_vs_a", "feasible", "feasible_count", "capacity_status",
        "verified_feasible", "fully_verified", "comparison_cost_scope",
    ]
    # 생성자로 전달된 대안도 모든 목표에 동일하게 적용한다.
    sample = copy_with_alternatives(config, alternatives)
    rows = []
    for target in targets:
        table = compare_facilities(
            sample,
            target=target,
            annual_budget_cap=annual_budget_cap,
            alternative_processing_yield=alternative_processing_yield,
            require_known_capacity=require_known_capacity,
        )
        selected_id = best(table)
        selected = None if selected_id is None else table.loc[table.id == selected_id].iloc[0]
        rows.append({
            "requested_target": table.requested_target.iloc[0],
            "effective_target": table.effective_target.iloc[0],
            "baseline_final_rate": table.baseline_final_rate.iloc[0],
            "selected_id": selected_id,
            "selected_name": None if selected is None else selected["name"],
            "minimum_comparison_cost": None if selected is None else selected.comparison_cost,
            "savings_vs_a": None if selected is None else selected.savings_vs_a,
            "feasible": selected is not None,
            "feasible_count": int(table.feasible.sum()),
            "capacity_status": None if selected is None else selected.capacity_status,
            "verified_feasible": False if selected is None else bool(selected.verified_feasible),
            "fully_verified": False,
            "comparison_cost_scope": COST_SCOPE,
        })
    curve = pd.DataFrame(rows, columns=columns)
    for column in ("selected_id", "selected_name", "capacity_status"):
        curve[column] = pd.Series([row[column] for row in rows], dtype=object)
    return curve
