import pandas as pd
from .common import AnalysisResult,require_unique,require_numeric

def guro_flows(frame):
    require_unique(frame,["reference_year"])
    require_numeric(frame,["handled_t","sorted_t","residue_t"])
    if ((frame.sorted_t+frame.residue_t-frame.handled_t).abs()>1e-6).any():
        raise ValueError("구로구 선별 수지가 일치하지 않습니다.")
    table=frame[["reference_year","handled_t","sorted_t","residue_t"]].sort_values("reference_year").rename(columns={"reference_year":"연도","handled_t":"처리대상량(t)","sorted_t":"선별량(t)","residue_t":"잔재량(t)"})
    table["선별 회수율(%)"]=table["선별량(t)"]/table["처리대상량(t)"]*100
    plot=table.melt(id_vars="연도",value_vars=["처리대상량(t)","선별량(t)","잔재량(t)"],var_name="흐름",value_name="연간 물량(t)")
    latest=table.iloc[-1]
    return AnalysisResult("guro_flows","시설 및 비용 분석","구로구 선별 회수와 잔재 추이",
        "행정처리 대상량 증가가 선별 회수량 증가와 함께 나타났는가?",table,plot,"line","연도","연간 물량(t)","흐름","t/년","2022–2024",
        sorted(set(frame.source_url)),f"2024년 선별 회수율 {latest['선별 회수율(%)']:.2f}%, 선별량 {latest['선별량(t)']:,.0f}t이다.",
        ["단일 지역·3개 연도의 행정처리 흐름이며 개별 가구 전체 발생량이 아니다.","최종 재처리 수율을 적용하지 않은 관측 선별 단계 결과다."],"src/analysis/costs.py")

def guro_budgets(frame):
    require_unique(frame,["reference_year"])
    require_numeric(frame,["collection_budget_krw","sorting_budget_krw","total_budget_krw","handled_t"])
    if ((frame.collection_budget_krw+frame.sorting_budget_krw-frame.total_budget_krw).abs()>1).any() or (frame.handled_t<=0).any():
        raise ValueError("예산 합계·처리량 분모가 맞지 않습니다.")
    table=frame[["reference_year","handled_t","collection_budget_krw","sorting_budget_krw","total_budget_krw"]].sort_values("reference_year").rename(columns={"reference_year":"연도","handled_t":"처리대상량(t)","collection_budget_krw":"수거운반 예산(원)","sorting_budget_krw":"선별처리 예산(원)","total_budget_krw":"합계 예산(원)"})
    table["처리대상량당 예산 참고비율(원/t)"]=table["합계 예산(원)"]/table["처리대상량(t)"]
    plot=table.melt(id_vars="연도",value_vars=["수거운반 예산(원)","선별처리 예산(원)"],var_name="예산 항목",value_name="명목 예산(억원)")
    plot["명목 예산(억원)"]/=1e8
    return AnalysisResult("guro_budgets","시설 및 비용 분석","구로구 수거·선별 공개 예산 추이",
        "공개 예산의 총액·구성과 처리대상량당 예산 참고비율은 어떻게 변했는가?",table,plot,"stacked","연도","명목 예산(억원)","예산 항목","명목 억원/년","2022–2024",
        sorted(set(frame.source_url)),f"2024년 수거·선별 예산 합계 {table['합계 예산(원)'].iloc[-1]/1e8:.2f}억원이다.",
        ["공개 예산이며 실집행액·사회적 실물원가 또는 검증 처리단가가 아니다.","연도별 명목 원화이며 물가 조정하지 않았다.","시설 인건비가 포함된 예산에 노동시간 가치를 다시 더하지 않는다."],
        "src/analysis/costs.py",measurement_type="공개 예산 대리값")
