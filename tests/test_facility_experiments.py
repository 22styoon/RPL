"""설비 실험의 기준선 고정, 제약 판정과 이산 최소비용곡선을 검증한다."""
from copy import deepcopy

import pandas as pd
import pytest

from src.facility_experiments import (
    COST_SCOPE,
    compare_facilities,
    copy_with_alternatives,
    evaluate_facility,
    minimum_cost_curve,
)
from src.model import best, compare, load_config


@pytest.fixture
def config():
    return load_config()


def alternative(config, **changes):
    scenario = deepcopy(config["scenarios"][0])
    scenario.update(
        id="E", name="추가 설비 대안", sorting_target=0.8,
        collection_budget_multiplier=0.8, sorting_budget_multiplier=0.8,
        capacity_t=13195, processing_yield=0.9,
    )
    scenario.update(changes)
    return scenario


def test_alternative_copy_and_yield_override_do_not_mutate(config):
    original = deepcopy(config)
    added = alternative(config)
    added_original = deepcopy(added)
    sample = copy_with_alternatives(config, [added])
    row, flows = evaluate_facility(sample, added)
    assert row["processing_yield"] == 0.9
    assert row["final_rate"] == pytest.approx(0.72)
    assert row["recycled_t"] == pytest.approx(13195 * 0.8 * 0.9)
    assert (flows.handled - flows.recycled - flows.sorting_loss - flows.processing_loss).abs().max() < 1e-8
    assert config == original
    assert added == added_original
    sample["scenarios"][-1]["name"] = "분리 복사"
    assert added["name"] == "추가 설비 대안"
    explicit, _ = evaluate_facility(config, added, processing_yield=0.7)
    assert explicit["processing_yield"] == 0.7


def test_default_comparison_preserves_existing_behavior(config):
    old = compare(config)
    new = compare_facilities(config)
    for column in ("id", "final_rate", "comparison_cost", "feasible", "savings_vs_a"):
        pd.testing.assert_series_equal(old[column], new[column])
    assert best(old) == best(new)
    assert not new.fully_verified.any()
    assert new.comparison_cost_scope.eq(COST_SCOPE).all()


def test_low_alternative_yield_cannot_lower_baseline_floor(config):
    original = deepcopy(config)
    initial = compare_facilities(config).set_index("id")
    changed = compare_facilities(config, alternative_processing_yield=0.1).set_index("id")
    assert changed.loc["A", "processing_yield"] == 0.85
    assert changed.loc["A", "final_rate"] == initial.loc["A", "final_rate"]
    assert changed.effective_target.eq(initial.loc["A", "final_rate"]).all()
    assert changed.loc[["B", "C", "D"], "processing_yield"].eq(0.1).all()
    assert not changed.loc[["B", "C", "D"], "feasible"].any()
    assert config == original


def test_scenario_and_id_specific_yields(config):
    result = compare_facilities(
        config, alternatives=[alternative(config)],
        alternative_processing_yield={"B": 0.8},
    ).set_index("id")
    assert result.loc["A", "processing_yield"] == 0.85
    assert result.loc["B", "processing_yield"] == 0.8
    assert result.loc["C", "processing_yield"] == 0.85
    assert result.loc["E", "processing_yield"] == 0.9
    with pytest.raises(ValueError, match="기준선 A"):
        compare_facilities(config, alternative_processing_yield={"A": 0.1})


def test_budget_capacity_and_rejection_reasons(config):
    added = alternative(config, capacity_t=13194)
    table = compare_facilities(
        config, target=0.8, annual_budget_cap=0, alternatives=[added]
    ).set_index("id")
    assert not table.feasible.any()
    assert table.loc["E", "rejection_reasons"] == (
        "재생원료율 하한 미달; 연간 비교비용 상한 초과; 연간 처리용량 초과"
    )
    boundary = compare_facilities(config, alternatives=[alternative(config)]).set_index("id")
    annual_cost = boundary.loc["E", "comparison_cost"]
    bounded = compare_facilities(
        config, annual_budget_cap=float(annual_cost), alternatives=[alternative(config)]
    ).set_index("id")
    assert bool(bounded.loc["E", "budget_ok"])
    assert bool(bounded.loc["E", "verified_feasible"])
    assert bounded.loc["E", "capacity_status"] == "충족"
    assert not bool(bounded.loc["E", "fully_verified"])


def test_unknown_capacity_is_only_conditional(config):
    default = compare_facilities(config)
    assert default.capacity_status.eq("미확인").all()
    assert default.feasible.any()
    assert not default.verified_feasible.any()
    assert default.verification_note.str.contains("조건부").all()
    strict = compare_facilities(config, require_known_capacity=True)
    assert not strict.feasible.any()
    assert strict.rejection_reasons.str.contains("용량 미확인").all()
    assert best(strict) is None


def test_cost_curve_matches_direct_comparisons_and_no_solution(config):
    targets = [0, 0.53, 0.55, 1]
    curve = minimum_cost_curve(config, targets)
    assert curve.selected_id.tolist() == ["A", "B", "D", None]
    for row in curve.itertuples():
        direct = compare_facilities(config, row.requested_target)
        assert row.selected_id == best(direct)
        if row.feasible:
            assert row.minimum_comparison_cost == direct.loc[direct.feasible, "comparison_cost"].min()
        else:
            assert pd.isna(row.minimum_comparison_cost)
            assert row.feasible_count == 0
    costs = curve.loc[curve.feasible, "minimum_comparison_cost"]
    assert costs.is_monotonic_increasing
    assert minimum_cost_curve(config, []).empty


def test_curve_reuses_generator_alternatives(config):
    additions = (scenario for scenario in [alternative(config)])
    curve = minimum_cost_curve(config, [0.6, 0.7], alternatives=additions)
    assert curve.selected_id.tolist() == ["E", "E"]


@pytest.mark.parametrize("kwargs", [
    {"target": -0.1}, {"target": 1.1}, {"target": True},
    {"annual_budget_cap": -1}, {"annual_budget_cap": float("nan")},
    {"alternative_processing_yield": 1.1},
    {"alternative_processing_yield": {"B": None}},
    {"alternative_processing_yield": {"missing": 0.9}},
    {"require_known_capacity": "yes"},
])
def test_invalid_constraints_are_rejected(config, kwargs):
    with pytest.raises(ValueError):
        compare_facilities(config, **kwargs)


def test_duplicate_alternatives_are_rejected(config):
    with pytest.raises(ValueError, match="중복"):
        copy_with_alternatives(config, [alternative(config, id="A")])
