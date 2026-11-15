import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from src.model import ROOT, load_config, load_observations, baseline, household_saving
from src.presentation import korean_table
from src.provenance import inputs_table
from src.kosis import KosisError, collect_all, display_table
from src.kosis_analysis import display_materials
from src.policy_ui import render_policy_experiment
from src.facility_ui import render_facility_experiment

st.set_page_config(page_title="분리배출 정책 실험실", layout="wide")
st.title("분리배출 정책 실험실")
st.caption("국가통계포털 KOSIS의 전국 현황 · 구로구 실제 처리실적에 근거한 조건부 정책 실험")
config = load_config()
st.caption("정책 효과·최종 수율·미관측 비용은 외생 가정으로 구분하며, 법규·안전성까지 검증한 정책 권고는 아닙니다.")
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
    st.caption("인증 OpenAPI로 수집한 상세 통계를 표시합니다. 새로 불러오면 로컬 설정의 인증키를 사용해 원표와 품목 집계를 함께 갱신합니다.")
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
            st.caption(f"수집된 상세 관측 셀: {len(frame):,}개 · 단위: 톤/년")
            if "processing_method" in frame:
                regions = ["전국"] + sorted(set(frame.geography) - {"전국"})
                region = st.selectbox("상세 통계 지역", regions, key="region_"+file.stem)
                subset = frame.loc[frame.geography == region]
                route = st.selectbox("상세 통계 배출방식", ["전체"]+sorted(subset.emission_route.unique().tolist()), key="route_"+file.stem)
                if route != "전체":
                    subset = subset.loc[subset.emission_route == route]
                methods = st.multiselect("상세 통계 처리방법", sorted(subset.processing_method.unique().tolist()), default=["발생량","물질재활용"], key="methods_"+file.stem)
                subset = subset.loc[subset.processing_method.isin(methods)]
                st.dataframe(display_table(subset[["geography","emission_route","class_1_path","processing_method","value","unit","reference_year"]]), hide_index=True)
                material_path = ROOT / f"data/processed/kosis_materials_{int(frame.reference_year.iloc[0])}.csv"
                if material_path.exists():
                    materials = pd.read_csv(material_path)
                    materials = materials.loc[materials.geography == region]
                    st.subheader(f"{region} 대응 4품목 발생·처리 현황")
                    columns = ["material","generated_t","material_recycling_t","energy_recovery_t","material_treatment_rate_pct"]
                    shown_materials = display_materials(materials[columns])
                    st.dataframe(shown_materials, hide_index=True)
                    melted = shown_materials.melt(id_vars="품목 그룹", value_vars=["발생량(톤/년)","물질재활용 처리량(톤/년)","에너지회수(톤/년)"], var_name="통계 구분", value_name="물량(톤/년)")
                    st.plotly_chart(px.bar(melted, x="품목 그룹", y="물량(톤/년)", color="통계 구분", barmode="group"), width="stretch")
                    st.download_button("지역별 4품목 한글 CSV", display_materials(materials).to_csv(index=False).encode("utf-8-sig"), f"kosis_materials_{region}.csv", "text/csv", key="materials_"+file.stem)
                    st.caption("두 배출방식의 대응 품목을 묶은 파생그룹입니다. 영농폐비닐과 복합제품 재질은 제외합니다. 물질재활용 처리량은 최종 재생원료 생산량이 아닙니다. 공개 지표의 정수 표시와 상세 원표의 소수점 표기는 정밀도가 다릅니다.")
            else:
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
    mode = st.radio("실험 대상", ["KOSIS 지역별 4품목", "구로구 시설·예산"], horizontal=True, key="policy_mode")
    if mode == "KOSIS 지역별 4품목":
        render_policy_experiment()
    else:
        render_facility_experiment(config)

with household_tab:
    st.subheader("가구당 시간 절약의 조건부 가치")
    unit_time_value = st.number_input("가정: 가구당 계산기의 시간가치(원/시간)", min_value=0, value=int(config["common"]["time_value"]), step=10)
    minutes = st.slider("가정: 한 가구의 주당 절약 시간(분)", 0, 60, 5)
    st.metric("가구당 연간 시간 절약 가치", f"{household_saving(minutes, unit_time_value):,.0f} 원")
    st.code(f"{minutes}분 × 52주 ÷ 60 × {unit_time_value:,}원/시간")
    st.markdown("2024년 공식 최저임금 **9,860원/시간**을 시간가치의 기준 가정으로 사용했습니다. 실제 관측된 가계 기회비용은 아닙니다.")
    st.caption("이 사례의 수거대상 가구 수와 분리배출 시간 실측값이 없어 전체 가계비·정책 비교 합계에는 반영하지 않습니다.")
    st.markdown("[최저임금위원회 연도별 결정현황](https://www.minimumwage.go.kr/minWage/policy/decisionMain.do)")

with evidence_tab:
    st.subheader("기본 자료·가정의 근거")
    st.dataframe(korean_table(inputs_table(config)), hide_index=True)
    st.markdown("최종 수율 85%는 구로구 실측값이 아닙니다. [폐합성수지 시설 연구](https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART001757031)는 품목·연도가 달라 참고만 합니다.")
    st.caption("B: 공식 의회 보고서에 재수록된 구청 행정자료. D: 외생 가정. 미확인 항목은 0으로 대체하지 않습니다. 이 표는 구로구 기본 설정의 근거입니다. 실제 실행에 적용한 변경값은 각 정책 실험의 입력 스냅샷과 ZIP에서 확인합니다.")
    st.dataframe(korean_table(pd.read_csv(ROOT / "data/sources.csv", keep_default_na=False)), hide_index=True)

    report_path = ROOT / "docs/interim_development_report_2026-11-16.md"
    if report_path.exists():
        st.download_button("중간 개발 보고서 내려받기", report_path.read_bytes(), report_path.name, "text/markdown")
