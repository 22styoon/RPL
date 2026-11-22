"""Project a freshly assessed geographic audit into report summary fields."""
from .audit_evidence import assess_boundary_audit


def current_audit_fields(root, cached, *, waste_frame=None, december_frame=None, assessment=None):
    result=assessment if assessment is not None else assess_boundary_audit(root,waste_frame=waste_frame,december_frame=december_frame)
    cached_join_count=int(cached.get("cached_verified_join_rows",cached.get("verified_join_rows",0)))
    join_binding_current=(result["verified"]
        and cached.get("boundary_input_binding_verified") is True
        and cached.get("policy_join_boundary_input_verified") is True
        and bool(result.get("waste_roster_sha256")) and bool(result.get("monthly_roster_sha256"))
        and cached.get("boundary_waste_roster_sha256")==result["waste_roster_sha256"]
        and cached.get("boundary_monthly_roster_sha256")==result["monthly_roster_sha256"])
    return {
        "administrative_boundary_audit_status":result["status"],
        "administrative_boundary_audit_geometry_assessed":False,
        "boundary_input_binding_verified":bool(result["verified"]),
        "boundary_audit_reasons":result.get("reasons",[]),
        "boundary_audit_input_binding_version":result.get("input_binding_version"),
        "boundary_waste_roster_sha256":result.get("waste_roster_sha256",""),
        "boundary_monthly_roster_sha256":result.get("monthly_roster_sha256",""),
        "cached_verified_join_rows":cached_join_count,
        "policy_join_boundary_input_verified":bool(join_binding_current),
        "verified_join_rows":cached_join_count if join_binding_current else 0,
        "policy_outcome_join_status":"geographic_inputs_current_policy_evidence_separate"
            if join_binding_current else "cached_join_binding_unverified_rebuild_required",
        "metadata_code_snapshot":"2024_monthly_code_name_roster_stable_input_binding_verified_geometry_not_assessed"
            if result["verified"] else "current_bound_monthly_audit_not_verified",
    }


def audit_note(summary):
    if summary.get("boundary_input_binding_verified") is True:
        return "2024년 월별 코드·명칭 감사가 현재 입력·원문 증빙과 일치합니다. GIS 경계 도형은 평가하지 않았습니다."
    reasons=", ".join(summary.get("boundary_audit_reasons",[])) or "current_audit_not_verified"
    return ("현재 입력에 연결된 월별 코드·명칭 감사를 확인하지 못했습니다. 과거 감사·정책 결합 건수는 현재의 검증 결과로 인정하지 않습니다. "
            +"상태: "+summary.get("administrative_boundary_audit_status","not_audited")+" / "+reasons)
