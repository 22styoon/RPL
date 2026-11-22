"""Audit reuse must follow the current logical geography and preserved sources."""
import hashlib
import json

import pandas as pd
import pytest

from src.regional_data import boundary_audit
from src.regional_data.audit_evidence import (
    BINDING_VERSION, MONTHLY_FILE, WASTE_FILE, assess_boundary_audit,
    canonical_roster_sha256, make_input_binding, source_pages_sha256,
)


@pytest.fixture
def bound_audit(tmp_path):
    # Constructed code/name units and a local source page, not observed cities.
    waste = pd.DataFrame([{"sigungu_code": f"11{i:04d}0000", "sido_name": "서울",
                           "sigungu_name": f"가상구{i:03d}", "reference_year": 2024,
                           "material": "폐지류", "generated_t": 100, "material_recycling_t": 50}
                          for i in range(1, 230)])
    monthly = pd.concat([waste[["sigungu_code", "sido_name", "sigungu_name"]].assign(reference_month=f"2024{month:02d}")
                         for month in range(1, 13)], ignore_index=True)
    waste_path, monthly_path = tmp_path / WASTE_FILE, tmp_path / MONTHLY_FILE
    waste_path.parent.mkdir(parents=True)
    waste.to_csv(waste_path, index=False, encoding="utf-8-sig")
    monthly.to_csv(monthly_path, index=False, encoding="utf-8-sig")
    raw_relative = "data/raw/regional_2024/audit_fixture/page.json"
    raw_path = tmp_path / raw_relative
    raw_path.parent.mkdir(parents=True)
    raw_path.write_text(json.dumps({"constructed_local_evidence": True}), encoding="utf-8")
    requests = [{"raw_file": raw_relative, "sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                 "parameters": {"fixture": "local-source-integrity"}}]
    manifest = {"reference_year": 2024, "status": "complete", "run_id": "constructed-test",
                "retrieved_at": "2026-11-19T00:00:00+09:00",
                "summary": {"month_count": 12, "statistical_unit_count": 229,
                            "statistical_code_name_roster_stable": True,
                            **dict.fromkeys(["monthly_missing_statistical_codes", "monthly_name_mismatches",
                                             "unknown_unmatched_units", "code_roster_changes", "code_name_changes"], 0)},
                "requests": requests, "artifacts": {"monthly": MONTHLY_FILE},
                "input_binding": make_input_binding(waste, monthly, requests)}
    path = waste_path.parent / "boundary_audit_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return {"root": tmp_path, "waste": waste, "monthly": monthly, "manifest": manifest,
            "manifest_path": path, "raw_path": raw_path, "waste_path": waste_path, "monthly_path": monthly_path}


def test_canonical_roster_ignores_row_order_material_duplication_and_non_geography_fields():
    frame = pd.DataFrame([{"sigungu_code": "1111000000", "sido_name": "서울", "sigungu_name": "가상구",
                           "material": "paper", "population": 10},
                          {"sigungu_code": "1114000000", "sido_name": "서울", "sigungu_name": "다른구",
                           "material": "plastic", "population": 20}])
    altered = pd.concat([frame.iloc[::-1], frame]).copy()
    altered["material"] = "different"
    altered["population"] = 999
    altered["compatibility_status"] = "changed_metadata"
    assert canonical_roster_sha256(frame) == canonical_roster_sha256(altered)


@pytest.mark.parametrize("kind", ["missing", "empty", "ambiguous_code", "ambiguous_name", "wrong_year", "wrong_month"])
def test_canonical_roster_rejects_missing_and_ambiguous_identities(kind):
    frame = pd.DataFrame([{"sigungu_code": "1111000000", "sido_name": "서울", "sigungu_name": "가상구",
                           "reference_month": "202412"}])
    monthly = False
    if kind == "missing": frame.loc[0, "sigungu_name"] = pd.NA
    elif kind == "empty": frame.loc[0, "sigungu_code"] = " "
    elif kind == "ambiguous_code": frame = pd.concat([frame, frame.assign(sigungu_name="다른구")])
    elif kind == "ambiguous_name": frame = pd.concat([frame, frame.assign(sigungu_code="1114000000")])
    elif kind == "wrong_year": frame["reference_year"] = 2025
    else: frame["reference_month"] = "202501"; monthly = True
    with pytest.raises(ValueError): canonical_roster_sha256(frame, monthly=monthly)


def test_bound_current_evidence_is_verified_without_claiming_geometry(bound_audit):
    result = assess_boundary_audit(bound_audit["root"])
    assert result["verified"] and result["status"] == "code_name_roster_stable"
    assert result["input_binding_version"] == BINDING_VERSION
    assert result["geometry_assessed"] is False and not result["reasons"]
    changed_quantities = bound_audit["waste"].assign(generated_t=1000, material_recycling_t=200)
    assert assess_boundary_audit(bound_audit["root"], waste_frame=changed_quantities)["verified"]


def test_roster_reordering_and_population_updates_do_not_stale_the_audit(bound_audit):
    monthly = bound_audit["monthly"].iloc[::-1].assign(population=999999, households=100)
    monthly.to_csv(bound_audit["monthly_path"], index=False, encoding="utf-8-sig")
    waste = pd.concat([bound_audit["waste"].iloc[::-1], bound_audit["waste"].assign(material="폐유리류")])
    waste.to_csv(bound_audit["waste_path"], index=False, encoding="utf-8-sig")
    assert assess_boundary_audit(bound_audit["root"])["verified"]


def test_duplicate_column_schema_is_rejected_as_invalid_roster():
    frame = pd.DataFrame([["1111000000", "1114000000", "서울", "가상구"]],
                         columns=["sigungu_code", "sigungu_code", "sido_name", "sigungu_name"])
    with pytest.raises(ValueError): canonical_roster_sha256(frame)


@pytest.mark.parametrize("target,expected_status", [("waste", "input_changed"), ("monthly", "input_changed"), ("raw", "input_changed")])
def test_changed_selected_inputs_cannot_reuse_success(bound_audit, target, expected_status):
    if target == "waste":
        frame = bound_audit["waste"].copy(); frame.loc[0, "sigungu_name"] = "변경구"
        frame.to_csv(bound_audit["waste_path"], index=False, encoding="utf-8-sig")
    elif target == "monthly":
        frame = bound_audit["monthly"].copy(); frame.loc[0, "sigungu_name"] = "변경구"
        frame.to_csv(bound_audit["monthly_path"], index=False, encoding="utf-8-sig")
    else: bound_audit["raw_path"].write_bytes(b"changed-source")
    result = assess_boundary_audit(bound_audit["root"])
    assert not result["verified"] and result["status"] == expected_status


@pytest.mark.parametrize("target", ["waste_path", "monthly_path", "raw_path"])
def test_missing_evidence_fails_closed(bound_audit, target):
    bound_audit[target].unlink()
    result = assess_boundary_audit(bound_audit["root"])
    assert not result["verified"] and result["status"] == "evidence_missing"


def test_legacy_success_requires_new_input_binding(bound_audit):
    manifest = bound_audit["manifest"]
    del manifest["input_binding"]
    bound_audit["manifest_path"].write_text(json.dumps(manifest), encoding="utf-8")
    result = assess_boundary_audit(bound_audit["root"])
    assert result["status"] == "input_binding_missing" and not result["verified"]


def test_review_required_and_inconsistent_success_flags_are_not_verified(bound_audit):
    manifest = bound_audit["manifest"]
    manifest["status"] = "review_required"
    bound_audit["manifest_path"].write_text(json.dumps(manifest), encoding="utf-8")
    assert assess_boundary_audit(bound_audit["root"])["status"] == "review_required"
    manifest["status"] = "complete"; manifest["summary"]["monthly_name_mismatches"] = 1
    bound_audit["manifest_path"].write_text(json.dumps(manifest), encoding="utf-8")
    assert assess_boundary_audit(bound_audit["root"])["status"] == "evidence_invalid"


def test_current_december_snapshot_and_explicit_preparation_input_are_compared(bound_audit):
    december = bound_audit["monthly"].loc[bound_audit["monthly"].reference_month.eq("202412")].copy()
    active = december.assign(code_reference_month="202412")
    path = bound_audit["waste_path"].parent / "admin_codes_202412.csv"
    active.to_csv(path, index=False, encoding="utf-8-sig")
    assert assess_boundary_audit(bound_audit["root"])["verified"]
    active.iloc[0, active.columns.get_loc("sigungu_name")] = "변경구"
    active.to_csv(path, index=False, encoding="utf-8-sig")
    assert assess_boundary_audit(bound_audit["root"])["status"] == "input_changed"
    assert assess_boundary_audit(bound_audit["root"], december_frame=december)["verified"]


def test_mois_checkpoint_changes_are_checked_logically_not_by_population(bound_audit):
    december = bound_audit["monthly"].loc[bound_audit["monthly"].reference_month.eq("202412")]
    state = {"records": [{"admmCd": row.sigungu_code, "statsYm": "202412", "ctpvNm": "서울특별시",
                           "sggNm": row.sigungu_name, "totNmprCnt": 100, "hhCnt": 50}
                          for row in december.itertuples(index=False)]}
    path = bound_audit["root"] / "data/raw/regional_2024/kr_admin_codes_2024/checkpoint.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(state), encoding="utf-8")
    assert assess_boundary_audit(bound_audit["root"])["verified"]
    state["records"][0]["totNmprCnt"] = 200
    path.write_text(json.dumps(state), encoding="utf-8")
    assert assess_boundary_audit(bound_audit["root"])["verified"]
    state["records"][0]["totNmprCnt"] = ""
    state["records"][0]["hhCnt"] = "not_a_population_observation"
    path.write_text(json.dumps(state), encoding="utf-8")
    assert assess_boundary_audit(bound_audit["root"])["verified"]
    state["records"][0]["sggNm"] = "변경구"
    path.write_text(json.dumps(state), encoding="utf-8")
    assert assess_boundary_audit(bound_audit["root"])["status"] == "input_changed"


def test_manifest_paths_cannot_escape_workspace(bound_audit):
    manifest = bound_audit["manifest"]
    manifest["requests"][0]["raw_file"] = "../outside-source.json"
    manifest["input_binding"]["source_pages_sha256"] = source_pages_sha256(manifest["requests"])
    bound_audit["manifest_path"].write_text(json.dumps(manifest), encoding="utf-8")
    result = assess_boundary_audit(bound_audit["root"])
    assert result["status"] == "evidence_invalid" and not result["verified"]


def test_modified_source_request_record_cannot_reuse_the_old_binding(bound_audit):
    manifest = bound_audit["manifest"]
    manifest["requests"][0]["parameters"]["fixture"] = "different-scope"
    bound_audit["manifest_path"].write_text(json.dumps(manifest), encoding="utf-8")
    result = assess_boundary_audit(bound_audit["root"])
    assert result["status"] == "evidence_invalid"
    assert result["reasons"] == ["source_page_binding_changed"]


def test_missing_or_malformed_manifest_has_an_explicit_status(tmp_path):
    assert assess_boundary_audit(tmp_path)["status"] == "not_audited"
    directory = tmp_path / "data/processed/regional_2024"; directory.mkdir(parents=True)
    (directory / "boundary_audit_manifest.json").write_text("not json", encoding="utf-8")
    assert assess_boundary_audit(tmp_path)["status"] == "evidence_invalid"


def test_audit_run_binds_its_outputs_and_rerun_has_same_logical_fingerprints(tmp_path, monkeypatch):
    directory = tmp_path / "data/processed/regional_2024"; directory.mkdir(parents=True)
    waste = pd.DataFrame([{"sido_name": "서울", "sigungu_name": f"가상구{i:03d}", "sigungu_code": f"11{i:04d}0000"}
                          for i in range(1, 230)])
    waste.to_csv(tmp_path / WASTE_FILE, index=False, encoding="utf-8-sig")
    monkeypatch.setattr(boundary_audit, "ROOT_CODES", ("11",))
    monkeypatch.setattr(boundary_audit, "load_mois_key", lambda root: "fixture")

    def fetch(key, params, *, timeout):
        rows = [{"admmCd": row.sigungu_code, "statsYm": f"2024{month:02d}",
                 "ctpvNm": "서울특별시", "sggNm": row.sigungu_name}
                for month in range(int(params["srchFrYm"][-2:]), int(params["srchToYm"][-2:]) + 1)
                for row in waste.itertuples(index=False)]
        begin = (params["pageNo"] - 1) * params["numOfRows"]
        payload = {"Response": {"head": {"resultCode": "0", "pageNo": params["pageNo"], "totalCount": len(rows)},
                                "items": {"item": rows[begin:begin + params["numOfRows"]]}}}
        return json.dumps(payload).encode("utf-8"), payload

    monkeypatch.setattr(boundary_audit, "_fetch_page", fetch)
    first = boundary_audit.run_boundary_audit(root=tmp_path, delay_seconds=0)
    assert first["input_binding"]["version"] == BINDING_VERSION
    assert assess_boundary_audit(tmp_path)["verified"]
    second = boundary_audit.run_boundary_audit(root=tmp_path, delay_seconds=0)
    assert first["input_binding"] == second["input_binding"]
    assert assess_boundary_audit(tmp_path)["verified"]


def _prepare_fixture(bound_audit, monkeypatch):
    """Synthetic county inputs; retain real tracked national source structure."""
    from src.model import ROOT
    from src.regional_data import prepare as preparation
    root=bound_audit["root"]
    for relative in ["data/processed/kosis_materials_2024.csv",
                     "data/raw/kosis/DT_106N_29_2020005_metadata.json",
                     "configs/regional_indicator.yaml"]:
        path=root/relative;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes((ROOT/relative).read_bytes())
    units=bound_audit["waste"][["sido_name","sigungu_name","sigungu_code"]]
    state={"retrieved_at":"2026-11-20T00:00:00+09:00", "records":[
        {"admmCd":row.sigungu_code,"statsYm":"202412","ctpvNm":"서울특별시","sggNm":row.sigungu_name}
        for row in units.itertuples(index=False)]}
    checkpoint=root/"data/raw/regional_2024/kr_admin_codes_2024/checkpoint.json"
    checkpoint.parent.mkdir(parents=True,exist_ok=True)
    checkpoint.write_text(json.dumps(state),encoding="utf-8")
    latest=root/"data/raw/regional_2024/kr_waste_2024_detail/latest.json"
    latest.parent.mkdir(parents=True,exist_ok=True)
    latest.write_text(json.dumps({"raw_file":bound_audit["raw_path"].relative_to(root).as_posix(),
                                 "sha256":hashlib.sha256(bound_audit["raw_path"].read_bytes()).hexdigest()}),encoding="utf-8")
    parsed=pd.concat([units.drop(columns="sigungu_code").assign(
        material=material,reference_year=2024,generated_t=100.,material_recycling_t=50.,
        source_id="constructed_fixture",source_url="https://example.gov/fixture",source_locator="synthetic unit",
        retrieved_at="2026-11-20T00:00:00+09:00",verification_status="source_cells_parsed",
        compatibility_status="pending",measurement_stage="material_recycling_treatment",waste_scope="household")
        for material in ("폐지류","폐합성수지류","폐금속류","폐유리류")],ignore_index=True)
    monkeypatch.setattr(preparation,"parse_counties",lambda raw,manifest:parsed.copy())
    return preparation,parsed


def test_preparation_assesses_current_parsed_roster_before_granting_binding(bound_audit,monkeypatch):
    preparation,parsed=_prepare_fixture(bound_audit,monkeypatch)
    first=preparation.prepare(root=bound_audit["root"])
    assert first["sigungu_verified_regions"]==229
    assert first["boundary_input_binding_verified"] is True
    assert first["policy_join_boundary_input_verified"] is True
    # New source parsing no longer matches the previously audited county roster.
    parsed.loc[parsed.sigungu_name.eq("가상구001"),"sigungu_name"]="수정된가상구"
    second=preparation.prepare(root=bound_audit["root"])
    assert second["sigungu_verified_regions"]==228
    assert second["administrative_boundary_audit_status"]=="input_changed"
    assert second["boundary_input_binding_verified"] is False
    current=pd.read_csv(bound_audit["waste_path"])
    assert not current.boundary_input_binding_verified.any()


def test_report_rechecks_sources_and_withholds_stale_join_count(bound_audit,monkeypatch,tmp_path):
    from src.analysis.regional_indicator_report import run
    preparation,_=_prepare_fixture(bound_audit,monkeypatch)
    preparation.prepare(root=bound_audit["root"])
    path=bound_audit["waste_path"].parent/"manifest.json"
    metadata=json.loads(path.read_text(encoding="utf-8"))
    metadata.update(verified_join_rows=12,policy_verified_rows=4)
    path.write_text(json.dumps(metadata),encoding="utf-8")
    bound_audit["raw_path"].write_text("changed source page",encoding="utf-8")
    # The workbook fixture uses this same local page; keep its separate workbook
    # input hash valid so the failure under test is the monthly audit evidence.
    latest=bound_audit["root"]/"data/raw/regional_2024/kr_waste_2024_detail/latest.json"
    workbook=json.loads(latest.read_text(encoding="utf-8"))
    workbook["sha256"]=hashlib.sha256(bound_audit["raw_path"].read_bytes()).hexdigest()
    latest.write_text(json.dumps(workbook),encoding="utf-8")
    report=run(root=bound_audit["root"],output_root=tmp_path/"report")
    summary=report["summary"]
    assert summary["administrative_boundary_audit_status"]=="input_changed"
    assert summary["boundary_input_binding_verified"] is False
    assert summary["verified_join_rows"]==0 and summary["cached_verified_join_rows"]==12
    assert summary["policy_verified_rows"]==4


def test_projection_does_not_restore_historical_joins_after_evidence_returns(bound_audit):
    from src.regional_data.audit_reporting import current_audit_fields
    assessment=assess_boundary_audit(bound_audit["root"])
    cached={"verified_join_rows":12,"policy_verified_rows":4,"boundary_input_binding_verified":True,
            "policy_join_boundary_input_verified":True,
            "boundary_waste_roster_sha256":assessment["waste_roster_sha256"],
            "boundary_monthly_roster_sha256":assessment["monthly_roster_sha256"]}
    assert current_audit_fields(bound_audit["root"],cached)["verified_join_rows"]==12
    raw=bound_audit["raw_path"].read_bytes()
    bound_audit["raw_path"].write_bytes(b"changed")
    withheld=current_audit_fields(bound_audit["root"],cached)
    bound_audit["raw_path"].write_bytes(raw)
    repeated=current_audit_fields(bound_audit["root"],dict(cached,**withheld))
    assert repeated["boundary_input_binding_verified"] is True
    assert repeated["policy_join_boundary_input_verified"] is False
    assert repeated["verified_join_rows"]==0 and repeated["cached_verified_join_rows"]==12
