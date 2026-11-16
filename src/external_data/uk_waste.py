"""영국 2024 WDI 반입 XLSB. 공개 허가번호별 반입량만 집계한다."""
from collections import defaultdict
from io import BytesIO
import json,math
from pathlib import Path
from urllib.parse import urlencode
from zipfile import ZipFile
from pyxlsb import open_workbook
from .common import ExternalDataError,fetch,metadata,save_records
PAGE="https://www.data.gov.uk/dataset/81f9d676-e77c-4d68-ab0c-b67e0b0b353e/2024-waste-data-interrogator"
DOWNLOAD="https://environment.data.gov.uk/api/file/download?"+urlencode({"fileDataSetId":"05820d7e-5269-4dc0-b1d4-79094cf7f19a","fileName":"2024 Waste Data Interrogator - Wastes Received (Excel) - Version 2.zip"})
LICENSE="Environment Agency Conditional Licence; internal/personal research; one-year and redistribution conditions apply"

def normalize_rows(headers,rows,meta):
    required={"Permit","Facility RPA","Facility Type","Tonnes Received"}
    if not required<=set(headers):
        raise ExternalDataError("확인한 WDI 반입 열이 없습니다.")
    positions={name:headers.index(name) for name in required}
    groups={}
    for values in rows:
        if not values or all(value is None for value in values):
            continue
        get=lambda name:values[positions[name]] if positions[name]<len(values) else None
        permit,tonnes=get("Permit"),get("Tonnes Received")
        if tonnes is None or isinstance(tonnes,bool) or not isinstance(tonnes,(int,float)) or not math.isfinite(tonnes):
            raise ExternalDataError("WDI 반입량이 결측이거나 비유한 수치입니다.")
        if isinstance(permit,float) and permit.is_integer():
            permit=str(int(permit))
        elif permit is not None:
            permit=str(permit).strip()
        # Unknown/confidential IDs cannot be treated as separate facilities.
        key=permit or None
        if key not in groups:
            groups[key]=dict(received_t=0.0,source_rows=0,regions=set(),types=set(),negative_adjustment_rows=0)
        group=groups[key]
        group["received_t"]+=tonnes
        group["source_rows"]+=1
        group["negative_adjustment_rows"]+=tonnes<0
        group["regions"].add(str(get("Facility RPA") or "미기재"))
        group["types"].add(str(get("Facility Type") or "미기재"))
    result=[]
    for permit,group in groups.items():
        if group["received_t"]<0:
            raise ExternalDataError("허가번호 합산 반입량이 음수입니다.")
        result.append(metadata(meta,country="GB-ENG",geography="England permitted waste facilities",year=2024,
            waste_scope="all wastes reported by permitted sites; includes transfer and hazardous waste",material="혼합 전체",
            process_stage="facility receipts",numerator_definition="reported receipts",
            denominator_definition="permit-year",site_key=permit,received_t=group["received_t"],
            value=group["received_t"],metric="received",unit="t/year",
            source_rows=group["source_rows"],region="; ".join(sorted(group["regions"])),
            facility_type="; ".join(sorted(group["types"])),negative_adjustment_rows=group["negative_adjustment_rows"],
            source_locator="2024 Waste Received XLSB; Permit grouped, Tonnes Received sum",
            comparability_flag="not_harmonized",uncertainty="inter-facility transfers; confidential site identities may be withheld"))
    return result

def normalize_zip(raw,meta):
    with ZipFile(BytesIO(raw)) as archive:
        members=[info for info in archive.infolist() if info.filename.endswith(".xlsb")]
        if len(members)!=1 or members[0].file_size>300_000_000:
            raise ExternalDataError("확인한 크기의 XLSB 한 개만 허용합니다.")
        with open_workbook(BytesIO(archive.read(members[0]))) as workbook:
            if "2024 Waste Received" not in workbook.sheets:
                raise ExternalDataError("확인한 반입 시트가 없습니다.")
            with workbook.get_sheet("2024 Waste Received") as sheet:
                rows=sheet.rows()
                headers=[cell.v for cell in next(rows)]
                return normalize_rows(headers,([cell.v for cell in row] for row in rows),meta)

def collect(*,root,year=2024,reuse_raw=False):
    if year!=2024:
        raise ExternalDataError("확인한 WDI 2024 Version 2만 지원합니다.")
    saved=list((Path(root)/"data/raw/international/uk_waste").glob("*/wastes_received_2024_v2.zip"))
    if reuse_raw and saved:
        path=saved[-1];raw=path.read_bytes()
        meta=json.loads((path.parent/"manifest.json").read_text(encoding="utf-8"))
        import hashlib
        if hashlib.sha256(raw).hexdigest()!=meta["sha256"]:
            raise ExternalDataError("보존 원자료 해시가 맞지 않습니다.")
    else:
        raw,meta=fetch("uk_waste",DOWNLOAD,"wastes_received_2024_v2.zip",root=root,
            license=LICENSE,redistribution="restricted_do_not_publish_raw")
    return save_records(normalize_zip(raw,meta),meta,root=root)
