import pandas as pd

from src.regional_data.policy_records import POLICY_FIELDS, verified_join


def materials():
    return pd.DataFrame([{
        "sigungu_code":"1111000000","reference_year":2024,"material":"폐지류",
        "generated_t":100.0,"material_recycling_t":50.0,"verification_status":"verified",
        "waste_scope":"household","measurement_stage":"material_recycling_treatment",
        "code_reference_month":"202412",
        "compatibility_status":"2024_code_midyear_boundary_audited",
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
