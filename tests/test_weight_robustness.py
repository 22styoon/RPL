import numpy as np
import pandas as pd
import pytest
from scipy.optimize import linprog
from src.analysis.weight_robustness import linear_extrema, compare_rate_bounds


def simplex(materials):
    return {"kind": "box", "lower": dict.fromkeys(materials, 0), "upper": dict.fromkeys(materials, 1)}


def compare(lower, upper=None, domains=None):
    return compare_rate_bounds(lower, lower if upper is None else upper,
        domains or {"all": simplex(lower.columns)}, reference_weights=dict.fromkeys(lower.columns, 1 / len(lower.columns)),
        reference_year=2024, measurement_label="constructed example")


def test_pair_gap_uses_same_weights_even_when_separate_score_intervals_overlap():
    rates = pd.DataFrame([[.9, .6], [.8, .5]], index=["A", "B"], columns=["paper", "plastic"])
    pairs, bounds, witnesses, _ = compare(rates)
    assert pairs.iloc[0].comparison == "a_strict"
    assert pairs.iloc[0].gap_lower_pp == pytest.approx(10)
    assert pairs.iloc[0].gap_upper_pp == pytest.approx(10)
    assert bounds.score_lower_pct.tolist() == pytest.approx([60, 50])
    assert bounds.score_upper_pct.tolist() == pytest.approx([90, 80])
    assert bounds.rank_lower_outer.tolist() == [1, 2]
    assert bounds.rank_upper_outer.tolist() == [1, 2]
    assert witnesses.groupby("endpoint").weight.sum().tolist() == pytest.approx([1, 1])


def test_all_weights_reduce_to_materialwise_extrema_and_expose_reversal():
    rates = pd.DataFrame([[.8, .2], [.2, .8]], index=["A", "B"], columns=["p", "g"])
    pairs, bounds, _, summary = compare(rates)
    assert pairs.iloc[0].comparison == "indeterminate"
    assert pairs.iloc[0].gap_lower_pp == pytest.approx(-60)
    assert pairs.iloc[0].gap_upper_pp == pytest.approx(60)
    assert summary.indeterminate_pairs.iloc[0] == 1
    assert bounds.rank_lower_outer.tolist() == [1, 1]
    assert bounds.rank_upper_outer.tolist() == [2, 2]


def test_three_alternatives_do_not_cover_their_coordinate_envelope():
    materials = list("abcd")
    vertices = pd.DataFrame([[.4,.3,.2,.1], [.2,.4,.1,.3], [.25]*4], columns=materials)
    hull = {"kind": "hull", "vertices": vertices.T.to_dict()}
    box = {"kind": "box", "lower": vertices.min().to_dict(), "upper": vertices.max().to_dict()}
    rates = pd.DataFrame([[.26,.76,.76,.26], [.5]*4], index=["A","B"], columns=materials)
    pairs, *_ = compare(rates, domains={"hull": hull, "box": box})
    assert pairs.iloc[0].comparison == "a_strict"
    assert pairs.iloc[0].gap_lower_pp == pytest.approx(1)
    assert pairs.iloc[1].comparison == "indeterminate"
    assert pairs.iloc[1].gap_lower_pp == pytest.approx(-6.5)


def test_box_extrema_match_independent_linear_programming_oracle():
    rng = np.random.default_rng(19)
    for _ in range(12):
        c = pd.Series(rng.normal(size=4), index=list("abcd"))
        reference = rng.dirichlet(np.ones(4))
        lower, upper = reference * .5, np.minimum(reference + .3, 1)
        domain = {"kind":"box", "lower":dict(zip(c.index,lower)), "upper":dict(zip(c.index,upper))}
        result = linear_extrema(c, domain)
        oracle = linprog(c, A_eq=[np.ones(4)], b_eq=[1], bounds=list(zip(lower,upper)), method="highs")
        maximum = linprog(-c, A_eq=[np.ones(4)], b_eq=[1], bounds=list(zip(lower,upper)), method="highs")
        assert oracle.success and maximum.success
        assert result["minimum"] == pytest.approx(oracle.fun)
        assert result["maximum"] == pytest.approx(-maximum.fun)


def test_missing_final_output_intervals_do_not_turn_into_midpoint_scores():
    lower = pd.DataFrame([[.8,0], [.6,.3]], index=["A","B"], columns=["paper","plastic"])
    upper = lower.copy(); upper.loc["A","plastic"] = 1
    pairs, bounds, _, summary = compare(lower, upper)
    assert not pairs.rates_exact.any()
    assert pairs.iloc[0].comparison == "indeterminate"
    assert pd.isna(bounds.reference_score_pct.iloc[0])
    assert bounds.reference_score_pct.iloc[1] == pytest.approx(45)
    assert not summary.rates_exact.any()


def test_numeric_string_rates_are_normalized_before_arithmetic():
    rates = pd.DataFrame([[".8",".5"],[".6",".2"]], index=["A","B"], columns=["p","g"])
    pairs, *_ = compare(rates)
    assert pairs.iloc[0].comparison == "a_strict"


def test_unrelated_missing_entity_does_not_hide_exact_pair_or_entity():
    lower = pd.DataFrame([[.8,.5],[.6,.2],[0,0]], index=["A","B","C"], columns=["p","g"])
    upper = lower.copy(); upper.loc["C"] = 1
    pairs, bounds, *_ = compare(lower, upper)
    assert pairs.iloc[0].rates_exact
    assert not pairs.iloc[1].rates_exact
    assert bounds.reference_score_pct.iloc[:2].tolist() == pytest.approx([65,40])
    assert pd.isna(bounds.reference_score_pct.iloc[2])


def test_boolean_rate_cells_are_rejected():
    rates = pd.DataFrame([[True,.5],[.6,.2]], index=["A","B"], columns=["p","g"])
    with pytest.raises(ValueError): compare(rates)


@pytest.mark.parametrize("year", [True,2024.5,float("nan"),float("inf"),"2024",None,0])
def test_reference_year_must_be_a_positive_integer(year):
    rates = pd.DataFrame([[.8,.5],[.6,.2]], index=["A","B"], columns=["p","g"])
    with pytest.raises(ValueError):
        compare_rate_bounds(rates,rates,{"all":simplex(rates.columns)},reference_weights={"p":.5,"g":.5},
                            reference_year=year,measurement_label="constructed example")


def test_ties_and_weak_dominance_do_not_create_false_strict_ranks():
    rates = pd.DataFrame([[.8,.5],[.8,.4],[.8,.5]], index=["A","B","C"], columns=["p","g"])
    pairs, bounds, _, _ = compare(rates)
    assert pairs.comparison.tolist() == ["a_no_reversal", "tie", "b_no_reversal"]
    assert bounds.rank_lower_outer.tolist() == [1,1,1]
    assert bounds.rank_upper_outer.tolist() == [1,3,1]


@pytest.mark.parametrize("domain", [
    {"kind":"box","lower":{"p":.8,"g":.8},"upper":{"p":1,"g":1}},
    {"kind":"box","lower":{"p":0,"g":0},"upper":{"p":.4,"g":.4}},
    {"kind":"box","lower":{"p":0,"g":0},"upper":{"p":-.1,"g":1}},
    {"kind":"hull","vertices":{"v":{"p":.5,"g":.4}}},
    {"kind":"hull","vertices":{"v":{"p":True,"g":0}}}])
def test_invalid_weight_sets_are_rejected(domain):
    with pytest.raises(ValueError):
        linear_extrema(pd.Series([.1,.2], index=["p","g"]), domain)


@pytest.mark.parametrize("bad", ["missing", "over_one", "negative", "duplicate", "misaligned"])
def test_incomplete_or_inconsistent_rate_tables_are_rejected(bad):
    rates = pd.DataFrame([[.8,.5],[.6,.2]], index=["A","B"], columns=["p","g"])
    upper = rates.copy()
    if bad == "missing": rates.iloc[0,0] = np.nan
    elif bad == "over_one": rates.iloc[0,0] = 2
    elif bad == "negative": rates.iloc[0,0] = -.1
    elif bad == "duplicate": rates.index = ["A","A"]
    else: upper = upper.rename(columns={"p":"paper"})
    with pytest.raises(ValueError): compare(rates, upper)
