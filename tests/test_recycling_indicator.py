import numpy as np
import pandas as pd
import pytest
from src.analysis.recycling_indicator import BOUNDARY, evaluate_rates, pool_three_years

WEIGHTS = {"paper": .5, "plastic": .5}


def flows():
    # Constructed pedagogical data, not national observations.
    return pd.DataFrame([
        {"entity": entity, "year": 2024, "material": material, "generated_t": mass,
         "secondary_output_t": mass * rate, "source_id": "synthetic_test", "source_locator": "test fixture",
         **BOUNDARY}
        for entity, masses in [("A", [900, 100]), ("B", [100, 900])]
        for material, mass, rate in zip(WEIGHTS, masses, [.8, .2])])


def test_composition_invariance_and_actual_mass_rate():
    result, _ = evaluate_rates(flows(), WEIGHTS)
    assert result.S_pct.tolist() == pytest.approx([50, 50])
    assert result.H_pct.tolist() == pytest.approx([74, 26])


def test_scale_invariance_and_material_monotonicity():
    data = flows()
    before, _ = evaluate_rates(data, WEIGHTS)
    data.loc[data.entity.eq("A"), ["generated_t", "secondary_output_t"]] *= 100
    scaled, _ = evaluate_rates(data, WEIGHTS)
    assert np.allclose(before.S_pct, scaled.S_pct)
    data.loc[0, "secondary_output_t"] += data.loc[0, "generated_t"] * .1
    improved, _ = evaluate_rates(data, WEIGHTS)
    assert improved.S_pct.iloc[0] == pytest.approx(before.S_pct.iloc[0] + 5)


def test_missing_output_produces_bounds_without_point_or_zero_imputation():
    data = flows().iloc[:2].copy()
    data.loc[1, "secondary_output_t"] = np.nan
    result, materials = evaluate_rates(data, WEIGHTS)
    row = result.iloc[0]
    assert pd.isna(row.S_pct) and pd.isna(row.H_pct)
    assert row.S_lower_pct == pytest.approx(40)
    assert row.S_upper_pct == pytest.approx(90)
    assert row.observed_generation_pct == pytest.approx(90)
    assert row.observed_reference_pct == pytest.approx(50)
    assert pd.isna(materials.loc[1, "secondary_output_t"])


def test_traced_output_interval_and_process_yield_have_separate_denominators():
    data = flows().iloc[:2].copy()
    data["recycling_input_t"] = [800, 50]
    result, _ = evaluate_rates(data, WEIGHTS)
    assert result.process_yield_pct.iloc[0] == pytest.approx(100 * 740 / 850)
    data.loc[1, "secondary_output_t"] = np.nan
    data.loc[1, "output_lower_t"] = 10
    data.loc[1, "output_upper_t"] = 30
    bounded, _ = evaluate_rates(data, WEIGHTS)
    assert bounded.S_lower_pct.iloc[0] == pytest.approx(45)
    assert bounded.S_upper_pct.iloc[0] == pytest.approx(55)
    assert pd.isna(bounded.process_yield_pct.iloc[0])


@pytest.mark.parametrize("field,value", [
    ("measurement_point", "recycling_input"), ("trade_basis", "exports_assumed_recycled"),
    ("period_basis", "calendar_treatment"), ("mass_basis", "wet_output"),
    ("scope_id", "all_waste"), ("secondary_output_t", 1000),
    ("generated_t", 0), ("generated_t", float("inf")), ("generated_t", True),
    ("source_locator", ""), ("year", 2024.5)])
def test_invalid_boundary_and_physical_mass_are_rejected(field, value):
    data = flows().astype({field: object}) if field in flows() else flows()
    data.loc[0, field] = value
    with pytest.raises(ValueError):
        evaluate_rates(data, WEIGHTS)


def test_missing_material_and_duplicate_routes_cannot_change_weights():
    data = flows()
    for bad in [data.drop(index=0), pd.concat([data, data.iloc[:1]])]:
        with pytest.raises(ValueError):
            evaluate_rates(bad, WEIGHTS)


def test_three_year_mass_pooling_differs_from_averaging_rates_and_preserves_missing():
    rows = []
    for year, mass, rate in [(2022, 200, .3), (2023, 100, .5), (2024, 50, .7)]:
        part = flows().iloc[:2].copy()
        part["year"] = year
        part["generated_t"] = mass
        part["secondary_output_t"] = mass * rate
        rows.append(part)
    data = pd.concat(rows, ignore_index=True)
    result, _ = pool_three_years(data, WEIGHTS, end_year=2024)
    assert result.S_pct.iloc[0] == pytest.approx(100 * 145 / 350)
    data.loc[0, "secondary_output_t"] = np.nan
    result, _ = pool_three_years(data, WEIGHTS, end_year=2024)
    assert pd.isna(result.S_pct.iloc[0])
    with pytest.raises(ValueError):
        pool_three_years(data.loc[data.year.ne(2023)], WEIGHTS, end_year=2024)
