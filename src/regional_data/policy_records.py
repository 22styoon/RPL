import pandas as pd
POLICY_FIELDS=["policy_id","policy_name","policy_category","reference_year","sigungu_code","implemented_in_2024","start_date","end_date","target_materials","collection_mode","operating_entity","coverage_level","coverage_description","waste_scope","measurement_stage","scope_verified","code_reference_month","administrative_boundary_verified","boundary_source_url","boundary_source_locator","source_url","source_locator","retrieved_at","evidence_status"]
JOIN_FIELDS=["policy_id","policy_name","policy_category","sigungu_code","reference_year","material","generated_t","material_recycling_t","source_url","policy_source_url","verification_status"]
EXCLUSION_FIELDS=["policy_id","sigungu_code","material","reason"]
def flag(value):
    return value is True or str(value).strip().lower()=="true"

def missing(value):
    if value is None:return True
    try:
        if pd.isna(value):return True
    except (TypeError,ValueError):
        pass
    return str(value).strip()==""

def verified_join(materials,policies):
    joined=[];exclusions=[]
    for policy in policies.to_dict("records"):
        reasons=[]
        if policy.get("evidence_status")!="verified":reasons.append("policy_unverified")
        if not flag(policy.get("implemented_in_2024")):reasons.append("implementation_unverified")
        if missing(policy.get("reference_year")) or policy.get("reference_year")!=2024:reasons.append("year_mismatch")
        if missing(policy.get("sigungu_code")):reasons.append("geocode_missing")
        if policy.get("coverage_level")!="sigungu_full":reasons.append("aggregate_exposure_mismatch")
        if not flag(policy.get("scope_verified")):reasons.append("scope_unverified")
        if not flag(policy.get("administrative_boundary_verified")):reasons.append("administrative_boundary_unverified")
        if str(policy.get("code_reference_month"))!="202412":reasons.append("code_reference_month_unverified")
        for field in ("source_url","source_locator","retrieved_at","collection_mode","operating_entity","boundary_source_url","boundary_source_locator"):
            if missing(policy.get(field)):reasons.append(field+"_missing")
        try:
            if missing(policy.get("start_date")) or missing(policy.get("end_date")):
                raise ValueError("date_missing")
            start=pd.Timestamp(policy["start_date"]);end=pd.Timestamp(policy["end_date"])
            if pd.isna(start) or pd.isna(end):raise ValueError("date_missing")
            if start>pd.Timestamp("2024-01-01") or end<pd.Timestamp("2024-12-31"):reasons.append("temporal_exposure_mismatch")
        except (ValueError,KeyError,TypeError):
            reasons.append("dates_unverified")
        if reasons:
            exclusions.append(dict(policy_id=policy.get("policy_id"),sigungu_code=policy.get("sigungu_code"),material=None,reason=";".join(reasons)));continue
        selected=materials.loc[(materials.sigungu_code.astype(str)==str(policy["sigungu_code"]))&(materials.reference_year==2024)]
        if "code_reference_month" not in selected or selected.code_reference_month.isna().any() or not selected.code_reference_month.astype(str).eq(str(policy.get("code_reference_month"))).all():
            reasons.append("data_code_reference_mismatch")
        if "compatibility_status" not in selected or selected.compatibility_status.astype(str).str.contains("midyear_boundary_not_audited",regex=False).any():
            reasons.append("data_boundary_audit_missing")
        if reasons:
            exclusions.append(dict(policy_id=policy["policy_id"],sigungu_code=policy["sigungu_code"],material=None,reason=";".join(dict.fromkeys(reasons))));continue
        targets=[] if missing(policy.get("target_materials")) else str(policy.get("target_materials")).split(";")
        selected=selected.loc[selected.material.isin(targets)]
        if selected.empty:
            exclusions.append(dict(policy_id=policy["policy_id"],sigungu_code=policy["sigungu_code"],material=None,reason="no_matching_verified_material"));continue
        for row in selected.to_dict("records"):
            if row.get("verification_status")!="verified" or row.get("waste_scope")!=policy.get("waste_scope") or row.get("measurement_stage")!=policy.get("measurement_stage"):
                exclusions.append(dict(policy_id=policy["policy_id"],sigungu_code=policy["sigungu_code"],material=row["material"],reason="outcome_scope_or_stage_mismatch"));continue
            joined.append(dict(row,policy_id=policy["policy_id"],policy_name=policy["policy_name"],policy_category=policy["policy_category"],
                policy_source_url=policy["source_url"],verification_status="verified_join"))
    result=pd.DataFrame(joined,columns=list(dict.fromkeys([*materials.columns,*JOIN_FIELDS])))
    if not result.empty:
        ambiguous=result.duplicated(["sigungu_code","reference_year","material"],keep=False)
        for row in result.loc[ambiguous].to_dict("records"):
            exclusions.append(dict(policy_id=row["policy_id"],sigungu_code=row["sigungu_code"],material=row["material"],reason="multiple_policies_ambiguous"))
        result=result.loc[~ambiguous].copy()
    return result,pd.DataFrame(exclusions,columns=EXCLUSION_FIELDS)
