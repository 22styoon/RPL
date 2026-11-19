"""통계 분석 보고서의 Streamlit 프런트엔드. 기본 화면에서 정책 가정을 실행하지 않는다."""
import json
from pathlib import Path
import pandas as pd
import plotly.io as pio
import streamlit as st
import yaml
from src.model import ROOT
from src.analysis.pipeline import TITLE

MENU=["국내 통계 현황","지역·재질별 비교","시도 표준화 분석","해외 통계 비교","시설 및 비용 분석","가구 시간 분석","선행연구","자료 출처·품질","가정 기반 민감도 분석"]
REPORT=ROOT/"outputs/reports/statistical_analysis"
OUTPUT=ROOT/"outputs"

def load_manifest():
    path=REPORT/"manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

def artifact_path(relative):
    output=OUTPUT.resolve()
    path=(output/str(relative).replace("\\","/")).resolve()
    if not path.is_relative_to(output):
        raise ValueError("출력 폴더 밖의 결과는 표시하지 않습니다.")
    return path

def render_analysis(entry):
    st.subheader(entry["title"])
    st.markdown("**연구 질문** · "+entry["question"])
    st.caption(f'{entry["measurement_type"]} · 기준 {entry["year_label"]} · 단위 {entry["unit"]} · 분석표 {entry["row_count"]}행')
    st.write(entry["interpretation"])
    st.plotly_chart(pio.read_json(artifact_path(entry["figure_json"])),width="stretch",key="figure_"+entry["analysis_id"])
    with st.expander("분석표·출처·한계·다운로드"):
        path=artifact_path(entry["table"])
        st.dataframe(pd.read_csv(path),hide_index=True)
        columns=st.columns(3)
        for column,label,field,mime in zip(columns,["분석표 CSV","정적 PNG","정적 SVG"],["table","png","svg"],["text/csv","image/png","image/svg+xml"]):
            asset=artifact_path(entry[field])
            column.download_button(label,asset.read_bytes(),asset.name,mime,key=entry["analysis_id"]+"_"+field)
        for url in entry["sources"]:
            st.markdown("[공식 원자료]("+url+")")
        for note in entry["limitations"]:
            st.caption("• "+note)
        st.caption("분석 코드: "+entry["code_source"]+" · 그래프 수치는 함께 저장된 *_plot.csv에서 확인")

def render_category(manifest,category):
    entries=[row for row in manifest["analyses"] if row["category"]==category]
    for entry in entries:
        render_analysis(entry)

def literature():
    path=ROOT/"data/literature_evidence.csv"
    return pd.read_csv(path,keep_default_na=False) if path.exists() else pd.DataFrame()

def render_household():
    st.subheader("가구 분리배출 시간: 현재 확보 자료")
    st.info("국내 가구별 시간일지 원자료 미확보. 시간 분포·평균 신뢰구간·정책 전후 시간차를 아직 산출하지 않습니다.")
    frame=literature()
    if not frame.empty:
        selected=frame.loc[frame.topic=="household_time"]
        st.dataframe(selected[["title","country","publication_year","reported_value","verification_status","limitation"]].rename(columns={"title":"문헌","country":"국가","publication_year":"출판연도","reported_value":"보고된 값","verification_status":"검증 범위","limitation":"한계"}),hide_index=True)
    template=ROOT/"data/household_diary_template.csv"
    if template.exists():
        st.download_button("시간일지 빈 양식 CSV",template.read_bytes(),template.name,"text/csv")
    st.caption("문헌의 약 30분/주는 노르웨이 자기보고 설문 평균이다. 한국 가구의 실측값이나 단일·다중흐름 전환의 시간차가 아니다.")
    st.markdown("예비조사는 20~40가구·2~4주 탐색 표본을 계획합니다. 세척·분류·보관·배출 이동과 배출량을 따로 기록합니다. 반복 주차는 가구별로 먼저 평균하고, 20가구 이상이면 가구 단위 부트스트랩을 사용할 수 있습니다.")
    st.caption("분석 코드: src/analysis/household_time.py. 대표성·정책 인과효과는 별도로 검증해야 합니다.")

def render_literature():
    st.subheader("선행연구 근거 목록")
    frame=literature()
    if frame.empty:
        st.info("자료 미확보")
        return
    st.caption("초록 확인과 원문 확인을 구분합니다. 국가·시기·표본·측정법이 다른 효과크기를 합산하거나 한국 실측치로 대입하지 않습니다.")
    st.dataframe(frame[["title","publication_year","country","sample_description","method","reported_value","verification_status"]].rename(columns={"title":"문헌","publication_year":"출판연도","country":"국가","sample_description":"표본·대상","method":"방법","reported_value":"보고된 값","verification_status":"확인 범위"}),hide_index=True)
    for row in frame.to_dict("records"):
        with st.expander(row["title"]):
            st.write(row["reported_value"] or "채택할 정량값 미확인")
            st.caption("범위: "+row["scope"]+" · "+row["source_locator"])
            st.caption("한계: "+row["limitation"])
            st.markdown("[확인한 원문 또는 저자·기관 출처]("+row["source_url"]+")")
    st.download_button("문헌 근거 CSV",frame.to_csv(index=False).encode("utf-8-sig"),"literature_evidence.csv","text/csv")

def render_cost_candidates():
    path=ROOT/"data/processed/public_data/contracts/latest_sample.json"
    if path.exists():
        meta=json.loads(path.read_text(encoding="utf-8"))
        candidates=path.parent/meta["run_id"]/"cost_candidates.csv"
        if candidates.exists():
            frame=pd.read_csv(candidates)
            validated=int(frame.validation_status.eq("validated").sum())
            st.subheader("계약 금액과 비용 근거 검토")
            st.metric("검증 완료 처리단가",f"{validated}건")
            st.caption(f"계약 후보 {len(frame)}행은 일반 용역 샘플이다. 계약금액을 톤당 원가로 표시하지 않으며 서비스기간·지역·품목·공정·실제 톤수를 대조해야 한다.")
            with st.expander("비용 근거 후보표"):
                st.dataframe(frame,hide_index=True)
                st.download_button("비용 후보 CSV",candidates.read_bytes(),candidates.name,"text/csv")

def render_quality(manifest):
    render_category(manifest,"자료 출처·품질")
    st.subheader("출처와 파일 무결성")
    st.dataframe(pd.DataFrame(manifest["source_files"]).rename(columns={"path":"분석 입력 파일","sha256":"SHA-256"}),hide_index=True)
    sources=yaml.safe_load((ROOT/"configs/external_sources.yaml").read_text(encoding="utf-8"))["sources"]
    rows=[]
    for name,spec in sources.items():
        path=ROOT/"data/processed/international"/name/"manifest.json"
        actual=json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        rows.append({"출처":name,"기준연도":str(spec["reference_year"]),"형식":spec["format"],"수집 상태":actual.get("status",spec["collection_status"]),"정규화 행수":actual.get("record_count"),"이용조건":spec["license"]})
    st.dataframe(pd.DataFrame(rows),hide_index=True)
    st.subheader("아직 산출하지 않는 분석")
    st.dataframe(pd.DataFrame(manifest["unavailable"]).rename(columns={"topic":"분석 주제","reason":"미산출 이유"}),hide_index=True)
    if st.button("저장 자료로 통계 결과 재생성"):
        from src.analysis.pipeline import run
        with st.spinner("CSV·PNG/SVG·대화형 보고서 생성 중"):
            run()
        st.rerun()
    st.caption("기본 재생성은 네트워크·인증키를 사용하지 않는다. 원자료 수집은 별도 CLI에서 명시적으로 실행한다.")

def render_regional_indicator():
    directory=OUTPUT/"reports/regional_indicator"
    path=directory/"manifest.json"
    if not path.exists():
        st.info("지역 표준화 분석 결과가 아직 없습니다.")
        st.code(r".\.venv\Scripts\python scripts/run_regional_indicator.py --year 2024 --level sido",language="powershell")
        if st.button("보유 2024 자료로 지역 분석 생성"):
            from src.analysis.regional_indicator_report import run
            run();st.rerun()
        return
    meta=json.loads(path.read_text(encoding="utf-8"));summary=meta["summary"]
    st.subheader("2024년 시도별 재질 구성 표준화")
    st.markdown("지역별 4재질 발생량 비중을 전국 실측 발생량 비중으로 고정해 비교합니다. 정책효과나 최종 재생원료 생산률을 나타내지 않습니다.")
    columns=st.columns(4)
    columns[0].metric("시도 관측",f'{summary["sido_rows"]}개')
    columns[1].metric("시군구 자료 연결",f'{summary["sigungu_verified_rows"]}행')
    columns[2].metric("검증된 정책",f'{summary["policy_verified_rows"]}건')
    columns[3].metric("정책·실적 검증 결합",f'{summary["verified_join_rows"]}행')
    for key,title,table_name in (("scores","관측 R과 표준화 S","scores"),("contributions","재질별 R-S 기여도","contributions"),("weight_sensitivity","가중치 민감도","weight_sensitivity")):
        figure=artifact_path(f"figures/regional_indicator/{key}.json")
        st.plotly_chart(pio.read_json(figure),width="stretch",key="regional_indicator_"+key)
        csv_path=artifact_path(f"tables/regional_indicator/{table_name}.csv")
        with st.expander(title+" 표·CSV"):
            st.dataframe(pd.read_csv(csv_path),hide_index=True)
            st.download_button("CSV 다운로드",csv_path.read_bytes(),csv_path.name,"text/csv",key="regional_download_"+table_name)
    stability_path=artifact_path("tables/regional_indicator/weight_stability_by_region.csv")
    if stability_path.exists():
        with st.expander("시도별 점수·순위 민감 경고"):
            st.dataframe(pd.read_csv(stability_path),hide_index=True)
            st.download_button("민감도 경고 CSV",stability_path.read_bytes(),stability_path.name,"text/csv",key="regional_download_stability")
    with st.expander("보조 회귀·진단 결과"):
        for name in ("inference_tests","inference_coefficients","inference_vif","inference_diagnostics","inference_leave_one_out"):
            csv_path=artifact_path(f"tables/regional_indicator/{name}.csv")
            if csv_path.exists():
                st.markdown("**"+name+"**")
                st.dataframe(pd.read_csv(csv_path),hide_index=True)
                st.download_button(name+" CSV",csv_path.read_bytes(),csv_path.name,"text/csv",key="regional_download_"+name)
        st.warning("R은 재질 구성과 재질별 처리비율의 산술 결합입니다. 회귀 p값은 지표 타당성이나 정책효과를 증명하지 않습니다.")
    if summary.get("administrative_boundary_audit_status") == "code_name_roster_stable":
        st.info(f'시군구 {summary["sigungu_verified_rows"]}행의 2024년 월별 코드·명칭 대조가 완료됐습니다. GIS 경계 도형은 평가하지 않았고, 실제 정책 자료가 없어 정책 결합은 {summary["verified_join_rows"]}행입니다.')
    else:
        st.info(f'시군구는 이름·2024년 말 코드가 연결된 {summary["sigungu_verified_rows"]}행입니다. 월별 코드·명칭 감사가 끝나지 않았고 실제 정책 자료가 없어 정책 결합은 {summary["verified_join_rows"]}행입니다.')
    ordinance_versions=summary.get("law_ordinance_version_candidates",0)
    if ordinance_versions:
        st.caption(
            f'법제처 자치법규 연혁 후보 {ordinance_versions}버전(고유 ID {summary.get("law_ordinance_unique_ids",0)}개) 중 '
            f'2024년 통계단위 코드 일치 {summary.get("law_ordinance_matched_statistical_unit_rows",0)}행, '
            f'시도 단위 {summary.get("law_ordinance_sido_only_rows",0)}행, 미매칭 {summary.get("law_ordinance_unmatched_rows",0)}행입니다. '
            f'본문 {summary.get("law_ordinance_detail_json_count",0)}건을 받았으며, 실제 운영정책 증거와 구분합니다.'
        )
        crosswalk_path=ROOT/"data/processed/regional_2024/policy_ordinance_geography_crosswalk.csv"
        if crosswalk_path.exists():
            with st.expander("자치법규 후보와 2024 행정코드 교차표"):
                legal=pd.read_csv(crosswalk_path,dtype=str).fillna("")
                columns=["policy_name","locality","effective_date","geography_match_status","matched_sigungu_code_2024","candidate_status"]
                columns=[column for column in columns if column in legal]
                st.dataframe(legal[columns],hide_index=True)
                st.download_button("자치법규 코드 교차표 CSV",crosswalk_path.read_bytes(),crosswalk_path.name,"text/csv",key="law_ordinance_crosswalk_download")
                st.caption("코드 연결은 후보 탐색용입니다. 법령만으로 2024년 실제 시행·대상범위·성과를 확인하지 않았습니다.")
    sigungu_report=OUTPUT/"reports/regional_indicator_sigungu"
    sigungu_manifest=sigungu_report/"manifest.json"
    if sigungu_manifest.exists():
        county=json.loads(sigungu_manifest.read_text(encoding="utf-8"));county_summary=county["summary"]
        st.divider();st.subheader("시군구 보조 기술 비교")
        st.caption("2024년 공식 원표 지역명 기준 229개 지역의 R/S 분포입니다. 월별 코드·명칭 대조는 완료됐으나 GIS 경계 도형과 정책 적용권역은 미확인 상태이므로 지도·정책 효과 회귀를 제공하지 않습니다.")
        st.metric("시군구 관측",f'{county_summary["sigungu_count"]}개 · {county_summary["material_rows"]} 재질행')
        for key,title,table_name in (("county_scatter","시군구 R과 S","scores"),("county_distribution","분포 비교","scores"),("county_extremes","표준화 상·하위","scores")):
            figure=artifact_path(f"figures/regional_indicator_sigungu/{key}.json")
            st.plotly_chart(pio.read_json(figure),width="stretch",key="regional_sigungu_"+key)
        county_scores=artifact_path("tables/regional_indicator_sigungu/scores.csv")
        with st.expander("시군구 전체 지표 CSV"):
            st.dataframe(pd.read_csv(county_scores),hide_index=True)
            st.download_button("시군구 지표 CSV",county_scores.read_bytes(),county_scores.name,"text/csv",key="regional_sigungu_scores")
        county_html=sigungu_report/"index.html"
        if county_html.exists():st.download_button("시군구 오프라인 보고서 HTML",county_html.read_bytes(),county_html.name,"text/html",key="regional_sigungu_html")
    for name in ("index.html","report.md"):
        file=directory/name
        if file.exists():st.download_button("지역 분석 보고서 "+name,file.read_bytes(),name,"text/html" if name.endswith("html") else "text/markdown",key="regional_report_"+name)

def main():
    st.set_page_config(page_title=TITLE,layout="wide")
    st.title(TITLE)
    st.caption("국내외 실제 통계 · 독립 연구 질문 · 출처와 정의 확인 · Python으로 재현")
    page=st.sidebar.radio("분석 영역",MENU,key="analysis_page")
    manifest=load_manifest()
    if page=="시도 표준화 분석":
        render_regional_indicator();return
    if page=="가정 기반 민감도 분석":
        st.info("이 보조 영역은 외생 가정에 따른 비교다. 관측된 정책 인과효과·확정 절감액과 구분한다.")
        from src.model import load_config,household_saving
        from src.policy_ui import render_policy_experiment
        from src.facility_ui import render_facility_experiment
        mode=st.radio("가정 기반 분석 대상",["KOSIS 지역별 4품목","구로구 시설·예산","가구 시간가치"],horizontal=True,key="policy_mode")
        if mode=="KOSIS 지역별 4품목":
            render_policy_experiment()
        elif mode=="구로구 시설·예산":
            render_facility_experiment(load_config())
        else:
            minutes=st.number_input("가정: 가구당 주당 절약 시간(분)",min_value=0.0,value=5.0)
            value=st.number_input("가정: 시간가치(원/시간)",min_value=0.0,value=9860.0)
            st.metric("가구당 연간 가정 가치",f"{household_saving(minutes,value):,.0f}원")
            st.caption("관측 시간차가 없다. 9,860원은 2024년 최저임금의 참고 가정이며 실제 기회비용과 구분한다.")
        return
    if page=="가구 시간 분석":
        render_household();return
    if page=="선행연구":
        render_literature();return
    if manifest is None:
        st.info("통계 분석 결과를 먼저 생성하세요.")
        st.code(r".\.venv\Scripts\python run_statistical_analysis.py",language="powershell")
        if st.button("보유 자료로 첫 분석 생성"):
            from src.analysis.pipeline import run
            run();st.rerun()
        return
    st.sidebar.caption(f'생성 {manifest["generated_at"]} · 독립 분석 {manifest["analysis_count"]}개')
    for name,label,mime in (("index.html","전체 대화형 보고서","text/html"),("report.md","분석 보고서 Markdown","text/markdown")):
        path=REPORT/name
        st.sidebar.download_button(label,path.read_bytes(),name,mime,key="report_"+name)
    if page=="자료 출처·품질":
        render_quality(manifest);return
    if page=="국내 통계 현황":
        columns=st.columns(3)
        public=pd.read_csv(ROOT/"data/processed/kosis_public_waste.csv").sort_values("reference_year")
        latest=public.iloc[-1]
        columns[0].metric(f"{int(latest.reference_year)}년 생활폐기물",f"{latest.value/1e4:,.1f}만 t/년")
        columns[1].metric("KOSIS 상세 비교", "17개 시도 · 4품목")
        columns[2].metric("독립 통계 분석",f'{manifest["analysis_count"]}개')
        st.caption("전국 생활폐기물 전체와 대응 4품목 합계의 범위를 구분한다.")
    render_category(manifest,page)
    if page=="해외 통계 비교":
        st.subheader("한국 통계와 직접 비교할 수 있는가")
        st.dataframe(pd.read_csv(OUTPUT/"tables/statistical_analysis/comparability.csv"),hide_index=True)
        st.caption("현재 비교 정의가 맞지 않아 한국과의 통합 순위·회귀 그래프는 만들지 않는다. 해외 출처 안의 기술통계를 각각 보여준다.")
        epa=ROOT/"data/processed/international/epa/records.csv"
        if epa.exists():
            with st.expander("미국 EPA 2018 추정 요약 · 참고"):
                st.dataframe(pd.read_csv(epa)[["year","metric","raw_value","raw_unit","value","unit","measurement_type"]],hide_index=True)
                st.caption("2018년 추정·반올림 수치. 미국 short ton을 metric tonne으로 변환했으며 최근 한국 값과 직접 비교하지 않는다.")
    if page=="시설 및 비용 분석":
        render_cost_candidates()
