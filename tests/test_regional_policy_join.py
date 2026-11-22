import pandas as pd
import pytest

from src.regional_data.policy_records import POLICY_FIELDS, verified_join


def materials():
    return pd.DataFrame([{
        "sigungu_code":"1111000000","reference_year":2024,"material":"폐지류",
        "generated_t":100.0,"material_recycling_t":50.0,"verification_status":"verified",
        "waste_scope":"household","measurement_stage":"material_recycling_treatment",
        "code_reference_month":"202412",
        "compatibility_status":"2024_monthly_MOIS_code_name_roster_stable; input_binding_verified; geometry_not_assessed",
        "boundary_input_binding_verified":True,
        "source_url":"https://example.gov/data","source_locator":"table 1"
    }])


def policy(**override):
    result={"policy_id":"p1","policy_name":"sample test only","policy_category":"separate collection",
        "reference_year":2024,"sigungu_code":"1111000000","implemented_in_2024":True,
        "start_date":"2024-01-01","end_date":"2024-12-31","target_materials":"폐지류",
        "collection_mode":"test","operating_entity":"test","coverage_level":"sigungu_full",
        "coverage_description":"unit test fixture","waste_scope":"household",
        "measurement_stage":"material_recycling_treatment","scope_verified":True,
        "code_reference_month":"202412","administrative_boundary_verified":True,
        "boundary_source_url":"https://example.gov/codes","boundary_source_locator":"2024 history",
        "source_url":"https://example.gov/policy","source_locator":"paragraph 1",
        "retrieved_at":"2026-11-16T00:00:00+09:00","evidence_status":"verified"}
    result.update(override)
    return result


def test_join_requires_boundary_audit_and_evidence():
    joined,rejected=verified_join(materials(),pd.DataFrame([policy()]))
    assert len(joined)==1 and joined.iloc[0].verification_status=="verified_join"
    assert rejected.empty
    joined,rejected=verified_join(materials(),pd.DataFrame([policy(administrative_boundary_verified=False)]))
    assert joined.empty
    assert "administrative_boundary_unverified" in rejected.iloc[0].reason


def test_missing_policy_dates_do_not_imply_full_year_coverage():
    joined,rejected=verified_join(materials(),pd.DataFrame([policy(end_date=pd.NA)]))
    assert joined.empty
    assert "dates_unverified" in rejected.iloc[0].reason


def test_year_end_name_match_is_not_midyear_boundary_proof():
    frame=materials()
    frame.loc[0,"compatibility_status"]="name_and_202412_code_match_midyear_boundary_not_audited"
    joined,rejected=verified_join(frame,pd.DataFrame([policy()]))
    assert joined.empty
    assert "data_boundary_audit_missing" in rejected.iloc[0].reason


def test_empty_policy_schema_has_boundary_provenance_fields():
    assert "administrative_boundary_verified" in POLICY_FIELDS
    assert "boundary_source_locator" in POLICY_FIELDS


@pytest.mark.parametrize("status",[
    None,pd.NA,"","unknown","review_required","input_changed",
    "2024_code_midyear_boundary_audited",
    "2024_monthly_MOIS_code_name_roster_stable; geometry_not_assessed",
    "2024_monthly_MOIS_code_name_roster_unstable; input_binding_verified; geometry_not_assessed",
    "not_2024_monthly_MOIS_code_name_roster_stable; input_binding_verified; geometry_not_assessed",
    "2024_monthly_MOIS_code_name_roster_stable; input_binding_verified; geometry_not_assessed; review_required",
    "2024_monthly_MOIS_code_name_roster_stable; input_binding_verified; geometry_not_assessed; input_changed",
    "2024_monthly_MOIS_code_name_roster_stable; input_binding_verified; geometry_not_assessed; not_audited",
])
def test_policy_evidence_cannot_override_unknown_or_negative_outcome_audit(status):
    frame=materials().astype({"compatibility_status":object})
    frame.loc[0,"compatibility_status"]=status
    joined,rejected=verified_join(frame,pd.DataFrame([policy()]))
    assert joined.empty
    assert "data_boundary_audit_missing" in rejected.iloc[0].reason


@pytest.mark.parametrize("value",[None,pd.NA,False,"false","False","0",0,1,"1","yes","not true"])
def test_binding_requires_explicit_true_not_a_truthy_value(value):
    frame=materials().astype({"boundary_input_binding_verified":object})
    frame.loc[0,"boundary_input_binding_verified"]=value
    joined,rejected=verified_join(frame,pd.DataFrame([policy()]))
    assert joined.empty
    assert "data_boundary_input_binding_unverified" in rejected.iloc[0].reason


@pytest.mark.parametrize("column",["compatibility_status","boundary_input_binding_verified"])
def test_missing_audit_contract_column_is_not_verified(column):
    joined,rejected=verified_join(materials().drop(columns=column),pd.DataFrame([policy()]))
    assert joined.empty
    assert "data_boundary_" in rejected.iloc[0].reason


@pytest.mark.parametrize("value",[True,"true"," True "])
def test_bound_audit_marker_allows_known_nested_unit_annotation(value):
    frame=materials().astype({"boundary_input_binding_verified":object})
    frame.loc[0,"boundary_input_binding_verified"]=value
    frame.loc[0,"compatibility_status"]+="; 35_nested_general_districts_excluded"
    joined,rejected=verified_join(frame,pd.DataFrame([policy()]))
    assert len(joined)==1 and rejected.empty


def test_a_single_unbound_selected_outcome_prevents_policy_join():
    frame=pd.concat([materials(),materials().assign(material="폐유리류",boundary_input_binding_verified=False)],ignore_index=True)
    joined,rejected=verified_join(frame,pd.DataFrame([policy(target_materials="폐지류;폐유리류")]))
    assert joined.empty
    assert "data_boundary_input_binding_unverified" in rejected.iloc[0].reason


def test_no_matching_outcomes_cannot_use_empty_all_as_audit_success():
    frame=materials().iloc[:0].drop(columns=["compatibility_status","boundary_input_binding_verified"])
    joined,rejected=verified_join(frame,pd.DataFrame([policy()]))
    assert joined.empty
    assert rejected.iloc[0].reason=="no_matching_verified_material"


def test_target_material_must_exist_even_with_verified_audit():
    joined,rejected=verified_join(materials(),pd.DataFrame([policy(target_materials="폐유리류")]))
    assert joined.empty
    assert rejected.iloc[0].reason=="no_matching_verified_material"
