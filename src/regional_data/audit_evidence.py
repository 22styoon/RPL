"""Bind a code/name audit to the geography inputs and source pages it checked.

Fingerprints describe logical rosters, not population or treatment quantities.
An unbound historical success flag is not accepted as current audit evidence.
"""
from pathlib import Path
import hashlib
import json
import re

import pandas as pd

from src.model import ROOT

BINDING_VERSION = "boundary_rosters_v1"
ROSTER_FIELDS = ("sigungu_code", "sido_name", "sigungu_name")
MONTHS_2024 = {f"2024{month:02d}" for month in range(1, 13)}
MONTHLY_FILE = "data/processed/regional_2024/admin_codes_monthly_2024.csv"
WASTE_FILE = "data/processed/regional_2024/sigungu_2024_materials_verified.csv"


def _canonical_records(frame, *, monthly=False):
    fields = (("reference_month",) if monthly else ()) + ROSTER_FIELDS
    if (not isinstance(frame, pd.DataFrame) or frame.empty or frame.columns.has_duplicates
            or not set(fields).issubset(frame.columns)):
        raise ValueError("roster_fields_or_rows_missing")
    selected = frame[list(fields)].copy()
    if selected.isna().any().any():
        raise ValueError("roster_identity_missing")
    for field in fields:
        selected[field] = selected[field].astype(str).str.strip()
        if selected[field].eq("").any():
            raise ValueError("roster_identity_missing")
    if not selected.sigungu_code.str.fullmatch(r"[0-9]{10}").all():
        raise ValueError("roster_code_invalid")
    if "reference_year" in frame:
        if not frame.reference_year.astype(str).eq("2024").all():
            raise ValueError("roster_reference_year_invalid")
    if monthly and not selected.reference_month.str.fullmatch(r"2024(0[1-9]|1[0-2])").all():
        raise ValueError("roster_reference_month_invalid")
    selected = selected.drop_duplicates()
    scope = ["reference_month"] if monthly else []
    if selected.duplicated([*scope, "sigungu_code"]).any():
        raise ValueError("roster_code_has_ambiguous_names")
    if selected.duplicated([*scope, "sido_name", "sigungu_name"]).any():
        raise ValueError("roster_name_has_ambiguous_codes")
    return fields, selected.sort_values(list(fields), kind="stable").to_dict("records")


def canonical_roster_sha256(frame, monthly=False):
    """Hash unique code/name identities independently of row/material order."""
    fields, records = _canonical_records(frame, monthly=monthly)
    payload = {"version": BINDING_VERSION, "fields": fields, "records": records}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def source_pages_sha256(requests):
    """Bind recorded query parameters and expected bytes for each source page."""
    if not isinstance(requests, list) or not requests:
        raise ValueError("audit_source_requests_missing")
    records = []
    for request in requests:
        if not isinstance(request, dict):
            raise ValueError("audit_source_request_invalid")
        path, digest, parameters = request.get("raw_file"), request.get("sha256"), request.get("parameters")
        if not isinstance(path, str) or not path or not _is_sha256(digest) or not isinstance(parameters, dict):
            raise ValueError("audit_source_request_invalid")
        records.append({"raw_file": path, "sha256": digest, "parameters": parameters})
    if len({record["raw_file"] for record in records}) != len(records):
        raise ValueError("audit_source_page_repeated")
    return hashlib.sha256(json.dumps(sorted(records, key=lambda item: item["raw_file"]),
        ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def make_input_binding(waste_frame, monthly_frame, requests):
    """Create the versioned contract stored by a completed audit run."""
    if not set(monthly_frame.reference_month.astype(str)) == MONTHS_2024:
        raise ValueError("audit_month_coverage_incomplete")
    december = monthly_frame.loc[monthly_frame.reference_month.astype(str).eq("202412")]
    return {"version": BINDING_VERSION,
            "waste_roster_sha256": canonical_roster_sha256(waste_frame),
            "monthly_roster_sha256": canonical_roster_sha256(monthly_frame, monthly=True),
            "december_roster_sha256": canonical_roster_sha256(december),
            "monthly_file": MONTHLY_FILE,
            "source_pages_sha256": source_pages_sha256(requests)}


def _is_sha256(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _safe_path(root, value):
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError("audit_evidence_path_invalid")
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise ValueError("audit_evidence_path_outside_workspace")
    return path


def _read_roster(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _validate_december_month(frame):
    for field in ("reference_month", "code_reference_month"):
        if field in frame and not frame[field].astype(str).eq("202412").all():
            raise ValueError("december_roster_month_mismatch")


def assess_boundary_audit(root=ROOT, *, waste_frame=None, december_frame=None):
    """Reassess stored audit evidence against the currently selected inputs.

    No network or credentials are read. Malformed, missing, legacy, or changed
    evidence fails closed. Geometry and policy exposure remain unassessed.
    """
    root = Path(root).resolve()
    directory = root / "data/processed/regional_2024"
    manifest_path = directory / "boundary_audit_manifest.json"
    result = {"status": "not_audited", "verified": False, "reasons": [],
              "geometry_assessed": False, "input_binding_version": None}

    def fail(status, reason):
        return dict(result, status=status, reasons=[reason])

    if not manifest_path.exists():
        return fail("not_audited", "boundary_audit_manifest_missing")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        if not isinstance(manifest, dict):
            return fail("evidence_invalid", "boundary_audit_manifest_invalid")
        result.update(audit_run_id=manifest.get("run_id"), audited_at=manifest.get("retrieved_at"))
        if manifest.get("status") == "review_required":
            return fail("review_required", "boundary_audit_requires_review")
        if manifest.get("status") != "complete":
            return fail("evidence_invalid", "boundary_audit_not_complete")
        binding = manifest.get("input_binding")
        if not isinstance(binding, dict) or binding.get("version") != BINDING_VERSION:
            return fail("input_binding_missing", "boundary_audit_binding_missing_or_unsupported")
        result["input_binding_version"] = binding["version"]
        required_hashes = ("waste_roster_sha256", "monthly_roster_sha256", "december_roster_sha256", "source_pages_sha256")
        if any(not _is_sha256(binding.get(field)) for field in required_hashes):
            return fail("evidence_invalid", "boundary_audit_binding_hash_invalid")
        summary = manifest.get("summary", {})
        zeros = ("monthly_missing_statistical_codes", "monthly_name_mismatches", "unknown_unmatched_units",
                 "code_roster_changes", "code_name_changes")
        if (manifest.get("reference_year") != 2024 or not isinstance(summary, dict)
                or summary.get("statistical_code_name_roster_stable") is not True
                or summary.get("month_count") != 12 or summary.get("statistical_unit_count") != 229
                or any(summary.get(field) != 0 for field in zeros)):
            return fail("evidence_invalid", "boundary_audit_success_claim_inconsistent")

        if waste_frame is None:
            waste_path = root / WASTE_FILE
            if not waste_path.exists():
                return fail("evidence_missing", "current_waste_roster_missing")
            waste_frame = _read_roster(waste_path)
        waste_digest = canonical_roster_sha256(waste_frame)
        result["waste_roster_sha256"] = waste_digest
        if waste_digest != binding["waste_roster_sha256"]:
            return fail("input_changed", "current_waste_roster_changed")

        monthly_path = _safe_path(root, binding.get("monthly_file"))
        if manifest.get("artifacts", {}).get("monthly") != binding["monthly_file"]:
            return fail("evidence_invalid", "monthly_artifact_binding_mismatch")
        if not monthly_path.exists():
            return fail("evidence_missing", "monthly_roster_evidence_missing")
        monthly = _read_roster(monthly_path)
        monthly_digest = canonical_roster_sha256(monthly, monthly=True)
        result["monthly_roster_sha256"] = monthly_digest
        if monthly_digest != binding["monthly_roster_sha256"]:
            return fail("input_changed", "monthly_roster_evidence_changed")
        if set(monthly.reference_month.astype(str)) != MONTHS_2024:
            return fail("evidence_invalid", "monthly_roster_coverage_incomplete")
        december = monthly.loc[monthly.reference_month.astype(str).eq("202412")]
        december_digest = canonical_roster_sha256(december)
        if december_digest != binding["december_roster_sha256"]:
            return fail("evidence_invalid", "december_audit_binding_mismatch")

        if december_frame is not None:
            _validate_december_month(december_frame)
            if canonical_roster_sha256(december_frame) != december_digest:
                return fail("input_changed", "selected_december_roster_changed")
        active_december_path = directory / "admin_codes_202412.csv"
        if december_frame is None and active_december_path.exists():
            active_december = _read_roster(active_december_path)
            _validate_december_month(active_december)
            if canonical_roster_sha256(active_december) != december_digest:
                return fail("input_changed", "active_december_roster_changed")
        checkpoint = root / "data/raw/regional_2024/kr_admin_codes_2024/checkpoint.json"
        if checkpoint.exists():
            from .geocodes import normalize_mois_roster
            state = json.loads(checkpoint.read_text(encoding="utf-8-sig"))
            active_source = normalize_mois_roster(state)
            if canonical_roster_sha256(active_source) != december_digest:
                return fail("input_changed", "active_mois_checkpoint_roster_changed")

        requests = manifest.get("requests")
        if source_pages_sha256(requests) != binding["source_pages_sha256"]:
            return fail("evidence_invalid", "source_page_binding_changed")
        for request in requests:
            path = _safe_path(root, request["raw_file"])
            if not path.exists():
                return fail("evidence_missing", "audit_source_page_missing")
            if hashlib.sha256(path.read_bytes()).hexdigest() != request["sha256"]:
                return fail("input_changed", "audit_source_page_changed")
        return dict(result, status="code_name_roster_stable", verified=True, reasons=[])
    except (ValueError, TypeError, KeyError, AttributeError, OSError):
        return fail("evidence_invalid", "boundary_audit_evidence_invalid")
