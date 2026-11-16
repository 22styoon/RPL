from .common import AnalysisResult,require_unique,require_numeric

def regional_profiles(frame):
    require_unique(frame,["geography","material","reference_year"])
    if frame.reference_year.nunique()!=1:
        raise ValueError("서로 다른 연도를 지역 합계로 합치지 않습니다.")
    data=frame.loc[frame.geography!="전국"].copy()
    require_numeric(data,["generated_t","material_recycling_t"])
    counts=data.groupby("geography").material.nunique()
    if len(counts)!=17 or not (counts==4).all():
        raise ValueError("17개 시도 각각 대응 4품목이 필요합니다.")
    table=data.groupby("geography",as_index=False)[["generated_t","material_recycling_t"]].sum()
    table["물질재활용 처리비율(%)"]=table.material_recycling_t/table.generated_t*100
    table=table.rename(columns={"geography":"시도","generated_t":"4품목 발생량(t/년)","material_recycling_t":"물질재활용 처리량(t/년)"}).sort_values("물질재활용 처리비율(%)")
    return AnalysisResult("regional_profiles","지역·재질별 비교","17개 시도의 처리 구성 차이",
        "대응 4품목의 물질재활용 처리비율은 지역별로 얼마나 차이가 나는가?",
        table,table,"barh","시도","물질재활용 처리비율(%)",None,"%","2024",sorted(set(data.source_url)),
        f"17개 시도별 발생량을 분모로 합산한 비율이다. 지역 중앙값은 {table['물질재활용 처리비율(%)'].median():.2f}%이다.",
        ["인구·가구 수 자료 미연결로 1인당·가구당 발생량은 산출하지 않는다.","지역의 품목 구성·반입 반출·시설 여건 차이가 있다. 정렬 순서를 정책 성과 순위로 해석하지 않는다.","전국 행을 시도 합계에 다시 더하지 않는다."],
        "src/analysis/regional.py")
