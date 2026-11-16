"""실제 확인한 2024 XLSX의 F열 발생량·H열 총계 물질재활용만 사용."""
from io import BytesIO
from zipfile import ZipFile
import pandas as pd
import numpy as np
SHEET="2-나-1). (시군구) 생활(가정)폐기물 발생량"
MIXED={"폐지류":"폐지류","폐합성수지류":"폐합성수지류","폐금속류":"폐금속류","폐유리류":"폐유리류"}
SEPARATE={"폐지류":"폐지류","폐합성수지류":"폐합성수지류","고철류":"폐금속류","금속캔":"폐금속류","폐유리병류":"폐유리류"}

def workbook_from_zip(raw):
    with ZipFile(BytesIO(raw)) as archive:
        found=[info for info in archive.infolist() if "02_01_" in info.filename and info.filename.endswith(".xlsx")]
        if len(found)!=1 or found[0].file_size>30_000_000:
            raise ValueError("생활계폐기물 XLSX 확인 실패")
        return BytesIO(archive.read(found[0])),found[0].filename

def parse_counties(raw,manifest):
    book,name=workbook_from_zip(raw)
    frame=pd.read_excel(book,sheet_name=SHEET,header=None)
    if "발생량" not in str(frame.iat[3,5]) or str(frame.iat[5,7])!="물질재활용" or "톤/년" not in str(frame.iat[2,29]):
        raise ValueError("검증한 원표 헤더·단위 변경")
    observations=[];sido=county=route=group=None
    clean=lambda v:None if pd.isna(v) else "".join(str(v).split())
    def number(v):
        if pd.isna(v) or str(v).strip() in ("","-"):return np.nan
        if isinstance(v,bool):raise ValueError("참거짓 물량 오류")
        return float(v)
    for row_index,row in frame.iloc[6:].iterrows():
        if pd.notna(row[0]) and pd.notna(row[1]):
            sido,county=str(row[0]).strip(),str(row[1]).strip()
            route=group=None
        if pd.notna(row[2]):route=clean(row[2]);group=None
        if pd.notna(row[3]):group=clean(row[3])
        material=MIXED.get(clean(row[4])) if route=="종량제방식등혼합배출" else SEPARATE.get(group) if route=="재활용가능자원분리배출" else None
        if material and sido and county:
            observations.append(dict(sido_name=sido,sigungu_name=county,material=material,material_raw=str(row[3])+" / "+str(row[4]),
                generated_t=number(row[5]),material_recycling_t=number(row[7]),source_row=row_index+1,
                emission_route=route))
    source=pd.DataFrame(observations)
    rows=[]
    for (sido,county,material),part in source.groupby(["sido_name","sigungu_name","material"],sort=False):
        rows.append(dict(sido_name=sido,sigungu_name=county,material=material,material_raw="; ".join(part.material_raw),
            reference_year=2024,generated_t=part.generated_t.sum(min_count=len(part)),
            material_recycling_t=part.material_recycling_t.sum(min_count=len(part)),
            separately_collected_t=None,sorted_t=None,residue_t=None,final_recycled_t=None,
            emission_route="종量制混合・再生可能資源分離排出".replace("종量制混合・再生可能資源分離排出","종량제방식 등 혼합배출 + 재활용 가능자원 분리배출"),
            measurement_stage="material_recycling_treatment",waste_scope="생활(가정)폐기물 대응 4품목",
            source_id="kr_waste_2024_detail",source_url=manifest["source_url"],
            source_locator=name+" | "+SHEET+" | F/H rows "+",".join(str(x) for x in part.source_row),
            retrieved_at=manifest["retrieved_at"],raw_component_count=len(part),
            verification_status="source_cells_parsed",compatibility_status="geocode_and_QA_pending"))
    return pd.DataFrame(rows)
