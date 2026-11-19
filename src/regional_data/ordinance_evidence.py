"""Local, source-bound ordinance article references; never policy exposure."""
from datetime import datetime
from pathlib import Path
import hashlib
import json
import re

import pandas as pd

from src.model import ROOT
from .audit_evidence import canonical_roster_sha256
from .law_client import _get, _walk, normalize_legal_title
from .policy_geography import link_ordinance_geography

DIRECTORY = "data/processed/regional_2024"
LATEST = "data/raw/regional_2024/law_ordinances/latest.json"
BINDING_VERSION = "ordinance_articles_v1"
TEMPORAL_SCOPE = "2024_effective_start_history_search_not_full_year_exposure"
DETAIL_ACCEPTED = "document_identity_and_body_validated_operational_policy_unverified"
ARTICLE_FIELDS = ("ordinance_id", "ordinance_serial", "policy_name", "locality",
    "effective_date", "promulgation_date", "amendment_type", "matched_sigungu_code_2024",
    "geography_match_status", "article_number", "article_title", "text_field", "article_text",
    "materials_mentioned", "topics_mentioned", "source_url", "api_source_url", "source_locator",
    "raw_detail_file", "raw_detail_sha256", "json_pointer", "legal_version_status")
COUNT_FIELDS = {
    "law_ordinance_version_candidates": "ordinance_version_rows",
    "law_ordinance_unique_ids": "unique_ordinance_ids",
    "law_ordinance_matched_statistical_unit_rows": "matched_waste_statistical_unit_rows",
    "law_ordinance_sido_only_rows": "sido_only_rows",
    "law_ordinance_unmatched_rows": "unmatched_locality_rows",
    "law_ordinance_detail_json_count": "ordinance_detail_json_count",
    "law_verified_document_version_rows": "verified_document_version_rows",
    "law_article_evidence_rows": "article_evidence_rows",
    "law_keyword_article_rows": "keyword_article_rows",
    "law_citation_regions": "citation_regions",
}
MATERIAL_TERMS = {"paper": ("종이",), "glass": ("유리",),
    "metal": ("금속", "캔류", "고철", "알루미늄", "철캔"),
    "plastic": ("플라스틱", "합성수지", "페트", "비닐")}
TOPICS = ("분리배출", "분리수거", "수거", "수집", "운반", "재활용", "재생원료")


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read_csv(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _safe_path(root, value):
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError("ORDINANCE_EVIDENCE_PATH_INVALID")
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise ValueError("ORDINANCE_EVIDENCE_PATH_INVALID")
    return path


def _nodes(value, pointer=""):
    if isinstance(value, dict):
        yield pointer, value
        for key, item in value.items():
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            yield from _nodes(item, pointer + "/" + escaped)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _nodes(item, pointer + "/" + str(index))


def _label(value):
    if isinstance(value, list):
        return ";".join(dict.fromkeys(str(item) for item in value))
    return str(value or "")


def public_ordinance_url(serial):
    """Pin the public, credential-free viewer to the listed history serial."""
    serial = str(serial or "")
    return "https://www.law.go.kr/LSW/ordinInfoP.do?ordinSeq=" + serial if re.fullmatch(r"\d+", serial) else ""


def _effective_start_matches(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{8}", value):
        return False
    try:
        return datetime.strptime(value, "%Y%m%d").year == 2024
    except ValueError:
        return False


def _version_status(payload, row):
    if not row.get("ordinance_serial"):
        return "id_only_version_unresolved"
    expected = {"serial": row["ordinance_serial"], "name": row.get("policy_name", ""),
        "locality": row.get("locality", ""), "effective": row.get("effective_date", ""),
        "promulgated": row.get("promulgation_date", "")}
    if not all(expected.values()) or not _effective_start_matches(expected["effective"]):
        return "version_metadata_incomplete_review_required"
    if any(all((normalize_legal_title(_get(node, field)) == normalize_legal_title(value))
               if field == "name" else _get(node, field) == value for field, value in expected.items())
           for node in _walk(payload) if isinstance(node, dict)):
        return "version_metadata_matched"
    return "version_metadata_incomplete_review_required"


def extract_article_evidence(payload, candidate, *, raw_sha256):
    """Keep exact returned text and JSON locations; mentions are review hints."""
    rows = []
    version_status = _version_status(payload, candidate)
    content_fields = {"조내용", "부칙내용", "개정문내용", "제개정이유내용"}
    for pointer, node in _nodes(payload):
        for field in sorted(content_fields & node.keys()):
            text = node[field]
            if not isinstance(text, str) or not text.strip():
                continue
            record = {key: candidate.get(key, "") for key in ARTICLE_FIELDS}
            record.update(article_number=_label(node.get("조문번호", "")),
                article_title=_label(node.get("조제목", "")), text_field=field,
                article_text=text, raw_detail_file=candidate.get("detail_raw_file", ""),
                raw_detail_sha256=raw_sha256, json_pointer=pointer + "/" + field,
                legal_version_status=version_status,
                materials_mentioned=";".join(material for material, terms in MATERIAL_TERMS.items()
                    if any(term in text for term in terms)),
                topics_mentioned=";".join(term for term in TOPICS if term in text))
            rows.append(record)
    return rows, version_status


def _review_counts(linked, articles):
    return {
        "verified_document_version_rows": int(linked.legal_version_status.eq("version_metadata_matched").sum()),
        "article_evidence_rows": len(articles),
        "keyword_article_rows": int(articles.topics_mentioned.ne("").sum()),
        "citation_regions": int(articles.loc[articles.geography_match_status.eq(
            "matched_2024_waste_statistical_unit"), "matched_sigungu_code_2024"].nunique()),
    }


def link_ordinance_evidence(root=ROOT):
    """Build geography crosswalk and article references from validated sources."""
    from .law_client import validate_collection_evidence
    root = Path(root).resolve()
    directory = root / DIRECTORY
    candidate_path = directory / "policy_ordinance_candidates.csv"
    manifest_path = root / LATEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_collection_evidence(root, manifest, candidate_csv=candidate_path)
    candidates = _read_csv(candidate_path)
    codes = _read_csv(directory / "admin_codes_202412.csv")
    waste = _read_csv(directory / "sigungu_2024_materials_verified.csv")
    linked, summary = link_ordinance_geography(candidates, codes, waste)
    # The API detail URL needs OC. Keep it as provenance, and give people the
    # public viewer for the same MST instead of a broken credential-less API URL.
    linked["api_source_url"] = linked.source_url
    linked["source_url"] = linked.ordinance_serial.map(public_ordinance_url)
    articles = []
    versions = []
    for candidate in linked.to_dict("records"):
        status = "detail_not_validated"
        if candidate.get("detail_status") == DETAIL_ACCEPTED and candidate.get("detail_raw_file"):
            path = _safe_path(root, candidate["detail_raw_file"])
            payload = json.loads(path.read_text(encoding="utf-8"))
            extracted, status = extract_article_evidence(payload, candidate, raw_sha256=_sha(path))
            articles.extend(extracted)
        versions.append(status)
    linked["legal_version_status"] = versions
    linked["effective_start_in_2024"] = linked.effective_date.map(_effective_start_matches)
    linked["legal_effect_interval_status"] = "effective_start_only_end_and_transitions_unverified"
    article_frame = pd.DataFrame(articles, columns=ARTICLE_FIELDS)
    crosswalk_path = directory / "policy_ordinance_geography_crosswalk.csv"
    articles_path = directory / "policy_ordinance_article_evidence.csv"
    linked.to_csv(crosswalk_path, index=False, encoding="utf-8-sig")
    article_frame.to_csv(articles_path, index=False, encoding="utf-8-sig")
    summary.update(law_api_status=manifest.get("status", "unknown"),
        law_api_pages=manifest.get("pages_used", 0),
        ordinance_detail_json_count=manifest.get("detail_count", 0),
        ordinance_effective_date_filter=manifest.get("effective_date_filter", ""),
        law_api_retrieved_at=manifest.get("retrieved_at", ""), law_api_source_manifest=LATEST,
        crosswalk_csv=crosswalk_path.relative_to(root).as_posix(),
        article_evidence_csv=articles_path.relative_to(root).as_posix(),
        effective_start_in_2024_rows=int(linked.effective_start_in_2024.sum()),
        temporal_scope=TEMPORAL_SCOPE,
        article_interpretation="literal legal text and keyword mentions only; material, duration, implementation and policy effect require review")
    summary.update(_review_counts(linked, article_frame))
    summary["input_binding"] = {"version": BINDING_VERSION,
        "candidate_sha256": _sha(candidate_path), "source_manifest_sha256": _sha(manifest_path),
        "codes_roster_sha256": canonical_roster_sha256(codes),
        "waste_roster_sha256": canonical_roster_sha256(waste),
        "crosswalk_sha256": _sha(crosswalk_path), "article_evidence_sha256": _sha(articles_path)}
    (directory / "policy_ordinance_candidate_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def assess_ordinance_linkage(root=ROOT):
    """Read-only reassessment; a saved summary alone never establishes success."""
    from .law_client import validate_collection_evidence
    root = Path(root).resolve()
    directory = root / DIRECTORY
    result = {"verified": False, "status": "not_linked", "reasons": [], "summary": {}}
    try:
        summary_path = directory / "policy_ordinance_candidate_summary.json"
        if not summary_path.exists():
            return dict(result, reasons=["ordinance_linkage_summary_missing"])
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if not isinstance(summary, dict):
            raise ValueError("ORDINANCE_LINKAGE_SUMMARY_INVALID")
        result["summary"] = summary
        binding = summary.get("input_binding", {})
        if not isinstance(binding, dict) or binding.get("version") != BINDING_VERSION:
            return dict(result, status="input_binding_missing", reasons=["ordinance_linkage_binding_missing"])
        manifest_path = root / LATEST
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        candidate_path = directory / "policy_ordinance_candidates.csv"
        validate_collection_evidence(root, manifest, candidate_csv=candidate_path)
        codes = _read_csv(directory / "admin_codes_202412.csv")
        waste = _read_csv(directory / "sigungu_2024_materials_verified.csv")
        # Logical roster hashes omit quantities and dates. Recheck explicit
        # temporal labels and identity consistency before admitting a linkage.
        _, expected = link_ordinance_geography(_read_csv(candidate_path), codes, waste)
        checks = {"candidate_sha256": _sha(candidate_path),
            "source_manifest_sha256": _sha(manifest_path),
            "codes_roster_sha256": canonical_roster_sha256(codes),
            "waste_roster_sha256": canonical_roster_sha256(waste),
            "crosswalk_sha256": _sha(directory / "policy_ordinance_geography_crosswalk.csv"),
            "article_evidence_sha256": _sha(directory / "policy_ordinance_article_evidence.csv")}
        if any(binding.get(field) != digest for field, digest in checks.items()):
            return dict(result, status="input_changed", reasons=["ordinance_source_or_linkage_input_changed"])
        crosswalk = _read_csv(directory / "policy_ordinance_geography_crosswalk.csv")
        articles = _read_csv(directory / "policy_ordinance_article_evidence.csv")
        expected.update(_review_counts(crosswalk, articles))
        expected["ordinance_detail_json_count"] = manifest.get("detail_count", 0)
        if (any(summary.get(field) != expected[field] for field in COUNT_FIELDS.values())
                or summary.get("law_api_status") != manifest.get("status", "unknown")):
            return dict(result, status="evidence_invalid", reasons=["ordinance_summary_counts_inconsistent"])
        return dict(result, verified=True, status="source_and_geography_bound")
    except (ValueError, TypeError, KeyError, AttributeError, OSError) as error:
        reason = str(error) if isinstance(error, ValueError) and str(error).startswith("LAW_COLLECTION_") else "ordinance_evidence_missing_or_invalid"
        return dict(result, status="evidence_invalid", reasons=[reason])


def current_ordinance_fields(root=ROOT, cached_summary=None):
    assessment = assess_ordinance_linkage(root)
    summary = assessment["summary"]
    cached = cached_summary if isinstance(cached_summary, dict) else {}
    fields = {"law_linkage_verified": assessment["verified"],
        "law_linkage_status": assessment["status"], "law_linkage_reasons": assessment["reasons"],
        "law_temporal_scope": TEMPORAL_SCOPE,
        "law_api_status": summary.get("law_api_status", "not_collected") if assessment["verified"] else assessment["status"]}
    for target, source in COUNT_FIELDS.items():
        historical = cached.get("cached_" + target, cached.get(target, summary.get(source, 0)))
        try:
            historical_count = max(0, int(historical))
        except (ValueError, TypeError, OverflowError):
            historical_count = 0
        fields["cached_" + target] = historical_count
        fields[target] = int(summary.get(source, 0)) if assessment["verified"] else 0
    return fields
