import numpy as np
import pandas as pd
MATERIALS=("폐지류","폐합성수지류","폐금속류","폐유리류")
def validate_materials(frame,*,region_key="geography",require_four=True):
    needed={region_key,"material","reference_year","generated_t","material_recycling_t"}
    if not needed<=set(frame):
        raise ValueError("지역·연도·재질·관측 물량 필수 열이 없습니다.")
    if frame.empty or frame.reference_year.nunique()!=1 or not frame.reference_year.eq(2024).all():
        raise ValueError("2024 동일 연도 실측 행이 필요합니다.")
    if frame[region_key].isna().any() or frame.duplicated([region_key,"reference_year","material"]).any():
        raise ValueError("지역 키 결측·중복")
    if not set(frame.material)<=set(MATERIALS):
        raise ValueError("검증하지 않은 재질")
    for name in ("generated_t","material_recycling_t"):
        values=pd.to_numeric(frame[name],errors="raise")
        if values.isna().any() or not np.isfinite(values).all():
            raise ValueError("물량 결측·비유한 값")
    if (frame.generated_t<=0).any() or (frame.material_recycling_t<0).any() or (frame.material_recycling_t>frame.generated_t).any():
        raise ValueError("G>0 및 0<=M<=G 위반; 자동 클리핑 금지")
    if require_four and not frame.groupby(region_key).material.nunique().eq(4).all():
        raise ValueError("지역별 대응 4품목 불완전")
    return frame

def verify_lineage(frame):
    required=["source_id","source_url","source_locator","retrieved_at","verification_status","compatibility_status"]
    if not set(required)<=set(frame):
        raise ValueError("출처 추적 필드 부족")
    if frame[required].isna().any().any() or frame[required].astype(str).apply(lambda x:x.str.strip().eq("")).any().any():
        raise ValueError("출처 추적 필드 결측")
