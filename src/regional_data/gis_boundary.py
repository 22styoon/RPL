"""Assess dated boundary polygons against the source-bound 2024 waste roster."""

import csv
import hashlib
import json
import math
import re
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd

from src.model import ROOT
from .audit_evidence import MONTHLY_FILE, WASTE_FILE, assess_boundary_audit
from .geocodes import ALIASES


DEFAULT_MANIFEST = Path("data/raw/regional_2024/gis_boundary/source_manifest.json")
SGIS_PROVINCES = dict(zip(
    ("11", "21", "22", "23", "24", "25", "26", "29", "31", "32", "33", "34", "35", "36", "37", "38", "39"),
    ("서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"),
    strict=True,
))
OVERLAP_TOLERANCE_M2 = 1.0


def _file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_file(directory, value):
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError("gis_input_path_invalid")
    path = (directory / value).resolve()
    if not path.is_relative_to(directory):
        raise ValueError("gis_input_path_invalid")
    return path


def _date(value):
    value = str(value).strip()
    if re.fullmatch(r"[0-9]{8}", value):
        value = f"{value[:4]}-{value[4:6]}-{value[6:]}"
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError("gis_reference_date_invalid") from None


def _source_manifest(path):
    manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(manifest, dict):
        raise ValueError("gis_source_manifest_invalid")
    url = manifest.get("source_url")
    parsed = urlsplit(url if isinstance(url, str) else "")
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        raise ValueError("gis_source_url_invalid")
    reference_date = _date(manifest.get("reference_date"))
    if reference_date.year != 2024:
        raise ValueError("gis_reference_year_mismatch")
    directory = path.parent
    boundary = _source_file(directory, manifest.get("boundary_file"))
    crosswalk = _source_file(directory, manifest.get("crosswalk_file"))
    if boundary.suffix.lower() == ".shp":
        companions = [boundary.with_suffix(ext) for ext in (".shx", ".dbf", ".prj")]
        cpg = boundary.with_suffix(".cpg")
        if cpg.exists():
            companions.append(cpg)
    elif boundary.suffix.lower() == ".geojson":
        companions = []
    else:
        raise ValueError("gis_boundary_format_unsupported")

    hashes = manifest.get("sha256")
    if not isinstance(hashes, dict):
        raise ValueError("gis_source_hashes_missing")
    files = {}
    for file in [boundary, crosswalk, *companions]:
        relative = file.relative_to(directory).as_posix()
        if not file.resolve().is_relative_to(directory):
            raise ValueError("gis_input_path_invalid")
        expected = hashes.get(relative)
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError(f"gis_source_hash_missing:{relative}")
        actual = _file_sha256(file)
        if expected != actual:
            raise ValueError(f"gis_source_hash_mismatch:{relative}")
        files[relative] = actual
    return manifest, reference_date, boundary, crosswalk, files


def _crosswalk(path):
    result = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or not {"gis_code", "mois_code"}.issubset(reader.fieldnames):
            raise ValueError("gis_crosswalk_columns_missing")
        for row in reader:
            gis_code = (row["gis_code"] or "").strip()
            mois_code = (row["mois_code"] or "").strip()
            if not re.fullmatch(r"[0-9]{2,10}", gis_code) or not re.fullmatch(r"[0-9]{10}", mois_code):
                raise ValueError("gis_crosswalk_code_invalid")
            if gis_code in result or mois_code in result.values():
                raise ValueError("gis_crosswalk_duplicate_identity")
            result[gis_code] = mois_code
    return result


def _shapefile_features(boundary, encoding, *, include_geometry):
    import shapefile

    with shapefile.Reader(str(boundary), encoding=encoding) as reader:
        if include_geometry:
            for record in reader.iterShapeRecords():
                yield record.__geo_interface__
        else:
            for record in reader.iterRecords():
                yield {"type": "Feature", "properties": record.as_dict()}


def _features(boundary, manifest, crs_type, *, include_geometry=True):
    if boundary.suffix.lower() == ".geojson":
        data = json.loads(boundary.read_text(encoding="utf-8-sig"))
        if (not isinstance(data, dict) or data.get("type") != "FeatureCollection"
                or "crs" in data or not isinstance(data.get("features"), list)):
            raise ValueError("gis_geojson_must_be_rfc7946_feature_collection")
        source_crs = crs_type.from_epsg(4326)
        features = data["features"]
    else:
        source_crs = crs_type.from_wkt(boundary.with_suffix(".prj").read_text(encoding="utf-8-sig"))
        cpg = boundary.with_suffix(".cpg")
        encoding = manifest.get("encoding") or (cpg.read_text(encoding="utf-8-sig").strip() if cpg.exists() else "cp949")
        if encoding == "65001":
            encoding = "utf-8"
        features = _shapefile_features(boundary, encoding, include_geometry=include_geometry)
    return source_crs, features


def _roster(root, reference_date):
    dtype = {"sigungu_code": str}
    waste = pd.read_csv(root / WASTE_FILE, dtype=dtype, keep_default_na=False)
    monthly = pd.read_csv(root / MONTHLY_FILE, dtype=str, keep_default_na=False)
    month = monthly.loc[monthly.reference_month.eq(reference_date.strftime("%Y%m"))]
    identities = ("sido_name", "sigungu_name")
    admin = month.set_index("sigungu_code")[list(identities)].to_dict("index")
    target_codes = set(waste.sigungu_code)
    children = defaultdict(set)
    for code in set(admin) - target_codes:
        parent = code[:4] + "000000"
        child = admin[code]
        if (parent not in target_codes or child["sido_name"] != admin[parent]["sido_name"]
                or not child["sigungu_name"].startswith(admin[parent]["sigungu_name"] + " ")
                or not child["sigungu_name"].endswith("구")):
            raise ValueError(f"gis_mois_hierarchy_unresolved:{code}")
        children[parent].add(code)
    return admin, target_codes, children


def _name(value):
    return " ".join(unicodedata.normalize("NFKC", str(value)).split())


def _identity_matches(gis_code, mois_code, label, namespace, admin, *, full_name=False):
    province = admin["sido_name"]
    county = admin["sigungu_name"]
    if namespace == "sgis":
        if (not re.fullmatch(r"[0-9]{5}", gis_code) and gis_code != "29") or SGIS_PROVINCES.get(gis_code[:2]) != province:
            return False
    elif gis_code not in {mois_code, mois_code[:5]}:
        return False
    names = {county}
    if not full_name:
        names.add(county.split(" ")[-1])
    if mois_code == "3611000000":
        names.add("세종특별자치시")
    prefixes = {province, *(alias for alias, name in ALIASES.items() if name == province)}
    names |= {f"{prefix} {name}" for prefix in prefixes for name in names}
    # The source may concatenate the complete city and district names.
    return _name(label).replace(" ", "") in {name.replace(" ", "") for name in names}


def _feature_properties(feature):
    if (not isinstance(feature, dict) or feature.get("type") != "Feature"
            or not isinstance(feature.get("properties"), dict)):
        raise ValueError("gis_feature_invalid")
    return feature["properties"]


def _statistical_unit_groups(source_codes, target_codes, children):
    result = {}
    for code in sorted(target_codes):
        wards = children[code] & source_codes
        if code in source_codes and not wards:
            result[code] = (code,)
        elif code not in source_codes and wards and wards == children[code]:
            result[code] = tuple(sorted(wards))
        else:
            raise ValueError(f"gis_statistical_unit_coverage_unresolved:{code}")
    return result


def _loaded_snapshot(root, manifest_path):
    from pyproj import CRS, Transformer
    from shapely import STRtree
    from shapely.geometry import shape
    from shapely.ops import transform, unary_union

    manifest, reference_date, boundary, crosswalk, files = _source_manifest(manifest_path)
    namespace = manifest.get("code_namespace", "sgis")
    if namespace not in {"sgis", "mois"}:
        raise ValueError("gis_code_namespace_unsupported")
    code_field, name_field, date_field = (manifest.get(key, default) for key, default in
        (("code_field", "ADM_CD"), ("name_field", "ADM_NM"), ("date_field", "BASE_DATE")))
    if not all(isinstance(field, str) and field.strip() for field in (code_field, name_field, date_field)):
        raise ValueError("gis_feature_fields_invalid")
    admin, target_codes, children = _roster(root, reference_date)
    mapping = _crosswalk(crosswalk)
    source_crs, features = _features(boundary, manifest, CRS)
    area_crs = CRS.from_epsg(5179)
    to_projected = (None if source_crs.equals(area_crs, ignore_axis_order=True)
                    else Transformer.from_crs(source_crs, area_crs, always_xy=True).transform)
    to_lonlat = Transformer.from_crs(source_crs, 4326, always_xy=True)
    polygons = {}
    for feature in features:
        properties = _feature_properties(feature)
        gis_code = str(properties.get(code_field, "")).strip()
        mois_code = mapping.get(gis_code)
        if mois_code not in admin or not _identity_matches(gis_code, mois_code, properties.get(name_field), namespace, admin[mois_code]):
            raise ValueError(f"gis_identity_unresolved:{gis_code}")
        if mois_code in polygons:
            raise ValueError(f"gis_boundary_duplicate_unit:{mois_code}")
        if _date(properties.get(date_field)) != reference_date:
            raise ValueError(f"gis_feature_date_mismatch:{gis_code}")
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict) or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            raise ValueError(f"gis_polygon_required:{gis_code}")
        polygon = shape(geometry)
        if polygon.is_empty or not polygon.is_valid or not all(map(math.isfinite, polygon.bounds)):
            raise ValueError(f"gis_polygon_invalid:{gis_code}")
        west, south, east, north = to_lonlat.transform_bounds(*polygon.bounds)
        if not (120 <= west < east <= 135 and 30 <= south < north <= 43):
            raise ValueError(f"gis_polygon_outside_korea_or_crs_invalid:{gis_code}")
        projected = polygon if to_projected is None else transform(to_projected, polygon)
        if ((to_projected is not None and not projected.is_valid)
                or not math.isfinite(projected.area) or projected.area <= 0):
            raise ValueError(f"gis_projected_polygon_invalid:{gis_code}")
        polygons[mois_code] = projected
    if set(mapping.values()) != set(polygons):
        raise ValueError("gis_crosswalk_has_unrepresented_units")

    statistical_polygons = {}
    dissolved_units = 0
    for code, source_codes in _statistical_unit_groups(polygons.keys(), target_codes, children).items():
        if source_codes == (code,):
            statistical_polygons[code] = polygons[code]
            continue
        wards = [polygons[ward] for ward in source_codes]
        geometry = unary_union(wards)
        if not geometry.is_valid or geometry.is_empty or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            raise ValueError(f"gis_dissolved_polygon_invalid:{code}")
        if sum(ward.area for ward in wards) - geometry.area > OVERLAP_TOLERANCE_M2:
            raise ValueError(f"gis_general_district_overlap:{code}")
        statistical_polygons[code] = geometry
        dissolved_units += 1

    codes = list(statistical_polygons)
    geometries = list(statistical_polygons.values())
    index = STRtree(geometries)
    for i, geometry in enumerate(geometries):
        for j in index.query(geometry, predicate="intersects"):
            if j > i and geometry.intersection(geometries[j]).area > OVERLAP_TOLERANCE_M2:
                raise ValueError(f"gis_statistical_unit_overlap:{codes[i]},{codes[j]}")

    summary = {"reference_date": reference_date.isoformat(), "source_url": manifest["source_url"],
               "code_namespace": namespace, "source_crs": source_crs.to_string(), "area_crs": "EPSG:5179",
               "statistical_unit_count": len(statistical_polygons), "source_feature_count": len(polygons),
               "dissolved_city_count": dissolved_units, "overlap_tolerance_m2": OVERLAP_TOLERANCE_M2,
               "source_sha256": files, "manifest_sha256": _file_sha256(manifest_path),
               "scope": "dated_statistical_unit_polygon_integrity_and_coverage"}
    return summary, statistical_polygons


def propose_gis_crosswalk(root, boundary, *, code_namespace="sgis", code_field="ADM_CD",
                          name_field="ADM_NM", date_field="BASE_DATE", encoding=None):
    """Propose explicit crosswalk rows for review from unique full identities."""
    from pyproj import CRS

    if code_namespace not in {"sgis", "mois"}:
        raise ValueError("gis_code_namespace_unsupported")
    root = Path(root).resolve()
    code_audit = assess_boundary_audit(root)
    if not code_audit["verified"]:
        raise ValueError("gis_current_mois_audit_unverified")
    boundary = (root / boundary).resolve()
    if boundary.suffix.lower() not in {".shp", ".geojson"}:
        raise ValueError("gis_boundary_format_unsupported")
    _, features = _features(boundary, {"encoding": encoding}, CRS, include_geometry=False)
    feature_rows = [_feature_properties(feature) for feature in features]
    dates = {_date(row.get(date_field)) for row in feature_rows}
    if len(dates) != 1 or next(iter(dates)).year != 2024:
        raise ValueError("gis_proposal_requires_one_2024_reference_date")
    reference_date = dates.pop()
    admin, targets, children = _roster(root, reference_date)
    rows = []
    unresolved = []
    used_mois = set()
    used_gis = set()
    for properties in feature_rows:
        gis_code = str(properties.get(code_field) or "").strip()
        name = _name(properties.get(name_field) or "")
        if not gis_code or not name:
            raise ValueError("gis_proposal_identity_blank")
        matches = [code for code, region in admin.items()
                   if _identity_matches(gis_code, code, name, code_namespace, region, full_name=True)]
        if len(matches) != 1 or matches[0] in used_mois or gis_code in used_gis:
            unresolved.append(gis_code)
            continue
        mois_code = matches[0]
        used_gis.add(gis_code)
        used_mois.add(mois_code)
        rows.append({"gis_code": gis_code, "mois_code": mois_code, "gis_name": name,
                     **admin[mois_code], "reference_date": reference_date.isoformat()})
    if unresolved:
        raise ValueError("gis_proposal_unresolved_codes:" + ",".join(sorted(set(unresolved))[:15]))
    _statistical_unit_groups(used_mois, targets, children)
    return sorted(rows, key=lambda row: row["gis_code"])


def assess_gis_boundary(root=ROOT, *, manifest_path=None, compare_manifest_path=None):
    """Verify one snapshot, optionally comparing two dates of the same series."""
    root = Path(root).resolve()
    path = (root / (manifest_path or DEFAULT_MANIFEST)).resolve()
    pending = {"status": "source_pending", "verified": False, "geometry_assessed": False,
               "reasons": [], "summary": {}, "comparison": None}
    if not path.is_file():
        return dict(pending, reasons=["gis_source_manifest_missing"])
    code_audit = assess_boundary_audit(root)
    if not code_audit["verified"]:
        return dict(pending, status="geographic_inputs_pending", reasons=code_audit["reasons"])

    def assess(path):
        try:
            summary, polygons = _loaded_snapshot(root, path)
        except ImportError:
            return dict(pending, status="dependencies_pending", reasons=["gis_dependencies_unavailable"]), {}
        except FileNotFoundError:
            return dict(pending, reasons=["gis_source_file_missing"]), {}
        except (LookupError, OSError, TypeError, ValueError) as exc:
            reason = str(exc) if isinstance(exc, ValueError) and re.fullmatch(r"gis_[^\r\n]{1,180}", str(exc)) else "gis_source_or_geometry_unreadable"
            return dict(pending, status="review_required", reasons=[reason]), {}
        except Exception as exc:
            if type(exc).__module__.split(".", 1)[0] not in {"pyproj", "shapely", "shapefile"}:
                raise
            return dict(pending, status="review_required", reasons=["gis_source_or_geometry_unreadable"]), {}
        summary["waste_roster_sha256"] = code_audit["waste_roster_sha256"]
        summary["monthly_roster_sha256"] = code_audit["monthly_roster_sha256"]
        return dict(pending, status="snapshot_verified", verified=True, geometry_assessed=True, summary=summary), polygons

    result, polygons = assess(path)
    if not result["verified"] or compare_manifest_path is None:
        return result
    second, other_polygons = assess((root / compare_manifest_path).resolve())
    first_summary, second_summary = result["summary"], second["summary"]
    if not second["verified"]:
        result["comparison"] = {"status": second["status"], "verified": False, "reasons": second["reasons"]}
    elif (first_summary["reference_date"] == second_summary["reference_date"]
          or any(first_summary[field] != second_summary[field] for field in ("source_url", "code_namespace", "source_crs"))):
        result["comparison"] = {"status": "review_required", "verified": False, "reasons": ["gis_comparison_series_or_date_mismatch"]}
    else:
        changed = [code for code, polygon in polygons.items() if not polygon.equals(other_polygons[code])]
        result["comparison"] = {"status": "compared", "verified": True,
                                "reference_dates": sorted([first_summary["reference_date"], second_summary["reference_date"]]),
                                "changed_statistical_unit_codes": changed, "changed_statistical_unit_count": len(changed),
                                "other_manifest_sha256": second_summary["manifest_sha256"]}
    return result
