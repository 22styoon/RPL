"""RPL H/S v1: origin-traced secondary output rates and identification bounds.

These functions do not convert reported treatment quantities into final output.
Unknown outputs retain physical bounds; they never become observed zeroes.
"""
from collections.abc import Mapping
import numpy as np
import pandas as pd

BOUNDARY = {
    "scope_id": "municipal_dry_materials_v1",
    "denominator_id": "domestic_generated_material",
    "measurement_point": "secondary_material_output",
    "mass_basis": "dry_material_equivalent",
    "trade_basis": "domestic_origin_traced",
    "period_basis": "generation_cohort",
}
KEYS = ["entity", "year", "material"]


def _number(values, name, *, nullable=False):
    if values.map(lambda x: isinstance(x, (bool, np.bool_))).any():
        raise ValueError(f"{name}: boolean is not a mass or year")
    result = pd.to_numeric(values, errors="raise")
    valid = result.dropna().to_numpy(dtype=float)
    if not np.isfinite(valid).all() or (valid < 0).any():
        raise ValueError(f"{name}: finite non-negative values required")
    if not nullable and result.isna().any():
        raise ValueError(f"{name}: missing values")
    return result


def validate_flows(frame: pd.DataFrame, weights: Mapping[str, float]):
    required = {*KEYS, *BOUNDARY, "generated_t", "secondary_output_t", "source_id", "source_locator"}
    if not required.issubset(frame.columns) or frame.empty:
        raise ValueError("Missing flow fields or empty input")
    if not weights or any(isinstance(v, (bool, np.bool_)) for v in weights.values()):
        raise ValueError("Explicit reference weights required")
    w = pd.Series(weights, dtype=float)
    if not np.isfinite(w).all() or (w <= 0).any() or not np.isclose(w.sum(), 1, rtol=0, atol=1e-10):
        raise ValueError("Reference weights must be positive and sum to one")
    data = frame.copy()
    for name in ["entity", "material", "source_id", "source_locator"]:
        if data[name].isna().any() or data[name].astype(str).str.strip().eq("").any():
            raise ValueError(f"{name}: missing identity or evidence")
    for name, expected in BOUNDARY.items():
        if not data[name].eq(expected).all():
            raise ValueError(f"Boundary mismatch: {name}; no automatic harmonization")
    data["year"] = _number(data.year, "year")
    if not data.year.mod(1).eq(0).all():
        raise ValueError("Integer reference year required")
    data["year"] = data.year.astype(int)
    if data.duplicated(KEYS).any():
        raise ValueError("Duplicate entity/year/material; aggregate audited routes first")
    for _, group in data.groupby(["entity", "year"]):
        if set(group.material) != set(w.index):
            raise ValueError("Every reference material needs a row; never renormalize available materials")
    data["generated_t"] = _number(data.generated_t, "generated_t")
    if data.generated_t.le(0).any():
        raise ValueError("Positive material generation required; zero strata need a redesigned common basket")
    data["secondary_output_t"] = _number(data.secondary_output_t, "secondary_output_t", nullable=True)
    for name in ["output_lower_t", "output_upper_t", "recycling_input_t"]:
        data[name] = _number(data[name] if name in data else pd.Series(np.nan, index=data.index), name, nullable=True)
    intake = data.recycling_input_t
    if (intake.notna() & (intake > data.generated_t)).any():
        raise ValueError("Cohort input exceeds generated material")
    cap = data.generated_t.where(intake.isna(), intake)
    known = data.secondary_output_t.notna()
    if (data.secondary_output_t > cap + 1e-9).any():
        raise ValueError("Output exceeds physical cohort mass; check moisture, additives, trade and stocks")
    if (known & (data.output_lower_t.notna() | data.output_upper_t.notna())).any():
        raise ValueError("Provide an exact output or an interval, not both")
    if (data.output_lower_t.isna() ^ data.output_upper_t.isna()).any():
        raise ValueError("Both interval endpoints required")
    # Filling endpoints constructs an identification set, not an imputed observation.
    data["lower_t"] = data.secondary_output_t.where(known, data.output_lower_t.fillna(0))
    data["upper_t"] = data.secondary_output_t.where(known, data.output_upper_t.fillna(cap))
    if (data.lower_t > data.upper_t).any() or (data.upper_t > cap + 1e-9).any():
        raise ValueError("Invalid physical output interval")
    data["output_observed"] = known
    data["weight"] = data.material.map(w)
    data["rate_lower"] = data.lower_t / data.generated_t
    data["rate_upper"] = data.upper_t / data.generated_t
    return data


def evaluate_rates(frame: pd.DataFrame, weights: Mapping[str, float]):
    """Return H (actual mix), S (fixed mix), coverage and material bounds, in percent.

    H=100 sum(F)/sum(G); S=100 sum(w*F/G). A point is published only
    if all outputs are observed. Interval widths are not confidence intervals.
    """
    data = validate_flows(frame, weights)
    rows = []
    for (entity, year), part in data.groupby(["entity", "year"], sort=True):
        total = float(part.generated_t.sum())
        exact = bool(part.output_observed.all())
        lo = float(100 * part.lower_t.sum() / total)
        hi = float(100 * part.upper_t.sum() / total)
        slo = float(100 * (part.weight * part.rate_lower).sum())
        shi = float(100 * (part.weight * part.rate_upper).sum())
        intake = part.recycling_input_t.sum(min_count=len(part))
        rows.append({"entity": entity, "year": int(year), "status": "identified" if exact else "bounded",
                     "H_pct": lo if exact else np.nan, "S_pct": slo if exact else np.nan,
                     "H_lower_pct": lo, "H_upper_pct": hi, "S_lower_pct": slo, "S_upper_pct": shi,
                     "observed_generation_pct": float(100 * part.loc[part.output_observed, "generated_t"].sum() / total),
                     "observed_reference_pct": float(100 * part.loc[part.output_observed, "weight"].sum()),
                     "process_yield_pct": float(100 * part.secondary_output_t.sum() / intake)
                     if exact and pd.notna(intake) and intake > 0 else np.nan})
    return pd.DataFrame(rows), data


def pool_three_years(frame: pd.DataFrame, weights: Mapping[str, float], *, end_year: int):
    """Pool masses within each material, then apply the same reference weights.

    All entities must contain all three contiguous cohort years. This is an
    optional stability statistic, not Korea's EPR target-setting formula.
    """
    data = validate_flows(frame, weights)
    years = {end_year - 2, end_year - 1, end_year}
    selected = data.loc[data.year.isin(years)]
    rows = []
    for entity in data.entity.unique():
        for material in weights:
            part = selected.loc[(selected.entity == entity) & (selected.material == material)]
            if set(part.year) != years:
                raise ValueError("Every entity/material needs all three consecutive years")
            exact = bool(part.output_observed.all())
            row = {"entity": entity, "year": end_year, "material": material, **BOUNDARY,
                   "source_id": ";".join(sorted(set(part.source_id))),
                   "source_locator": ";".join(sorted(set(part.source_locator))),
                   "generated_t": part.generated_t.sum(),
                   "secondary_output_t": part.secondary_output_t.sum() if exact else np.nan,
                   "recycling_input_t": part.recycling_input_t.sum(min_count=3)}
            if not exact:
                row.update(output_lower_t=part.lower_t.sum(), output_upper_t=part.upper_t.sum())
            rows.append(row)
    result, materials = evaluate_rates(pd.DataFrame(rows), weights)
    result["window"] = f"{end_year-2}–{end_year}"
    return result, materials
