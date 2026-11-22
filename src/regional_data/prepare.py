from pathlib import Path
import json,hashlib
import pandas as pd
from src.model import ROOT
from .clients import dump
from .parsers import parse_counties
from .geocodes import normalize_mois_roster,attach_codes
from .validation import validate_materials,verify_lineage,MATERIALS
from .policy_records import POLICY_FIELDS,verified_join
from .audit_evidence import assess_boundary_audit

def prepare(root=ROOT,year=2024):
    root=Path(root)
    if year!=2024:raise ValueError("2024년만 검증했습니다.")
    directory=root/"data/processed/regional_2024"
    directory.mkdir(parents=True,exist_ok=True)
    original=root/"data/processed/kosis_materials_2024.csv"
    frame=pd.read_csv(original)
    regions=frame.loc[frame.geography!="전국"].copy()
    validate_materials(regions)
    metadata=json.loads((root/"data/raw/kosis/DT_106N_29_2020005_metadata.json").read_text(encoding="utf-8-sig"))
    lookup={row["ITM_NM"]:row["ITM_ID"] for row in metadata if row.get("OBJ_NM")=="구분" and not row.get("UP_ITM_ID")}
    regions["sido_code"]=regions.geography.map(lookup)
    regions["code_system"]="KOSIS_DT_106N_29_2020005_classification"
    regions["sigungu_code"]=None
    regions["administrative_level"]="sido"
    regions["source_id"]="KOSIS_DT_106N_29_2020005"
    regions["source_locator"]=regions.source_codes
    regions["verification_status"]="verified"
    regions["compatibility_status"]="2024_corresponding_four_materials"
    regions["measurement_stage"]="material_recycling_treatment"
    regions["source_sha256"]=hashlib.sha256(original.read_bytes()).hexdigest()
    verify_lineage(regions)
    regions.to_csv(directory/"sido_2024_materials_verified.csv",index=False,encoding="utf-8-sig")
    codes=pd.DataFrame(columns=["sido_name","sigungu_name","reference_year","sido_code","sigungu_code","code_reference_month","code_verified"])
    checkpoint=root/"data/raw/regional_2024/kr_admin_codes_2024/checkpoint.json"
    if checkpoint.exists():
        codes=normalize_mois_roster(json.loads(checkpoint.read_text(encoding="utf-8")))
    codes.to_csv(directory/"admin_codes_202412.csv",index=False,encoding="utf-8-sig")
    candidate_columns=["sido_name","sigungu_name","material","reference_year","generated_t","material_recycling_t","sido_code","sigungu_code","source_id","source_url","source_locator","retrieved_at","verification_status","compatibility_status","measurement_stage","waste_scope"]
    counties=pd.DataFrame(columns=candidate_columns);exclusions=[]
    latest=root/"data/raw/regional_2024/kr_waste_2024_detail/latest.json"
    reconciliation=[]
    if latest.exists():
        manifest=json.loads(latest.read_text(encoding="utf-8"))
        if manifest.get("raw_file"):
            raw=(root/manifest["raw_file"]).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=manifest["sha256"]:raise ValueError("원본 ZIP 해시 오류")
            parsed=parse_counties(raw,manifest)
            for row in frame.to_dict("records"):
                reference=parsed.loc[(parsed.sido_name==row["geography"])&parsed.sigungu_name.isin(["소계","합계"])&(parsed.material==row["material"])]
                if len(reference)==1:
                    item=reference.iloc[0]
                    reconciliation.append(dict(geography=row["geography"],material=row["material"],generated_difference_t=item.generated_t-row["generated_t"],material_difference_t=item.material_recycling_t-row["material_recycling_t"]))
            pd.DataFrame(reconciliation).to_csv(directory/"workbook_kosis_reconciliation.csv",index=False,encoding="utf-8-sig")
            if any(abs(x["generated_difference_t"])>.6 or abs(x["material_difference_t"])>.6 for x in reconciliation):
                raise ValueError("XLSX 시도·전국 행과 KOSIS 원표 불일치")
            raw_counties=parsed.loc[(parsed.sido_name!="전국")&~parsed.sigungu_name.isin(["소계","합계"])].copy()
            counties=attach_codes(raw_counties,codes)
            counties["geography"]=counties.sido_name+" "+counties.sigungu_name
            for index,row in counties.iterrows():
                reason=None
                if pd.isna(row.sigungu_code):reason="202412_admin_code_unmatched"
                elif pd.isna(row.generated_t) or pd.isna(row.material_recycling_t):reason="source_cell_missing"
                elif row.generated_t<=0:reason="zero_or_negative_denominator"
                elif not 0<=row.material_recycling_t<=row.generated_t:reason="M_outside_0_G"
                if reason:
                    exclusions.append(dict(geography=row.geography,material=row.material,reason=reason,source_locator=row.source_locator))
                else:
                    counties.loc[index,"verification_status"]="verified"
                    counties.loc[index,"compatibility_status"]="name_and_202412_code_match_midyear_boundary_not_audited"
    verified=counties.loc[counties.verification_status=="verified"].copy()
    if not verified.empty:
        counts=verified.groupby("sigungu_code").material.nunique()
        verified=verified.loc[verified.sigungu_code.isin(counts[counts==4].index)]
        verified["administrative_level"]="sigungu"
        validate_materials(verified,region_key="sigungu_code");verify_lineage(verified)
    # Bind audit evidence only after the CURRENT parsed/validated unit roster
    # exists. A cached success flag alone cannot upgrade newly replaced inputs.
    assessment=assess_boundary_audit(root,waste_frame=verified,december_frame=codes)
    boundary_audit_ok=assessment["verified"]
    metadata_code_snapshot=("2024_monthly_code_name_roster_stable_input_binding_verified_geometry_not_assessed"
        if boundary_audit_ok else "202412_not_a_current_bound_midyear_audit")
    for dataset in (counties,verified):
        dataset["boundary_input_binding_verified"]=bool(boundary_audit_ok)
        dataset["boundary_waste_roster_sha256"]=assessment.get("waste_roster_sha256","")
        dataset["boundary_monthly_roster_sha256"]=assessment.get("monthly_roster_sha256","")
        if not dataset.empty:
            valid=dataset.verification_status.eq("verified")
            dataset.loc[valid,"compatibility_status"]=(
                "2024_monthly_MOIS_code_name_roster_stable; input_binding_verified; geometry_not_assessed"
                if boundary_audit_ok else "name_and_202412_code_match_midyear_boundary_not_audited; input_binding_unverified")
    counties.to_csv(directory/"sigungu_2024_materials_candidates.csv",index=False,encoding="utf-8-sig")
    verified.to_csv(directory/"sigungu_2024_materials_verified.csv",index=False,encoding="utf-8-sig")
    pd.DataFrame(exclusions,columns=["geography","material","reason","source_locator"]).to_csv(directory/"material_exclusions.csv",index=False,encoding="utf-8-sig")
    policy_path=directory/"policy_candidates_unverified.csv"
    if not policy_path.exists():
        pd.DataFrame(columns=POLICY_FIELDS).to_csv(policy_path,index=False,encoding="utf-8-sig")
    policies=pd.read_csv(policy_path,dtype={"sigungu_code":str})
    for field in POLICY_FIELDS:
        if field not in policies:policies[field]=pd.NA
    policies=policies[[*POLICY_FIELDS,*[field for field in policies.columns if field not in POLICY_FIELDS]]]
    policies.to_csv(policy_path,index=False,encoding="utf-8-sig")
    joined,rejected=verified_join(verified,policies)
    joined.to_csv(directory/"sigungu_2024_policy_material_join_verified.csv",index=False,encoding="utf-8-sig")
    rejected.to_csv(directory/"join_exclusions.csv",index=False,encoding="utf-8-sig")
    result=dict(reference_year=year,sido_rows=len(regions),sigungu_candidates=len(counties),
        sigungu_verified_rows=len(verified),sigungu_verified_regions=verified.sigungu_code.nunique() if len(verified) else 0,
        policy_candidates=len(policies),policy_verified_rows=int(policies.evidence_status.eq("verified").sum()),
        verified_join_rows=len(joined),metadata_code_snapshot=metadata_code_snapshot,
        administrative_boundary_audit_status=assessment["status"],
        boundary_input_binding_verified=bool(boundary_audit_ok),
        policy_join_boundary_input_verified=bool(boundary_audit_ok),
        boundary_waste_roster_sha256=assessment.get("waste_roster_sha256",""),
        boundary_monthly_roster_sha256=assessment.get("monthly_roster_sha256",""),
        boundary_audit_reasons=assessment.get("reasons",[]),
        boundary_audit_input_binding_version=assessment.get("input_binding_version"),
        administrative_boundary_audit_geometry_assessed=False,
        reconciliation_rows=len(reconciliation),external_validity="not_assessable_no_compatible_independent_indicator")
    dump(directory/"manifest.json",result)
    return result
