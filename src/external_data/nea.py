"""NEA가 연결한 공식 PDF 표를 파싱한다. '000 tonnes를 t로 변환."""
from io import BytesIO
import re
from pypdf import PdfReader
from .common import ExternalDataError,fetch,metadata,save_records
PAGE="https://www.nea.gov.sg/our-services/waste-management/waste-statistics-and-overall-recycling"
PDF="https://www.nea.gov.sg/docs/default-source/default-document-library/waste-and-recycling-statistics-2015-to-2025.pdf"

def normalize_text(text,meta):
    sections=list(re.finditer(r"Waste Statistics and Recycling Rate\s+(20\d{2})",text))
    rows=[]
    for pos,section in enumerate(sections):
        year=int(section.group(1))
        block=text[section.end():sections[pos+1].start() if pos+1<len(sections) else len(text)]
        found=[]
        for line in block.splitlines():
            match=re.match(r"^\s*(.+?)\s+([\d,]+)\s+([\d,]+)\s+(\d+%|N\.A\.)\s+([\d,]+)\s*$",line)
            if not match:
                continue
            material,generated,recycled,rate,disposed=match.groups()
            found.append(material)
            for metric,number in (("generated",generated),("recycled",recycled),("disposed",disposed)):
                rows.append(metadata(meta,country="SG",geography="Singapore",year=year,
                    waste_scope="domestic and non-domestic; includes construction and demolition",
                    material=material,process_stage="reported broad recycling; wood fuel included",
                    numerator_definition=metric,denominator_definition="all waste of specified material",
                    metric=metric,value=int(number.replace(",",""))*1000,unit="t/year",raw_unit="1000 tonnes",
                    reported_recycling_rate_pct=None if rate=="N.A." else int(rate.rstrip("%")),
                    source_locator=f"PDF table Waste Statistics and Recycling Rate {year}, {material}",
                    comparability_flag="not_harmonized",uncertainty="천 톤 단위 반올림; 목재·조경폐기물 연료 사용이 재활용에 포함됨"))
        if "Overall" not in found:
            raise ExternalDataError(f"NEA {year} 표의 Overall 행을 확인할 수 없습니다.")
    if not rows:
        raise ExternalDataError("NEA PDF 표 구조를 확인할 수 없습니다.")
    return rows

def collect(*,root,year=2024):
    raw,meta=fetch("nea",PDF,"nea_waste_2015_2025.pdf",root=root,license="Singapore Open Data Licence; source conditions apply",redistribution="attribution_required")
    text="\n".join(page.extract_text(extraction_mode="layout") for page in PdfReader(BytesIO(raw)).pages)
    return save_records(normalize_text(text,meta),meta,root=root)
