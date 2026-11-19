"""법제처 자치법규 후보의 기관명을 2024 MOIS 행정코드에 정확 매칭한다."""
import pandas as pd

from .boundary_audit import ALIASES as MOIS_SIDO_ALIASES

GEOGRAPHY_FIELDS = (
    "matched_sido_name_2024", "matched_sido_code_2024",
    "matched_sigungu_name_2024", "matched_sigungu_code_2024",
    "code_reference_month", "geography_match_status",
    "waste_statistical_unit_2024", "geography_source_locator",
)


def _validate_reference_period(frame, label):
    """Absent period metadata is legacy-compatible; contradictory metadata is not."""
    for field, expected in (("code_reference_month", "202412"),
                            ("reference_month", "202412"), ("reference_year", "2024")):
        if field in frame and not frame[field].astype(str).str.strip().eq(expected).all():
            raise ValueError(f"{label}: {field} must identify {expected} throughout.")


def _normalize_identities(frame, label):
    normalized = frame.copy()
    fields = [field for field in ("sido_name", "sido_code", "sigungu_name", "sigungu_code")
              if field in normalized]
    for field in fields:
        if normalized[field].isna().any():
            raise ValueError(f"{label}: {field} contains a missing geographic identity.")
        normalized[field] = normalized[field].astype(str).str.strip()
        if normalized[field].eq("").any():
            raise ValueError(f"{label}: {field} contains a missing geographic identity.")
    identities = normalized[fields].drop_duplicates()
    if {"sido_name", "sido_code"}.issubset(fields):
        for source, target in (("sido_name", "sido_code"), ("sido_code", "sido_name")):
            if identities.groupby(source)[target].nunique().gt(1).any():
                raise ValueError(f"{label}: ambiguous province name/code mapping.")
    if "sigungu_code" in fields:
        for field in fields:
            if field != "sigungu_code" and identities.groupby("sigungu_code")[field].nunique().gt(1).any():
                raise ValueError(f"{label}: conflicting identity for the same sigungu code.")
    return normalized


def _validate_shared_identity(codes, waste_units):
    common = [field for field in ("sido_name", "sido_code", "sigungu_name")
              if field in waste_units]
    if not common:
        return
    matched = codes[["sigungu_code", *common]].drop_duplicates().merge(
        waste_units[["sigungu_code", *common]].drop_duplicates(), on="sigungu_code",
        suffixes=("_code", "_waste"))
    if any(matched[field + "_code"].ne(matched[field + "_waste"]).any() for field in common):
        raise ValueError("MOIS and waste inputs disagree on a shared sigungu code's identity.")


def _sido_lookup(codes):
    # _normalize_identities rejects contradictory province mappings first.
    pairs = codes[["sido_name", "sido_code"]].drop_duplicates()
    return dict(pairs.itertuples(index=False, name=None))


def _resolve_locality(value, codes, waste_codes, sido_codes):
    locality = "" if pd.isna(value) else " ".join(str(value).split())
    if not locality:
        return {"matched_sido_name_2024": "", "matched_sido_code_2024": "",
                "matched_sigungu_name_2024": "", "matched_sigungu_code_2024": "",
                "code_reference_month": "202412", "geography_match_status": "locality_missing",
                "waste_statistical_unit_2024": False, "geography_source_locator": ""}

    provinces = sorted(MOIS_SIDO_ALIASES.items(), key=lambda item: len(item[0]), reverse=True)
    canonical = ""
    remainder = ""
    for alias, name in provinces:
        if locality == alias:
            canonical = name
            break
        if locality.startswith(alias + " "):
            canonical = name
            remainder = locality[len(alias):].strip()
            break
    if not canonical and locality in sido_codes:
        canonical = locality

    if not canonical or canonical not in sido_codes:
        return {"matched_sido_name_2024": "", "matched_sido_code_2024": "",
                "matched_sigungu_name_2024": "", "matched_sigungu_code_2024": "",
                "code_reference_month": "202412", "geography_match_status": "locality_unmatched_2024_admin_roster",
                "waste_statistical_unit_2024": False, "geography_source_locator": ""}

    sido_code = sido_codes[canonical]
    if not remainder:
        return {"matched_sido_name_2024": canonical, "matched_sido_code_2024": sido_code,
                "matched_sigungu_name_2024": "", "matched_sigungu_code_2024": "",
                "code_reference_month": "202412", "geography_match_status": "sido_only_no_sigungu_outcome_join",
                "waste_statistical_unit_2024": False,
                "geography_source_locator": "MOIS lv=2; statsYm=202412; sido_code=" + sido_code}

    match = codes.loc[(codes.sido_name.astype(str).str.strip() == canonical)
                      & (codes.sigungu_name.astype(str).str.strip() == remainder)]
    if len(match) != 1:
        return {"matched_sido_name_2024": canonical, "matched_sido_code_2024": sido_code,
                "matched_sigungu_name_2024": "", "matched_sigungu_code_2024": "",
                "code_reference_month": "202412", "geography_match_status": "locality_unmatched_2024_admin_roster",
                "waste_statistical_unit_2024": False, "geography_source_locator": ""}

    row = match.iloc[0]
    code = str(row.sigungu_code)
    statistical = code in waste_codes
    status = "matched_2024_waste_statistical_unit" if statistical else "matched_2024_admin_code_not_waste_unit"
    return {"matched_sido_name_2024": canonical, "matched_sido_code_2024": sido_code,
            "matched_sigungu_name_2024": remainder, "matched_sigungu_code_2024": code,
            "code_reference_month": "202412", "geography_match_status": status,
            "waste_statistical_unit_2024": statistical,
            "geography_source_locator": "MOIS lv=2; statsYm=202412; admmCd=" + code}


def link_ordinance_geography(candidates, codes, waste_units):
    required = {"locality", "ordinance_id", "ordinance_serial", "candidate_status"}
    if not required.issubset(candidates.columns):
        raise ValueError("조례 후보 CSV 필수 열이 없습니다.")
    code_required = {"sido_name", "sigungu_name", "sido_code", "sigungu_code"}
    if not code_required.issubset(codes.columns):
        raise ValueError("MOIS 코드 CSV 필수 열이 없습니다.")
    if "sigungu_code" not in waste_units:
        raise ValueError("폐기물 통계단위 CSV 필수 열이 없습니다.")
    for frame, label in ((codes, "MOIS"), (waste_units, "waste")):
        _validate_reference_period(frame, label)
    codes = _normalize_identities(codes, "MOIS")
    waste_units = _normalize_identities(waste_units, "waste")
    _validate_shared_identity(codes, waste_units)
    # Repeated identical records are the same logical unit. Different codes
    # sharing a locality label remain ambiguous in _resolve_locality.
    codes = codes.drop_duplicates(subset=sorted(code_required))
    waste_codes = set(waste_units.sigungu_code.dropna().astype(str))
    sido_codes = _sido_lookup(codes)
    linked = candidates.copy()
    geography = pd.DataFrame([_resolve_locality(row.locality, codes, waste_codes, sido_codes)
                              for row in linked.itertuples(index=False)], index=linked.index,
                             columns=GEOGRAPHY_FIELDS)
    linked = pd.concat([linked, geography], axis=1)
    status_counts = linked.geography_match_status.value_counts().sort_index().to_dict()
    summary = {
        "reference_year": 2024,
        "code_reference_month": "202412",
        "ordinance_version_rows": int(len(linked)),
        "unique_ordinance_ids": int(linked.ordinance_id.nunique()),
        "unique_locality_labels": int(linked.locality.nunique()),
        "matched_waste_statistical_unit_rows": int(linked.waste_statistical_unit_2024.sum()),
        "matched_admin_code_non_statistical_unit_rows": int(linked.geography_match_status.eq("matched_2024_admin_code_not_waste_unit").sum()),
        "sido_only_rows": int(linked.geography_match_status.eq("sido_only_no_sigungu_outcome_join").sum()),
        "unmatched_locality_rows": int(linked.geography_match_status.eq("locality_unmatched_2024_admin_roster").sum()),
        "match_status_counts": status_counts,
        "operational_policy_verified_rows": 0,
        "verified_outcome_join_rows": 0,
        "limitation": "exact institution-name crosswalk only; legal implementation, full-sigungu exposure, GIS boundary and outcome compatibility remain unverified",
    }
    return linked, summary
