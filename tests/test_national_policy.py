"""Regression checks using public KOSIS rows and explicitly hypothetical cost inputs."""
from copy import deepcopy
import hashlib
from io import BytesIO
import json
import zipfile

import pandas as pd
import pytest

from src import national_policy as policy


@pytest.fixture
def config():
    """Fresh actual-data configuration; no inferred regional costs."""
    sample = policy.load_policy_config()
    sample["region"] = "서울"
    return sample


@pytest.fixture
def priced_config(config):
    """Arbitrary test-only KRW/t values, never estimates of real costs."""
    config["costs"] = {
        "collection_per_t": 100.0,
        "material_processing_per_t": 20.0,
        "other_treatment_per_t": 15.0,
        "processing_residue_per_t": 10.0,
    }
    return config


def row_for(table, policy_id):
    return table.set_index("policy_id").loc[policy_id]


def scenario_for(config, scenario_id):
    return next(s for s in config["scenarios"] if s["id"] == scenario_id)


def test_baseline_uses_selected_regions_four_observed_materials(config):
    observed = pd.read_csv(policy.ROOT / "data/processed/kosis_materials_2024.csv")
    observed = observed.loc[observed.geography == "서울"].set_index("material")
    results, flows = policy.compare_policies(config)
    baseline = flows.loc[flows.policy_id == "A"].set_index("material")

    assert len(baseline) == 4
    assert set(baseline.index) == set(policy.MATERIALS)
    assert set(results.geography) == {"서울"}
    for material in policy.MATERIALS:
        actual = observed.loc[material]
        modeled = baseline.loc[material]
        assert modeled.generated_t == pytest.approx(actual.generated_t)
        assert modeled.observed_material_treatment_t == pytest.approx(actual.material_recycling_t)
        assert modeled.modeled_material_treatment_t == pytest.approx(actual.material_recycling_t)
        assert modeled.final_t == pytest.approx(
            actual.material_recycling_t * config["baseline_yields"][material]
        )
        assert modeled.final_t < modeled.observed_material_treatment_t
    a = row_for(results, "A")
    assert a.generated_t == pytest.approx(observed.generated_t.sum())
    assert a.material_treatment_t == pytest.approx(observed.material_recycling_t.sum())
    assert a.final_t == pytest.approx(baseline.final_t.sum())
    assert a.final_rate == pytest.approx(a.final_t / a.generated_t)


@pytest.mark.parametrize("extreme_changes", [False, True])
def test_material_balance_and_nonnegative_flows_even_when_rates_clip(config, extreme_changes):
    if extreme_changes:
        scenario_for(config, "B").update(treatment_change_pp=-1.0, yield_change_pp=-1.0)
        scenario_for(config, "D").update(treatment_change_pp=1.0, yield_change_pp=1.0)
    results, flows = policy.compare_policies(config)
    for flow in flows.itertuples():
        assert flow.generated_t == pytest.approx(
            flow.final_t + flow.other_pathways_t + flow.processing_loss_t
        )
        assert 0 <= flow.final_t <= flow.modeled_material_treatment_t <= flow.generated_t
        assert 0 <= flow.assumed_yield <= 1
    for result in results.itertuples():
        subset = flows.loc[flows.policy_id == result.policy_id]
        assert result.final_t == pytest.approx(subset.final_t.sum())
        assert result.material_treatment_t == pytest.approx(
            subset.modeled_material_treatment_t.sum()
        )
    if extreme_changes:
        assert flows.loc[flows.policy_id.isin(["B", "D"]), "rate_clipped"].all()


def test_missing_all_four_costs_never_ranks_a_partial_sum(config):
    assert all(value is None for value in config["costs"].values())
    results, _ = policy.compare_policies(config)
    assert results.comparison_cost.isna().all()
    assert results.public_cost.isna().all()
    assert not results.costs_complete.any()
    assert (results.known_cost_subtotal == 0).all()
    assert policy.selected_policy(results) is None
    curve = policy.target_curve(config, [0, 0.5, 1])
    assert curve.minimum_cost.isna().all()
    assert curve.selected_id.isna().all()


@pytest.mark.parametrize("missing_price", list(policy.PRICE_LABELS))
def test_even_one_missing_treatment_price_blocks_ranking(priced_config, missing_price):
    priced_config["costs"][missing_price] = None
    results, _ = policy.compare_policies(priced_config)
    assert (results.known_cost_subtotal > 0).all()
    assert results.comparison_cost.isna().all()
    assert results.public_cost.isna().all()
    assert not results.costs_complete.any()
    assert policy.selected_policy(results) is None


def test_explicit_zero_prices_are_complete_and_rankable(config):
    config["costs"] = dict.fromkeys(policy.PRICE_LABELS, 0)
    results, _ = policy.compare_policies(config)
    assert results.costs_complete.all()
    assert results.comparison_cost.notna().all()
    assert (results.public_cost == 0).all()
    assert (results.comparison_cost == 0).all()
    assert policy.selected_policy(results) == "A"


@pytest.mark.parametrize("missing_field", ["households", "baseline_minutes_per_week"])
def test_selected_household_scope_requires_both_inputs(priced_config, missing_field):
    priced_config["economics"].update(
        include_household=True, households=100, baseline_minutes_per_week=5
    )
    priced_config["economics"][missing_field] = None
    results, _ = policy.compare_policies(priced_config)
    assert results.public_cost.notna().all()
    assert results.household_cost.isna().all()
    assert results.comparison_cost.isna().all()
    assert not results.costs_complete.any()
    assert policy.selected_policy(results) is None


def test_unselected_household_inputs_remain_missing_without_blocking_ranking(priced_config):
    results, _ = policy.compare_policies(priced_config)
    assert results.household_cost.isna().all()
    assert results.costs_complete.all()
    assert policy.selected_policy(results) is not None


@pytest.mark.parametrize("ceiling, expected_status", [(100, "충족"), (99, "초과")])
def test_budget_counts_public_cost_and_capital_but_excludes_households_and_producers(
    config, ceiling, expected_status
):
    config["costs"] = dict.fromkeys(policy.PRICE_LABELS, 0)
    config["economics"].update(
        discount_rate=0, life_years=12, include_household=True,
        households=10, baseline_minutes_per_week=60, time_value=100,
    )
    scenario_for(config, "B").update(capital=1200, producer_real_per_t=10)
    config["constraints"]["annual_public_budget"] = ceiling
    results, _ = policy.compare_policies(config)
    b = row_for(results, "B")
    assert b.annual_capital == pytest.approx(100)
    assert b.public_cost == pytest.approx(100)
    assert b.household_cost > 0
    assert b.producer_cost > 0
    assert b.comparison_cost == pytest.approx(
        b.public_cost + b.household_cost + b.producer_cost
    )
    assert b.comparison_cost > ceiling
    assert b.budget_status == expected_status
    assert bool(b.feasible) is (expected_status == "충족")


def test_budget_is_unevaluated_if_public_prices_are_missing(config):
    config["constraints"]["annual_public_budget"] = 10**20
    results, _ = policy.compare_policies(config)
    assert (results.budget_status == "미평가").all()
    assert not results.feasible.any()
    assert results.rejection_reasons.str.contains("공공지출 제약 미평가").all()


@pytest.mark.parametrize(
    "field, value",
    [
        ("treatment_change_pp", 0.01),
        ("yield_change_pp", -0.01),
        ("collection_factor", 0.9),
        ("processing_factor", 1.1),
        ("other_factor", 0.9),
        ("capital", 1),
        ("additional_capacity_t", 1),
        ("producer_real_per_t", 1),
        ("household_time_factor", 0.9),
    ],
)
def test_baseline_a_cannot_be_modified(config, field, value):
    scenario_for(config, "A")[field] = value
    with pytest.raises(ValueError, match="기준선 A"):
        policy.compare_policies(config)


def test_lower_alternative_yield_does_not_relax_baseline_floor(priced_config):
    initial, _ = policy.compare_policies(priced_config)
    baseline_rate = row_for(initial, "A").final_rate
    scenario_for(priced_config, "B").update(
        treatment_change_pp=0.0, yield_change_pp=-0.85
    )
    results, _ = policy.compare_policies(priced_config)
    assert row_for(results, "A").final_rate == pytest.approx(baseline_rate)
    assert all(value == pytest.approx(baseline_rate) for value in results.effective_target)
    assert row_for(results, "B").final_rate == pytest.approx(0)
    assert not row_for(results, "B").recycling_ok
    assert not row_for(results, "B").feasible


@pytest.mark.parametrize("strict", [False, True])
def test_unknown_capacity_is_explicit_and_strict_option_excludes_it(priced_config, strict):
    priced_config["constraints"]["require_known_capacity"] = strict
    results, _ = policy.compare_policies(priced_config)
    assert (results.capacity_status == "미확인").all()
    assert not results.fully_verified.any()
    if strict:
        assert not results.feasible.any()
        assert results.rejection_reasons.str.contains("처리 용량 미입력").all()
        assert policy.selected_policy(results) is None
    else:
        assert row_for(results, "A").feasible
        assert policy.selected_policy(results) is not None


def test_capacity_checks_material_treatment_input_and_excludes_excess(priced_config):
    initial, _ = policy.compare_policies(priced_config)
    baseline_treatment = row_for(initial, "A").material_treatment_t
    priced_config["constraints"]["material_capacity_t"] = baseline_treatment
    results, _ = policy.compare_policies(priced_config)
    assert row_for(results, "A").capacity_status == "충족"
    assert row_for(results, "A").generated_t > baseline_treatment
    assert row_for(results, "B").capacity_status == "초과"
    assert not row_for(results, "B").feasible
    scenario_for(priced_config, "B")["additional_capacity_t"] = (
        row_for(results, "B").material_treatment_t - baseline_treatment
    )
    expanded, _ = policy.compare_policies(priced_config)
    assert row_for(expanded, "B").capacity_status == "충족"


def test_adoption_scan_has_thirteen_candidates_and_interpolates_inputs(priced_config):
    priced_config["scan_adoption"] = True
    scenario_for(priced_config, "B")["capital"] = 1200
    results, flows = policy.compare_policies(priced_config)
    assert len(results) == 13
    assert results.policy_id.is_unique
    assert len(flows) == 13 * 4
    assert row_for(results, "A").adoption == 0
    for scenario_id in ["B", "C", "D"]:
        subset = results.loc[results.scenario_id == scenario_id]
        assert set(subset.adoption) == {0.25, 0.5, 0.75, 1.0}
    a = flows.loc[flows.policy_id == "A"].set_index("material")
    full = flows.loc[flows.policy_id == "B"].set_index("material")
    half = flows.loc[flows.policy_id == "B_50"].set_index("material")
    for material in policy.MATERIALS:
        expected_treatment = (
            a.loc[material].modeled_material_treatment_t
            + full.loc[material].modeled_material_treatment_t
        ) / 2
        expected_yield = (a.loc[material].assumed_yield + full.loc[material].assumed_yield) / 2
        assert half.loc[material].modeled_material_treatment_t == pytest.approx(expected_treatment)
        assert half.loc[material].assumed_yield == pytest.approx(expected_yield)
        assert half.loc[material].final_t == pytest.approx(expected_treatment * expected_yield)
    assert row_for(results, "B_50").collection_cost == pytest.approx(
        (row_for(results, "A").collection_cost + row_for(results, "B").collection_cost) / 2
    )
    assert row_for(results, "B_50").annual_capital == pytest.approx(
        row_for(results, "B").annual_capital / 2
    )


def test_target_curve_is_discrete_nested_and_non_decreasing(priced_config):
    priced_config["scan_adoption"] = True
    candidates, _ = policy.compare_policies(priced_config)
    targets = sorted({0.0, 0.25, *candidates.final_rate.tolist(), 1.0})
    curve = policy.target_curve(priced_config, targets)
    assert curve.requested_target.tolist() == targets
    assert curve.effective_target.is_monotonic_increasing
    assert curve.feasible_count.is_monotonic_decreasing
    assert curve.minimum_cost.dropna().is_monotonic_increasing
    assert pd.isna(curve.iloc[-1].minimum_cost)
    assert pd.isna(curve.iloc[-1].selected_id)
    assert curve.iloc[-1].feasible_count == 0
    finite_costs = set(candidates.comparison_cost)
    previous_ids = set(candidates.loc[candidates.feasible, "policy_id"])
    for point in curve.itertuples():
        eligible = candidates.loc[
            candidates.feasible & (candidates.final_rate + 1e-12 >= point.effective_target)
        ]
        eligible_ids = set(eligible.policy_id)
        assert eligible_ids <= previous_ids
        previous_ids = eligible_ids
        assert point.feasible_count == len(eligible)
        if eligible.empty:
            assert pd.isna(point.minimum_cost)
            assert pd.isna(point.selected_id)
        else:
            assert point.minimum_cost in finite_costs
            assert point.minimum_cost == pytest.approx(eligible.comparison_cost.min())
            assert point.selected_id in eligible_ids


def test_sensitivity_handles_effect_bounds_without_changing_callers_config(priced_config):
    scenario_for(priced_config, "B")["treatment_change_pp"] = -1
    scenario_for(priced_config, "D")["treatment_change_pp"] = 1
    original = deepcopy(priced_config)
    experiments = policy.sensitivity(priced_config)
    assert len(experiments) == 9
    assert experiments.parameter.nunique() == 3
    assert priced_config == original


def test_snapshot_and_zip_preserve_current_region_inputs_and_source_hash(priced_config):
    original = deepcopy(priced_config)
    results, flows = policy.compare_policies(priced_config)
    snapshot = policy.input_snapshot(priced_config)
    expected_hash = hashlib.sha256(
        (policy.ROOT / "data/processed/kosis_materials_2024.csv").read_bytes()
    ).hexdigest()
    assert snapshot["configuration"] == priced_config
    assert snapshot["source_sha256"] == expected_hash
    assert snapshot["source_file"] == "data/processed/kosis_materials_2024.csv"
    snapshot["configuration"]["region"] = "전국"
    assert priced_config["region"] == "서울"

    bundle = policy.export_bundle(priced_config, results, flows)
    with zipfile.ZipFile(BytesIO(bundle)) as archive:
        assert set(archive.namelist()) == {
            "policy_results.csv", "material_flows.csv", "target_curve.csv",
            "sensitivity.csv", "inputs.json", "source_rows.csv", "readme.txt",
        }
        inputs = json.loads(archive.read("inputs.json").decode("utf-8"))
        assert inputs["configuration"] == priced_config
        assert inputs["source_sha256"] == expected_hash
        source = pd.read_csv(BytesIO(archive.read("source_rows.csv")), encoding="utf-8-sig")
        assert len(source) == 4
        assert set(source.geography) == {"서울"}
        exported = pd.read_csv(
            BytesIO(archive.read("material_flows.csv")), encoding="utf-8-sig"
        )
        assert "관측 물질재활용 처리량(톤/년)" in exported
        assert "예상 최종 재생원료량(톤/년)" in exported
        assert "물질재활용 외 경로(톤/년)" in exported
    assert priced_config == original


def test_analysis_functions_do_not_mutate_callers_configuration(priced_config):
    original = deepcopy(priced_config)
    policy.compare_policies(priced_config)
    policy.target_curve(priced_config, [0, 0.5, 1])
    policy.sensitivity(priced_config)
    policy.input_snapshot(priced_config)
    assert priced_config == original


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), True, -0.1])
@pytest.mark.parametrize(
    "section, field",
    [
        ("baseline_yields", "폐지류"),
        ("costs", "collection_per_t"),
        ("economics", "time_value"),
        ("constraints", "material_capacity_t"),
    ],
)
def test_invalid_nonnegative_numeric_inputs_are_rejected(config, section, field, invalid):
    config[section][field] = invalid
    with pytest.raises(ValueError):
        policy.compare_policies(config)


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), True, -1.01, 1.01])
def test_invalid_signed_policy_effects_are_rejected(config, invalid):
    scenario_for(config, "B")["treatment_change_pp"] = invalid
    with pytest.raises(ValueError):
        policy.compare_policies(config)


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), True, False, -0.1, 1.1])
def test_invalid_target_curve_inputs_are_rejected(config, invalid):
    with pytest.raises(ValueError):
        policy.target_curve(config, [invalid])


