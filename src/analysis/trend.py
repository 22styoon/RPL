"""동일 정의 시계열의 연간 증감률. 짧은 시계열에서 인과효과를 추정하지 않는다."""
import numpy as np
from .common import AnalysisResult,require_unique,require_numeric

def yearly_trend(frame):
    require_unique(frame,["reference_year"])
    require_numeric(frame,["value"])
    if any(frame[c].nunique(dropna=False)!=1 for c in ("geography","unit","waste_scope")):
        raise ValueError("동일 지역·단위·폐기물 범위만 시계열로 연결합니다.")
    data=frame.sort_values("reference_year").copy()
    if len(data)<2 or data.value.iloc[0]<=0:
        raise ValueError("양의 기준값과 2개 이상 연도가 필요합니다.")
    table=data[["reference_year","value"]].rename(columns={"reference_year":"연도","value":"발생량(t/년)"})
    table["전년 대비 증감률(%)"]=table["발생량(t/년)"].pct_change(fill_method=None)*100
    table.loc[table["연도"].diff()!=1,"전년 대비 증감률(%)"]=np.nan
    table["첫해=100 지수"]=table["발생량(t/년)"]/table["발생량(t/년)"].iloc[0]*100
    years=int(table["연도"].iloc[-1]-table["연도"].iloc[0])
    if years<=0:
        raise ValueError("연도 간격이 필요합니다.")
    cagr=((table["발생량(t/년)"].iloc[-1]/table["발생량(t/년)"].iloc[0])**(1/years)-1)*100
    latest=table.iloc[-1]
    return AnalysisResult("domestic_trend","국내 통계 현황","국내 생활폐기물 발생량 추이",
        "같은 정의의 전국 생활폐기물 발생량은 연도별로 어떻게 변했는가?",table,table,"line","연도","발생량(t/년)",None,"t/년",f"{table['연도'].min()}–{table['연도'].max()}",
        sorted(set(data.source_url)),f"최근 관측 {int(latest['연도'])}년 {latest['발생량(t/년)']:,.0f}t, 관측 기간 연평균 증감률 {cagr:.2f}%.",
        ["관측 연도 5개에 대한 기술통계이며 정책의 인과효과·장래 예측을 추정하지 않는다.","사업장비배출을 포함한 생활계 전체 시계열과 혼합하지 않는다."],
        "src/analysis/trend.py",extra={"cagr_pct":float(cagr)})
