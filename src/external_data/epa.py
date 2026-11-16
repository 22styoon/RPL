"""EPA 공식 본문의 2018 MSW 요약 수치. 미국 short ton 단위를 보존한다."""
from html.parser import HTMLParser
import re
from .common import ExternalDataError,fetch,metadata,save_records
PAGE="https://www.epa.gov/facts-and-figures-about-materials-waste-and-recycling/national-overview-facts-and-figures-materials"
SHORT_TON_TO_T=0.90718474

class Text(HTMLParser):
    def __init__(self):
        super().__init__();self.parts=[]
    def handle_data(self,data):
        self.parts.append(data)

def normalize_html(html,meta):
    parser=Text();parser.feed(html)
    text=" ".join(" ".join(parser.parts).split())
    patterns={
        "generated":r"total generation of municipal solid waste \(MSW\) in 2018 was ([\d.]+) million tons",
        "recycled":r"approximately ([\d.]+) million tons were recycled",
        "composted":r"and ([\d.]+) million tons were composted",
    }
    rows=[]
    for metric,pattern in patterns.items():
        match=re.search(pattern,text,re.I)
        if not match:
            raise ExternalDataError("EPA 요약 표의 검증된 문장을 찾지 못했습니다: "+metric)
        raw=float(match.group(1))*1000000
        rows.append(metadata(meta,country="US",geography="United States",year=2018,
            waste_scope="US MSW excluding C&D and industrial nonhazardous waste",material="전체",
            process_stage=metric,numerator_definition=metric,denominator_definition="US municipal solid waste",
            metric=metric,raw_value=raw,raw_unit="US short ton",value=raw*SHORT_TON_TO_T,unit="t/year",
            measurement_type="official_estimate",source_locator="The Current National Picture, opening summary",
            uncertainty="Rounded summary; 2018 food measurement methodology changed",comparability_flag="not_harmonized"))
    return rows

def collect(*,root,year=2018):
    if year!=2018:
        raise ExternalDataError("이 수집기는 공식 요약의 2018년 자료만 파싱합니다.")
    raw,meta=fetch("epa",PAGE,"epa_2018_overview.html",root=root,license="US EPA public information; attribution and third-party exclusions",redistribution="check_third_party_materials")
    return save_records(normalize_html(raw.decode("utf-8"),meta),meta,root=root)
