import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from src.model import ROOT, load_config, load_observations, baseline, compare, best, sensitivity, evaluate, household_saving
from src.presentation import korean_table, PARAMETERS
from src.provenance import inputs_table
from src.kosis import KosisError, collect_all, display_table

st.set_page_config(page_title="분리배출 정책 실험실", layout="wide")
st.title("분리배출 정책 실험실")
st.caption("국가통계포털 KOSIS의 전국 현황 · 구로구 실제 처리실적에 근거한 조건부 정책 실험")
config = load_config()
config["common"]["time_value"] = st.sidebar.slider("가정: 가계 시간가치(원/시간)", 0, 30000, int(config["common"]["time_value"]), 10)
target = st.sidebar.slider("가정: 최소 재생원료 전환비율(%)", 0, 100, 0)/100
config["common"]["processing_yield"] = st.sidebar.slider("가정: 선별 후 최종 재처리 수율(%)", 0, 100, round(config["common"]["processing_yield"] * 100))/100
scenario_b = next(s for s in config["scenarios"] if s["id"] == "B")
change = st.sidebar.number_input("가정: B의 선별처리 예산 증감(%)", min_value=-100.0, value=round((scenario_b["sorting_budget_multiplier"] - 1) * 100, 6), step=1.0)
scenario_b["sorting_budget_multiplier"] = 1 + change/100
st.sidebar.caption("시간가치는 가구당 계산기에만 적용합니다. 목표는 A보다 낮게 입력해도 A 수준을 유지합니다.")
table = compare(config, target)
selected_id = best(table)
st.info("비교액은 공공예산 대리값과 추가 투자 연간화의 합입니다. 총사회적 비용이 아닙니다. 연간 시설용량·법규는 미검증이며, 최종 재처리 수율과 대안 효과는 가정입니다.")
kosis_tab, observed_tab, simulation_tab, household_tab, evidence_tab = st.tabs(["국가통계포털(KOSIS)", "구로구 실제 실적", "조건부 정책 실험", "가구당 시간 비용", "입력 근거와 출처"])

with kosis_tab:
    st.subheader("KOSIS 전국 생활폐기물 발생량")
    public = pd.read_csv(ROOT / "data/processed/kosis_public_waste.csv")
    latest = public.sort_values("reference_year").iloc[-1]
    st.metric(f"{int(latest.reference_year)}년 생활폐기물 발생량", f"{latest.value:,.0f} 톤/년")
    chart = public.rename(columns={"reference_year":"연도", "value":"생활폐기물 발생량(톤/년)"})
    figure = px.line(chart, x="연도", y="생활폐기물 발생량(톤/년)", markers=True)
    figure.update_xaxes(dtick=1)
    st.plotly_chart(figure, width="stretch")
    st.dataframe(display_table(public[["reference_year","value","unit","source_url","evidence_grade"]]), hide_index=True)
    st.download_button("KOSIS 전국 추세 CSV", display_table(public).to_csv(index=False).encode("utf-8-sig"), "kosis_waste_trend.csv", "text/csv")
    st.caption("KOSIS 공개 지표의 원수치입니다. API 인증을 거친 상세 통계표 자료와 수집 경로를 구분해 기록했습니다. 생활폐기물과 사업장비배출 포함 생활계 전체는 범위가 다릅니다.")
    st.markdown("[KOSIS 공식 지표](https://kosis.kr/visual/nsportalStats/detailContents.do?listId=C&statJipyoId=3664&vStatJipyoId=5061) · [상세 원표](https://kosis.kr/statHtml/statHtml.do?orgId=106&tblId=DT_106N_29_2020005&conn_path=I2)")
    st.subheader("지역·품목·처리방법별 상세 자료")
    st.caption("상세 OpenAPI에는 발급된 KOSIS_API_KEY가 필요합니다. 프로젝트 .env에 설정한 뒤 아래 버튼을 누르세요. 키를 화면에 입력하거나 표시하지 않습니다.")
    if st.button("KOSIS 공식 상세 자료 불러오기"):
        try:
            with st.spinner("KOSIS 상세 통계 수집 중"):
                frames = collect_all()
            st.success(f"통계표 {len(frames)}개를 수집했습니다.")
        except KosisError as error:
            st.error(str(error))
    files = sorted((ROOT / "data/processed/kosis").glob("*.csv"))
    if files:
        for file in files:
            frame = pd.read_csv(file, keep_default_na=False, dtype={"class_1_id":str,"class_2_id":str,"item_id":str})
            st.dataframe(display_table(frame), hide_index=True)
            st.download_button("상세 원표 CSV 내려받기", display_table(frame).to_csv(index=False).encode("utf-8-sig"), file.name, "text/csv", key=file.stem)
        st.caption("지역·품목의 상하위 계층에 총계·소계가 함께 있습니다. 행을 단순 합산하면 중복됩니다. 최종 재생원료 수율은 이 통계로 자동 추정하지 않습니다.")
    else:
        st.info("상세 API 데이터는 아직 수집하지 않았습니다. 공개 전국 추세는 위에서 바로 사용할 수 있습니다.")
    st.markdown("[KOSIS OpenAPI 인증키 신청](https://kosis.kr/openapi/serviceUse/serviceUseUnityReg_01Detail.do)")

with observed_tab:
    obs = baseline(config)
    cols = st.columns(3)
    cols[0].metric("2024 처리대상량(원표: 재활용 발생량)", f"{obs['handled_t']:,.0f} t")
    cols[1].metric("관측 선별 회수량", f"{obs['sorted_t']:,.0f} t")
    cols[2].metric("관측 선별률", f"{obs['sorted_t']/obs['handled_t']:.2%}")
    st.caption("구로구의 수거·선별 행정처리 흐름입니다. 구 전체 가정의 발생량이나 최종 재생원료 생산량이 아닙니다. 품목별 구성은 미공표입니다.")
    history = load_observations()
    display = history[["reference_year", "handled_t", "sorted_t", "residue_t", "collection_budget_krw", "sorting_budget_krw", "total_budget_krw"]].rename(columns={
        "reference_year": "연도", "handled_t": "처리대상량(t)", "sorted_t": "선별량(t)", "residue_t": "선별 잔재(t)",
        "collection_budget_krw": "수거운반 예산(원)", "sorting_budget_krw": "선별처리 예산(원)", "total_budget_krw": "총 소요예산(원)"})
    st.dataframe(display, hide_index=True)
    trend = display.melt(id_vars="연도", value_vars=["처리대상량(t)", "선별량(t)", "선별 잔재(t)"], var_name="처리 흐름", value_name="연간 물량(t)")
    fig = px.line(trend, x="연도", y="연간 물량(t)", color="처리 흐름", markers=True)
    fig.update_xaxes(dtick=1)
    st.plotly_chart(fig, width="stretch")
    st.caption("2022~2024 예산은 각 연도의 명목금액입니다. 비용 배율 계산은 2024년 자료만 사용합니다.")
    st.markdown("[구로구의회 원보고서: 표5·6, 인쇄 57~58쪽](https://www.guroc.go.kr/kr/bbs/download.do?bbs_id=memnotice&uid=10C5C2B6918247C7947B3A54914B8714)")
    st.subheader("전국 생활계폐기물 추세 — 별도 참고")
    national = pd.read_csv(ROOT / "data/processed/korea_waste_trend.csv")
    fig = px.line(national.rename(columns={"reference_year":"연도", "value":"생활계 발생량(t/일)"}), x="연도", y="생활계 발생량(t/일)", markers=True)
    fig.update_xaxes(dtick=1)
    st.plotly_chart(fig, width="stretch")
    st.caption("전국 생활계 전체와 구로구 행정처리 흐름은 모집단이 달라 서로 배율 보정하거나 합산하지 않습니다.")

with simulation_tab:
    st.metric("등록 대안 중 조건부 최소 포함비용안", selected_id or "충족 대안 없음")
    st.markdown("A는 관측 기준선, B는 2023년 선별률 회복 목표, C는 비용 절감·회수 저하 실험, D는 설비 보강 목표입니다. 구로구는 이미 혼합 재활용품을 선별하므로 혼합수거 도입의 인과효과를 계산하지 않습니다.")
    shown = korean_table(table)
    st.dataframe(shown, hide_index=True)
    st.download_button("한글 비교 결과 CSV", shown.to_csv(index=False).encode("utf-8-sig"), "scenarios.csv", "text/csv")
    st.download_button("현재 입력값·근거 CSV", korean_table(inputs_table(config, target)).to_csv(index=False).encode("utf-8-sig"), "input_evidence.csv", "text/csv")
    st.caption(f"현재 최소 전환비율 요청: {target:.1%}. 실제 제약은 요청값과 A의 가정 적용 전환비율 중 큰 값입니다. 선별률과 전환비율은 다른 지표입니다.")
    costs = shown.melt(id_vars="시나리오", value_vars=["수거운반 예산 대리값(원/년)", "선별처리 예산 대리값(원/년)", "추가 투자 연간화(원/년)"], var_name="비용 구분", value_name="연간 포함비용(원)")
    st.plotly_chart(px.bar(costs, x="시나리오", y="연간 포함비용(원)", color="비용 구분"), width="stretch")
    st.plotly_chart(px.scatter(shown, x="가정 적용 재생원료 전환비율(%)", y="비교 포함비용(원/년)", color="시나리오", symbol="재생원료 목표 충족", hover_name="대안 설명"), width="stretch")
    selected = st.selectbox("물질수지 시나리오", table.id.tolist(), format_func=lambda key: key + " · " + table.loc[table.id == key, "name"].iloc[0])
    scenario = next(s for s in config["scenarios"] if s["id"] == selected)
    _, flows = evaluate(config, scenario)
    st.dataframe(korean_table(flows), hide_index=True)
    st.plotly_chart(go.Figure(go.Sankey(node=dict(label=["처리대상량", "선별 회수", "예상 재생원료", "선별 잔재", "가정 공정손실"]), link=dict(source=[0,0,1,1], target=[1,3,2,4], value=[flows.sorted.sum(),flows.sorting_loss.sum(),flows.recycled.sum(),flows.processing_loss.sum()]))), width="stretch")
    st.caption("공정손실의 실제 처분 경로는 미확인입니다. 별도 처분비는 선별처리 예산과의 중복 여부가 확인되지 않아 더하지 않습니다.")
    st.subheader("민감도 분석")
    st.caption("최종 수율은 70·85·95%, 예산 배율은 현재 입력의 0.9·1.0·1.1배로 각각 바꿉니다. 확률·신뢰구간을 뜻하지 않습니다.")
    experiments = sensitivity(config, target)
    for parameter, name in PARAMETERS.items():
        frame = korean_table(experiments.loc[experiments.parameter == parameter])
        outcome = "가정 적용 재생원료 전환비율(%)" if parameter == "processing_yield" else "비교 포함비용(원/년)"
        st.plotly_chart(px.line(frame, x="실험 설정값", y=outcome, color="시나리오", markers=True, title=name, hover_data=["재생원료 목표 충족", "조건부 최소비용안"]), width="stretch")
    st.download_button("한글 민감도 결과 CSV", korean_table(experiments).to_csv(index=False).encode("utf-8-sig"), "sensitivity.csv", "text/csv")

with household_tab:
    st.subheader("가구당 시간 절약의 조건부 가치")
    minutes = st.slider("가정: 한 가구의 주당 절약 시간(분)", 0, 60, 5)
    st.metric("가구당 연간 시간 절약 가치", f"{household_saving(minutes, config['common']['time_value']):,.0f} 원")
    st.code(f"{minutes}분 × 52주 ÷ 60 × {config['common']['time_value']:,}원/시간")
    st.markdown("2024년 공식 최저임금 **9,860원/시간**을 시간가치의 기준 가정으로 사용했습니다. 실제 관측된 가계 기회비용은 아닙니다.")
    st.caption("이 사례의 수거대상 가구 수와 분리배출 시간 실측값이 없어 전체 가계비·정책 비교 합계에는 반영하지 않습니다.")
    st.markdown("[최저임금위원회 연도별 결정현황](https://www.minimumwage.go.kr/minWage/policy/decisionMain.do)")

with evidence_tab:
    st.subheader("실행에 적용한 입력과 근거")
    st.dataframe(korean_table(inputs_table(config, target)), hide_index=True)
    st.markdown("최종 수율 85%는 구로구 실측값이 아닙니다. [폐합성수지 시설 연구](https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART001757031)는 품목·연도가 달라 참고만 합니다.")
    st.caption("B: 공식 의회 보고서에 재수록된 구청 행정자료. D: 외생 가정. 미확인 항목은 0으로 대체하지 않습니다. 화면에서 바꾼 값은 입력 근거 CSV에도 반영됩니다.")
    st.dataframe(korean_table(pd.read_csv(ROOT / "data/sources.csv", keep_default_na=False)), hide_index=True)
