"""Public-only adapters for documented PPS contract list/history operations.

Amounts remain contract amounts. Long-term total amounts and current amounts
have different meanings and are never added across amendment/history records.
Official schema and guide: data.go.kr/data/15129427/openapi.do.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import hashlib
import json
import re

from .facilities import (
    PublicDataSchemaError, _date, _mapping, _metadata, _number, _text, _values,
)

SOURCE_ID = "15129427"
SOURCE_URL = "https://www.data.go.kr/data/15129427/openapi.do"
GUIDE_URL = (
    "https://www.data.go.kr/cmm/cmm/fileDownload.do?"
    "atchFileId=FILE_000000007761074&fileDetailSn=1"
)

_BASE_OPERATIONS = {
    "getCntrctInfoListServc": "service",
    "getCntrctInfoListCnstwk": "construction",
    "getCntrctInfoListThng": "goods",
    "getCntrctInfoListFrgcpt": "foreign",
}
_COMMON_FIELDS = {
    "unified_contract_id": "untyCntrctNo",
    "contract_id": "dcsnCntrctNo",
    "contract_reference_id": "cntrctRefNo",
    "registered_at": "rgstDt",
    "changed_at": "chgDt",
}
_CURRENT_FIELDS = {
    "business_category": "bsnsDivNm",
    "long_term_category": "lngtrmCtnuDivNm",
    "contract_agency_code": "cntrctInsttCd",
    "contract_agency_name": "cntrctInsttNm",
    "contract_date": "cntrctCnclsDate",
    "contract_period": "cntrctPrd",
    "total_contract_amount": "totCntrctAmt",
    "current_contract_amount": "thtmCntrctAmt",
}
_ALL_CANONICAL_FIELDS = set(_COMMON_FIELDS) | set(_CURRENT_FIELDS) | {
    "title", "start_date", "current_completion_date", "total_completion_date",
    "deleted_at", "deletion_category", "change_order",
}
_STRING_FIELDS = {
    "unified_contract_id", "contract_id", "contract_reference_id", "title",
    "business_category", "long_term_category", "contract_agency_code",
    "contract_agency_name", "contract_period", "deletion_category", "change_order",
}
_DATE_FIELDS = {
    "contract_date", "start_date", "current_completion_date", "total_completion_date",
}
_TIMESTAMP_FIELDS = {"registered_at", "changed_at", "deleted_at"}
_AMOUNT_FIELDS = {"total_contract_amount", "current_contract_amount"}
_METADATA_FIELDS = {
    "source_id", "source_url", "retrieved_at", "reference_period",
    "requested_reference_period", "reference_period_verified", "region",
    "data_kind", "field_mapping_source",
}
_OUTPUT_FIELDS = _ALL_CANONICAL_FIELDS | _METADATA_FIELDS | {
    "business_type", "operation", "record_status", "title_category",
    "needs_manual_review", "cost_interpretation", "amount_aggregation",
    "change_order_status", "contract_year",
}
# These attributes distinguish substantive versions, unlike retrieval metadata.
_CONTENT_FIELDS = _ALL_CANONICAL_FIELDS | {
    "business_type", "contract_year",
}


def _operation(context: dict) -> tuple[str, str, str]:
    operation = _text(context.get("operation"), "operation")
    for base, business_type in _BASE_OPERATIONS.items():
        if operation == base:
            return operation, business_type, "current"
        if operation == base + "ChgHstry":
            return operation, business_type, "change"
        if operation == base + "DltHstry":
            return operation, business_type, "deleted"
    raise PublicDataSchemaError("An exact supported PPS list/history operation is required.")


def classify_contract_title(title: str | None) -> tuple[str, bool]:
    """Return a conservative title category and a manual-scope-review flag.

    This classifies text only; it never validates an actual cost or unit price.
    Mixed scopes and professional/unspecified services require manual review.
    """
    text = _text(title, "title")
    if not text:
        return "unclassified", True
    compact = re.sub(r"\s+", "", text)
    if not re.search(r"폐기물|재활용|자원회수|선별장|선별시설|소각|매립", compact):
        return "unclassified", True
    if re.search(r"기본계획|실시설계|설계용역|감리|타당성|연구용역", compact):
        return "professional_service", True
    categories = set()
    if re.search(r"공사|신설|증설|건립|건설|현대화|시설조성", compact):
        categories.add("facility_construction")
    if (
        re.search(r"선별기|파쇄기|압축기|컨베이어|설비|장비|기계", compact)
        and re.search(r"구매|구입|제작|납품|교체|설치", compact)
    ):
        categories.add("equipment_purchase")
    if re.search(r"운영|유지관리|유지보수|정비|보수용역", compact):
        categories.add("operation_maintenance")
    if re.search(r"수집|운반|수거", compact):
        categories.add("waste_collection_transport")
    if re.search(r"처리용역|위탁처리|처리대행|선별용역", compact):
        categories.add("waste_treatment_service")
    if len(categories) > 1:
        return "mixed_scope", True
    if not categories:
        return "unclassified", True
    return categories.pop(), False


def normalize_contracts(items: list[dict], context: dict) -> list[dict]:
    """Normalize current/change/deletion rows using exact operation schemas.

    Nested dminsttList/corpList strings contain contacts and are discarded.
    Contract number suffixes are preserved verbatim; no amendment number is
    guessed from the many historical identifier formats.
    """
    if not isinstance(items, list):
        raise PublicDataSchemaError("Contract items must be a list.")
    metadata = _metadata(context, SOURCE_ID, SOURCE_URL, registry=True)
    operation, business_type, status = _operation(context)
    defaults = dict(_COMMON_FIELDS)
    if status == "deleted":
        defaults.update({"deleted_at": "dltDt", "deletion_category": "chgDivNm"})
    else:
        defaults.update(_CURRENT_FIELDS)
        defaults["title"] = "cnstwkNm" if business_type == "construction" else "cntrctNm"
        if business_type == "service":
            defaults.update({
                "start_date": "wbgnDate",
                "current_completion_date": "thtmScmpltDate",
                "total_completion_date": "ttalScmpltDate",
            })
        elif business_type == "construction":
            defaults.update({
                "start_date": "cbgnDate",
                "current_completion_date": "thtmCcmpltDate",
                "total_completion_date": "ttalCcmpltDate",
            })
    mapping = _mapping(context, defaults, _ALL_CANONICAL_FIELDS - set(defaults))
    required = {"unified_contract_id"} if status == "deleted" else {"unified_contract_id", "title"}
    rows = []
    for item in items:
        values = _values(item, mapping, required)
        for canonical in context.get("field_mapping", {}):
            if mapping[canonical] not in item:
                raise PublicDataSchemaError(f"Explicitly mapped field is absent: {canonical}.")
        row = {name: _text(values.get(name), name) for name in _STRING_FIELDS}
        row.update({name: _date(values.get(name), name) for name in _DATE_FIELDS})
        row.update({
            name: _date(values.get(name), name, timestamp=True)
            for name in _TIMESTAMP_FIELDS
        })
        row.update({name: _number(values.get(name), name) for name in _AMOUNT_FIELDS})
        category, review = classify_contract_title(row["title"])
        row.update(metadata)
        row.update({
            "business_type": business_type,
            "operation": operation,
            "record_status": status,
            "contract_year": int(row["contract_date"][:4]) if row["contract_date"] else None,
            "title_category": category,
            "needs_manual_review": review,
            "cost_interpretation": "public_contract_amount_not_actual_cost",
            "amount_aggregation": "not_summed",
            "change_order_status": (
                "explicit_verified_mapping" if row["change_order"] is not None
                else "not_a_separate_documented_field"
            ),
        })
        rows.append(row)
    return rows


def contract_key(row: dict) -> tuple[str, str]:
    """Use the documented unified identifier, never a title/amount heuristic."""
    if not isinstance(row, dict):
        raise PublicDataSchemaError("A normalized contract row must be a dictionary.")
    identifier = _text(row.get("unified_contract_id"), "unified_contract_id")
    if not identifier:
        raise PublicDataSchemaError("A unified contract identifier is required for merging.")
    source = _text(row.get("source_id", SOURCE_ID), "source_id")
    if not source:
        raise PublicDataSchemaError("A contract source identifier is required for merging.")
    return source, identifier


def _fingerprint(row: dict) -> str:
    payload = {key: row.get(key) for key in sorted(_CONTENT_FIELDS)}
    payload["is_deleted"] = row.get("record_status") == "deleted"
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    ).hexdigest()


def _version_identity(row: dict) -> tuple:
    return tuple(row.get(key) for key in (
        "contract_id", "contract_reference_id", "change_order",
        "changed_at", "registered_at", "deleted_at",
    )) + (row.get("record_status") == "deleted",)


def _version_time(row: dict) -> str | None:
    # These timestamps describe source records; retrieval time is never a
    # substitute for a documented amendment/registration/deletion chronology.
    return row.get("deleted_at") or row.get("changed_at") or row.get("registered_at")


def merge_contract_versions(rows: list[dict]) -> list[dict]:
    """Deduplicate observations and preserve every distinct public version.

    A representative uses the latest documented source timestamp. Conflicting
    versions, unknown ordering, or deletion leave representative amounts None.
    Every original amount remains visible in version_history and is not summed.
    """
    if not isinstance(rows, list):
        raise PublicDataSchemaError("Contract versions must be a list.")
    groups = defaultdict(list)
    for row in rows:
        key = contract_key(row)
        # Output allowlisting prevents an accidental raw row from retaining
        # supplier/contact payloads even when passed directly to this function.
        snapshot = {field: deepcopy(row.get(field)) for field in sorted(_OUTPUT_FIELDS)}
        snapshot["source_id"], snapshot["unified_contract_id"] = key
        groups[key].append(snapshot)
    merged = []
    for key in sorted(groups):
        observations = groups[key]
        distinct = {}
        identities = defaultdict(set)
        for row in observations:
            fingerprint = _fingerprint(row)
            identities[_version_identity(row)].add(fingerprint)
            if fingerprint not in distinct:
                distinct[fingerprint] = deepcopy(row)
                distinct[fingerprint]["version_fingerprint"] = fingerprint
                distinct[fingerprint]["duplicate_count"] = 0
                distinct[fingerprint]["observed_operations"] = []
                distinct[fingerprint]["observed_retrieval_times"] = []
            version = distinct[fingerprint]
            version["duplicate_count"] += 1
            for field, target in (
                ("operation", "observed_operations"),
                ("retrieved_at", "observed_retrieval_times"),
            ):
                value = row.get(field)
                if value is not None and value not in version[target]:
                    version[target].append(value)
        history = sorted(
            distinct.values(),
            key=lambda row: (
                _version_time(row) or "", row.get("contract_id") or "",
                row["version_fingerprint"],
            ),
        )
        for version in history:
            version["observed_operations"].sort()
            version["observed_retrieval_times"].sort()
        reasons = []
        if any(len(fingerprints) > 1 for fingerprints in identities.values()):
            reasons.append("same_version_has_conflicting_public_fields")
        if len(history) > 1 and any(_version_time(row) is None for row in history):
            reasons.append("version_order_unverified")
        latest_time = max((_version_time(row) or "" for row in history), default="")
        candidates = [row for row in history if (_version_time(row) or "") == latest_time]
        if len(candidates) > 1:
            reasons.append("latest_version_is_ambiguous")
        if len({row.get("business_type") for row in history}) > 1:
            reasons.append("business_type_conflict")
        representative = {
            field: deepcopy(candidates[-1].get(field)) for field in sorted(_OUTPUT_FIELDS)
        }
        deleted = representative.get("record_status") == "deleted"
        # Historical versions may have ordinary changes in amount. Their
        # presence alone is not an arithmetic conflict or a reason to add them.
        if reasons or deleted:
            representative["total_contract_amount"] = None
            representative["current_contract_amount"] = None
            representative["needs_manual_review"] = True
        representative.update({
            "contract_key": list(key),
            "version_history": history,
            "version_count": len(history),
            "observation_count": len(observations),
            "has_conflict": bool(reasons),
            "conflict_reasons": reasons,
            "amount_aggregation": "not_summed",
            "amount_scope": "latest_observed_version_not_lifetime_sum",
            "is_deleted": deleted,
        })
        merged.append(representative)
    return merged

