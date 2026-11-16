import pandas as pd
from .common import AnalysisResult

def missingness(frame,columns):
    if frame.empty:
        raise ValueError("빈 자료에는 결측률의 분모가 없습니다.")
    rows=[]
    for column in columns:
        series=frame[column] if column in frame else pd.Series(pd.NA,index=frame.index)
        missing=series.isna()|series.astype(str).str.strip().eq("")
        rows.append({"필드":column,"관측 행수":len(frame),"미입력 행수":int(missing.sum()),"미입력 비율(%)":float(missing.mean()*100)})
    return pd.DataFrame(rows)

def facility_quality(frame):
    fields={"business_name":"업체명","province_name":"시도명","district_name":"시군구명","facility_name":"별도 시설명","facility_capacity":"연간 시설용량","reference_period":"기준연도"}
    table=missingness(frame,list(fields))
    table["필드"]=table["필드"].map(fields)
    return AnalysisResult("facility_quality","자료 출처·품질","시설 명부에서 실제로 제공되는 정보",
        "추가 수집한 처리시설 명부는 비용·용량 분석에 필요한 항목을 얼마나 제공하는가?",
        table,table,"barh","필드","미입력 비율(%)",None,"%","수집일 2026-11-16",
        ["https://www.data.go.kr/data/15172490/openapi.do"],f"{len(frame):,}행의 필드별 결측을 확인했다. 빈 값을 용량 0이나 비용 0으로 해석하지 않는다.",
        ["업체 ID는 개별 시설 고유 ID와 다르다.","API에 제공되지 않은 필드를 관측한 것으로 보완하지 않는다."],"src/analysis/quality.py",measurement_type="관측 자료 품질")
