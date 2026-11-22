"""Exact common-weight comparisons for linear material-rate indicators.

Weight sets are declared normative/scenario choices, not distributions. Bounds
describe possible scores, not confidence intervals. Measurement intervals use
an independent rectangular uncertainty set; dependence needs extra constraints.
"""
from itertools import combinations
import numpy as np
import pandas as pd

TOL = 1e-10


def _vector(values, materials, name, *, probability=False):
    if set(values) != set(materials):
        raise ValueError(name + ": material names must match exactly")
    raw = [values[m] for m in materials]
    if any(isinstance(v, (bool, np.bool_)) for v in raw):
        raise ValueError(name + ": booleans are not weights or rates")
    result = np.asarray(raw, dtype=float)
    if not np.isfinite(result).all():
        raise ValueError(name + ": finite values required")
    if probability and ((result < 0).any() or (result > 1).any()):
        raise ValueError(name + ": values must lie in [0,1]")
    return result


def _domain_arrays(domain, materials):
    if domain.get("kind") == "hull":
        vertices = domain.get("vertices", {})
        if not vertices:
            raise ValueError("A convex hull needs named reference weight vectors")
        values = np.stack([_vector(v, materials, "vertex", probability=True) for v in vertices.values()])
        if not np.allclose(values.sum(axis=1), 1, rtol=0, atol=TOL):
            raise ValueError("Each reference vector must sum to one")
        return "hull", values
    if domain.get("kind") == "box":
        lower = _vector(domain["lower"], materials, "weight lower", probability=True)
        upper = _vector(domain["upper"], materials, "weight upper", probability=True)
        if (lower > upper).any() or lower.sum() > 1 + TOL or upper.sum() < 1 - TOL:
            raise ValueError("Weight bounds and sum-to-one constraint are infeasible")
        return "box", (lower, upper)
    raise ValueError("Supported weight sets are convex hull and bounded simplex")


def _minimize_box(coefficients, lower, upper):
    # Exchange argument: allocate remaining weight to the cheapest coefficient
    # first; a positive transfer from a dearer unfilled component cannot help.
    weights = lower.copy()
    remaining = 1.0 - float(weights.sum())
    for index in np.argsort(coefficients, kind="stable"):
        amount = min(max(0.0, remaining), float(upper[index] - weights[index]))
        weights[index] += amount
        remaining -= amount
    if remaining > TOL or not np.isclose(weights.sum(), 1, rtol=0, atol=TOL):
        raise ValueError("No feasible unit-sum weight vector")
    return weights


def linear_extrema(coefficients: pd.Series, domain: dict):
    """Min/max of one linear form over a common, explicitly declared weight set."""
    if coefficients.empty or coefficients.index.has_duplicates:
        raise ValueError("Unique named coefficients required")
    materials = list(coefficients.index)
    c = _vector(coefficients.to_dict(), materials, "coefficients")
    kind, values = _domain_arrays(domain, materials)
    if kind == "hull":
        scores = values @ c
        w_min, w_max = values[int(np.argmin(scores))], values[int(np.argmax(scores))]
    else:
        lower, upper = values
        w_min = _minimize_box(c, lower, upper)
        w_max = _minimize_box(-c, lower, upper)
    return {"minimum": float(w_min @ c), "maximum": float(w_max @ c),
            "min_weights": dict(zip(materials, w_min.tolist())),
            "max_weights": dict(zip(materials, w_max.tolist()))}


def _comparison(lower, upper):
    if lower > TOL:
        return "a_strict"
    if upper < -TOL:
        return "b_strict"
    if lower >= -TOL and upper <= TOL:
        return "tie"
    if lower >= -TOL:
        return "a_no_reversal"
    if upper <= TOL:
        return "b_no_reversal"
    return "indeterminate"


def compare_rate_bounds(lower: pd.DataFrame, upper: pd.DataFrame, domains: dict,
                        *, reference_weights: dict, reference_year: int, measurement_label: str):
    """Pair gaps optimize a SINGLE common w, not separate country score bounds.

    For A,B: min_w w*(lower_A-upper_B), max_w w*(upper_A-lower_B).
    Rank intervals are conservative outer bounds from pairwise guarantees;
    their endpoints need not be jointly attainable for all competitors.
    """
    if lower.empty or len(lower) < 2 or not lower.index.equals(upper.index) or not lower.columns.equals(upper.columns):
        raise ValueError("Aligned rate bounds for at least two entities are required")
    if lower.index.has_duplicates or lower.columns.has_duplicates or lower.index.isna().any() or lower.columns.isna().any():
        raise ValueError("Unique non-missing entity and material labels required")
    if not measurement_label or not domains:
        raise ValueError("Measurement boundary label and explicit weight sets required")
    if isinstance(reference_year, (bool, np.bool_)) or not isinstance(reference_year, (int, np.integer)) or reference_year < 1:
        raise ValueError("Positive integer reference year required")
    reference_year=int(reference_year)
    for frame in (lower, upper):
        if any(isinstance(value, (bool, np.bool_)) for value in frame.to_numpy().flat):
            raise ValueError("Boolean cells are not measured rates")
    lo, hi = lower.to_numpy(dtype=float), upper.to_numpy(dtype=float)
    if not np.isfinite(lo).all() or not np.isfinite(hi).all() or (lo < 0).any() or (hi > 1).any() or (lo > hi).any():
        raise ValueError("Finite ordered rates within [0,1] required; missing strata are not dropped")
    lower = pd.DataFrame(lo, index=lower.index, columns=lower.columns)
    upper = pd.DataFrame(hi, index=upper.index, columns=upper.columns)
    materials = list(lower.columns)
    reference = _vector(reference_weights, materials, "reference weights", probability=True)
    if not np.isclose(reference.sum(), 1, rtol=0, atol=TOL):
        raise ValueError("Reference weights must sum to one")
    meta = {"reference_year": reference_year, "measurement": measurement_label}
    pairs, witnesses, bounds, summaries = [], [], [], []
    exact = bool(np.array_equal(lo, hi))
    for domain_id, domain in domains.items():
        _domain_arrays(domain, materials)
        gap_min, gap_max = {}, {}
        domain_rows = []
        for a, b in combinations(lower.index, 2):
            worst = linear_extrema(lower.loc[a] - upper.loc[b], domain)
            best = linear_extrema(upper.loc[a] - lower.loc[b], domain)
            minimum, maximum = worst["minimum"], best["maximum"]
            comparison = _comparison(minimum, maximum)
            row = {"domain": domain_id, "entity_a": a, "entity_b": b,
                   "gap_lower_pp": minimum * 100, "gap_upper_pp": maximum * 100,
                   "comparison": comparison,
                   "rates_exact": bool(np.array_equal(lower.loc[[a,b]], upper.loc[[a,b]])), **meta}
            pairs.append(row); domain_rows.append(row)
            gap_min[a, b], gap_max[a, b] = minimum, maximum
            gap_min[b, a], gap_max[b, a] = -maximum, -minimum
            for endpoint, weights, a_rates, b_rates in [
                ("lower", worst["min_weights"], lower.loc[a], upper.loc[b]),
                ("upper", best["max_weights"], upper.loc[a], lower.loc[b])]:
                for m in materials:
                    witnesses.append({"domain": domain_id, "entity_a": a, "entity_b": b,
                        "endpoint": endpoint, "material": m, "weight": weights[m],
                        "rate_a": float(a_rates[m]), "rate_b": float(b_rates[m]),
                        "gap_contribution_pp": float(100 * weights[m] * (a_rates[m] - b_rates[m])), **meta})
        for entity in lower.index:
            minimum = linear_extrema(lower.loc[entity], domain)["minimum"] * 100
            maximum = linear_extrema(upper.loc[entity], domain)["maximum"] * 100
            others = [other for other in lower.index if other != entity]
            guaranteed_above = sum(gap_max[entity, other] < -TOL for other in others)
            possibly_above = sum(gap_min[entity, other] < -TOL for other in others)
            bounds.append({"domain": domain_id, "entity": entity,
                "score_lower_pct": minimum, "score_upper_pct": maximum,
                "rank_lower_outer": 1 + guaranteed_above, "rank_upper_outer": 1 + possibly_above,
                "reference_score_pct": float(reference @ lower.loc[entity]) * 100
                if np.array_equal(lower.loc[entity], upper.loc[entity]) else np.nan, **meta})
        counts = pd.Series([row["comparison"] for row in domain_rows]).value_counts()
        summaries.append({"domain": domain_id, "kind": domain["kind"], "pair_count": len(domain_rows),
            "strict_pairs": int(counts.get("a_strict", 0) + counts.get("b_strict", 0)),
            "nonreversal_pairs": int(len(domain_rows) - counts.get("indeterminate", 0)),
            "indeterminate_pairs": int(counts.get("indeterminate", 0)),
            "tie_pairs": int(counts.get("tie", 0)), "rates_exact": exact, **meta})
    return pd.DataFrame(pairs), pd.DataFrame(bounds), pd.DataFrame(witnesses), pd.DataFrame(summaries)
