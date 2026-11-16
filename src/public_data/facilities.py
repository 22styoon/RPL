"""Normalize the documented KECO registry without inventing facility attributes.

The official 15172490 getList item schema contains business identifiers and
administrative areas, not a separate facility name, street address, capacity, or
reference year. Unknown response fields are never copied into normalized rows.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SOURCE_ID = "15172490"
SOURCE_URL = "https://www.data.go.kr/data/15172490/openapi.do"

# Confirmed in the official portal's embedded Swagger getList_response schema.
FACILITY_FIELDS = {
    "business_id": "bzentyId",
    "business_name": "bzentyNm",
    "facility_type_code": "fcltTypeCd",
    "facility_type_name": "fcltTypeNm",
    "facility_category_code": "fcltSeCd",
    "facility_category_name": "fcltSeNm",
    "province_code": "lctnCtpyCd",
    "province_name": "lctnCtpyNm",
    "district_code": "lctnSggCd",
    "district_name": "lctnSggNm",
}
FACILITY_EXTENSION_FIELDS = {
    "facility_id", "facility_name", "address", "facility_capacity",
    "facility_capacity_unit", "registration_date",
}


class PublicDataSchemaError(ValueError):
    """A response or explicit field mapping cannot be normalized safely."""


def _text(value: Any, field: str) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise PublicDataSchemaError(f"Expected a scalar public field: {field}.")
    result = str(value).strip()
    return result or None


def _number(value: Any, field: str) -> int | float | None:
    text = _text(value, field)
    if text is None:
        return None
    if not re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", text):
        raise PublicDataSchemaError(f"Invalid non-negative numeric field: {field}.")
    try:
        number = Decimal(text.replace(",", ""))
    except InvalidOperation:
        raise PublicDataSchemaError(f"Invalid numeric field: {field}.") from None
    if not number.is_finite():
        raise PublicDataSchemaError(f"Invalid numeric field: {field}.")
    return int(number) if number == number.to_integral_value() else float(number)


def _date(value: Any, field: str, *, timestamp: bool = False) -> str | None:
    text = _text(value, field)
    if text is None:
        return None
    patterns = (
        "%Y-%m-%d %H:%M:%S", "%Y%m%d%H%M%S", "%Y%m%d%H%M",
        "%Y-%m-%d", "%Y%m%d",
    )
    parsed = None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for pattern in patterns:
            try:
                parsed = datetime.strptime(text, pattern)
                break
            except ValueError:
                continue
    if parsed is None:
        raise PublicDataSchemaError(f"Invalid calendar field: {field}.")
    return parsed.isoformat(timespec="seconds") if timestamp else parsed.date().isoformat()


def _public_url(value: Any, field: str) -> str | None:
    text = _text(value, field)
    if text is None:
        return None
    parts = urlsplit(text)
    if parts.scheme not in {"http", "https"} or not parts.netloc or parts.username or parts.password:
        raise PublicDataSchemaError(f"Expected a public HTTP source URL: {field}.")
    # Context must not reintroduce a query credential into persisted provenance.
    query = [
        (key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower().replace("_", "").replace("-", "") not in {
            "servicekey", "apikey", "key", "token", "authorization", "accesskey",
        }
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def _metadata(context: dict, source_id: str, source_url: str, *, registry: bool = False) -> dict:
    if not isinstance(context, dict):
        raise PublicDataSchemaError("Normalization context must be a dictionary.")
    kind = context.get("data_kind", "live")
    if kind not in {"live", "synthetic"}:
        raise PublicDataSchemaError("data_kind must be live or synthetic.")
    period = _text(context.get("reference_period"), "reference_period")
    verified = context.get("reference_period_verified") is True
    return {
        "source_id": _text(context.get("source_id", source_id), "source_id"),
        "source_url": _public_url(context.get("source_url", source_url), "source_url"),
        "retrieved_at": _text(context.get("retrieved_at"), "retrieved_at"),
        "reference_period": period if not registry or verified else None,
        "requested_reference_period": period,
        "reference_period_verified": verified,
        "region": _text(context.get("region"), "region"),
        "data_kind": kind,
        "field_mapping_source": _public_url(context.get("field_mapping_source"), "field_mapping_source"),
    }


def _mapping(context: dict, defaults: dict[str, str], extensions: set[str]) -> dict[str, str]:
    overrides = context.get("field_mapping", {})
    if not isinstance(overrides, dict):
        raise PublicDataSchemaError("field_mapping must map canonical names to exact response names.")
    allowed = set(defaults) | extensions
    result = dict(defaults)
    for canonical, source in overrides.items():
        if canonical not in allowed or not isinstance(source, str) or not source.strip():
            raise PublicDataSchemaError("Unsupported or ambiguous explicit field mapping.")
        if result.get(canonical) != source and not context.get("field_mapping_source"):
            raise PublicDataSchemaError("An explicit field mapping requires its verified source URL.")
        # Embedded contact/vendor-list fields must never enter normalized output.
        compact = source.lower().replace("_", "")
        if compact in {"corplist", "dminsttlist"} or re.search(
            r"tel|phone|fax|email|rrn|resident|담당자|연락처|주민|rprsntv|chrgprsn", compact
        ):
            raise PublicDataSchemaError("Personal/contact fields cannot be explicitly mapped.")
        result[canonical] = source
    return result


def _values(item: dict, mapping: dict[str, str], required: set[str]) -> dict:
    if not isinstance(item, dict):
        raise PublicDataSchemaError("Every response item must be a dictionary.")
    for canonical in sorted(required):
        source = mapping[canonical]
        if source not in item or _text(item[source], canonical) is None:
            raise PublicDataSchemaError(f"Required documented field is absent: {canonical}.")
    # A configured override must exist; silently accepting a typo loses provenance.
    return {canonical: item.get(source) for canonical, source in mapping.items()}


def normalize_facilities(items: list[dict], context: dict) -> list[dict]:
    """Return public registry rows; absent facility attributes remain None.

    Optional field_mapping overrides/extensions require field_mapping_source.
    These are explicit, reviewable mappings, never guessed aliases. A requested
    reference year is not an observed registry year unless separately verified.
    """
    if not isinstance(items, list):
        raise PublicDataSchemaError("Facility items must be a list.")
    metadata = _metadata(context, SOURCE_ID, SOURCE_URL, registry=True)
    mapping = _mapping(context, FACILITY_FIELDS, FACILITY_EXTENSION_FIELDS)
    rows = []
    for item in items:
        values = _values(item, mapping, {"business_id", "business_name"})
        for canonical in context.get("field_mapping", {}):
            if mapping[canonical] not in item:
                raise PublicDataSchemaError(f"Explicitly mapped field is absent: {canonical}.")
        row = {name: _text(values.get(name), name) for name in FACILITY_FIELDS}
        row.update({
            name: _text(values.get(name), name)
            for name in FACILITY_EXTENSION_FIELDS
            if name not in {"facility_capacity", "registration_date"}
        })
        row["facility_capacity"] = _number(values.get("facility_capacity"), "facility_capacity")
        row["registration_date"] = _date(values.get("registration_date"), "registration_date")
        if row["facility_capacity"] is None:
            row["facility_capacity_unit"] = None
        row.update(metadata)
        row.update({
            "evidence_kind": "current_registry_snapshot",
            "historical_performance_verified": False,
            "capacity_basis": "not_provided" if row["facility_capacity"] is None else "explicit_verified_mapping",
            "facility_name_status": "not_provided" if row["facility_name"] is None else "explicit_verified_mapping",
        })
        rows.append(row)
    return rows

