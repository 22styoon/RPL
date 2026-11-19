"""Saved reports must not grant a current audit after their inputs change."""
from copy import deepcopy

from src import statistics_ui as ui


def cached_summary():
    return {"sido_rows":17,"sigungu_verified_rows":916,"sigungu_count":229,
            "policy_verified_rows":4,"verified_join_rows":12,
            "administrative_boundary_audit_status":"code_name_roster_stable",
            "administrative_boundary_audit_geometry_assessed":True,
            "boundary_input_binding_verified":True,"policy_join_boundary_input_verified":True,
            "boundary_waste_roster_sha256":"a"*64,"boundary_monthly_roster_sha256":"b"*64}


def current_assessment():
    return {"verified":True,"status":"code_name_roster_stable","reasons":[],
            "waste_roster_sha256":"a"*64,"monthly_roster_sha256":"b"*64,"geometry_assessed":False}


def test_stale_report_loses_current_join_claim_without_changing_policy_evidence(monkeypatch):
    original=cached_summary();before=deepcopy(original)
    monkeypatch.setattr(ui,"assess_boundary_audit",lambda root:{
        "verified":False,"status":"input_changed","reasons":["waste_roster_changed"],"geometry_assessed":False})
    view=ui.live_regional_audit_view(original)
    assert view["administrative_boundary_audit_status"]=="input_changed"
    assert view["boundary_input_binding_verified"] is False
    assert view["verified_join_rows"]==0 and view["cached_verified_join_rows"]==12
    assert view["policy_verified_rows"]==4
    assert view["administrative_boundary_audit_geometry_assessed"] is False
    assert view["boundary_audit_reasons"]==["waste_roster_changed"]
    assert view["cached_report_stale"] is True
    assert original==before


def test_menu_view_reassesses_instead_of_caching_previous_success(monkeypatch):
    responses=iter([
        current_assessment(),
        {"verified":False,"status":"evidence_missing","reasons":["source_page_missing"]},
    ])
    calls=[]
    def assess(root):
        calls.append(root)
        return next(responses)
    monkeypatch.setattr(ui,"assess_boundary_audit",assess)
    first=ui.live_regional_audit_view(cached_summary())
    second=ui.live_regional_audit_view(cached_summary())
    assert first["verified_join_rows"]==12
    assert first["boundary_input_binding_verified"] is True
    assert first["cached_report_stale"] is False
    assert second["verified_join_rows"]==0
    assert second["cached_report_stale"] is True
    assert len(calls)==2


def test_unbound_legacy_summary_cannot_claim_completion_in_county_caption():
    view=ui.live_regional_audit_view(cached_summary(),assessment={
        "verified":False,"status":"input_binding_missing","reasons":["legacy_unbound_audit"]})
    caption=ui.regional_boundary_caption(view,county_report=True)
    assert "229개 시군구" in caption
    assert "현재 입력 유효성을 확인하지 못했습니다" in caption
    assert "현재 입력과 증빙이 일치합니다" not in caption
    assert view["verified_join_rows"]==0


def test_current_bound_audit_can_be_shown_without_geometry_claim():
    assessment=current_assessment();assessment["geometry_assessed"]=True
    view=ui.live_regional_audit_view(cached_summary(),assessment=assessment)
    caption=ui.regional_boundary_caption(view,county_report=True)
    assert "현재 입력과 증빙이 일치합니다" in caption
    assert "GIS 경계 도형과 정책 적용권역은 별도 검증 대상" in caption
    assert view["administrative_boundary_audit_geometry_assessed"] is False
    assert view["policy_join_boundary_input_verified"] is True
    assert view["verified_join_rows"]==12


def test_no_audit_and_zero_cached_join_remain_unverified_without_stale_success_label():
    view=ui.live_regional_audit_view({"policy_verified_rows":2,"verified_join_rows":0},assessment={
        "verified":False,"status":"not_audited","reasons":["audit_manifest_missing"]})
    assert view["verified_join_rows"]==0
    assert view["policy_verified_rows"]==2
    assert view["cached_report_stale"] is False
    assert view["boundary_input_binding_verified"] is False


def test_live_geographic_success_does_not_admit_legacy_join_or_reprojection():
    legacy=cached_summary()
    for field in ("boundary_input_binding_verified","policy_join_boundary_input_verified",
                  "boundary_waste_roster_sha256","boundary_monthly_roster_sha256"):
        legacy.pop(field)
    first=ui.live_regional_audit_view(legacy,assessment=current_assessment())
    second=ui.live_regional_audit_view(first,assessment=current_assessment())
    for view in (first,second):
        assert view["boundary_input_binding_verified"] is True
        assert view["policy_join_boundary_input_verified"] is False
        assert view["policy_outcome_join_status"]=="cached_join_binding_unverified_rebuild_required"
        assert view["cached_verified_join_rows"]==12
        assert view["verified_join_rows"]==0
        assert view["policy_verified_rows"]==4
        assert view["cached_report_stale"] is True


def test_current_audit_with_different_hashes_requires_join_rebuild():
    assessment=current_assessment();assessment["waste_roster_sha256"]="c"*64
    view=ui.live_regional_audit_view(cached_summary(),assessment=assessment)
    assert view["boundary_input_binding_verified"] is True
    assert view["policy_join_boundary_input_verified"] is False
    assert view["verified_join_rows"]==0
    assert view["cached_report_stale"] is True
