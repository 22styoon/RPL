"""법제처 자치법규 후보의 기관명을 2024 MOIS 행정코드에 정확 매칭한다."""
import pandas as pd

from .boundary_audit import ALIASES as MOIS_SIDO_ALIASES


def _sido_lookup(codes):
    rows = codes.dropna(subset=["sido_name", "sido_code"])
    lookup = {}
    for row in rows.to_dict("records"):
        lookup[str(row["sido_name"]).strip()] = str(row["sido_code"]).strip()
    return lookup


def _resolve_locality(value, codes, waste_codes, sido_codes):
    locality = " ".join(str(value or "").split())
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
    waste_codes = set(waste_units.sigungu_code.dropna().astype(str))
    sido_codes = _sido_lookup(codes)
    linked = candidates.copy()
    geography = pd.DataFrame([_resolve_locality(row.locality, codes, waste_codes, sido_codes)
                              for row in linked.itertuples(index=False)], index=linked.index)
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
