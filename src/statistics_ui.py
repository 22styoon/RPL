"""통계 분석 보고서의 Streamlit 프런트엔드. 기본 화면에서 정책 가정을 실행하지 않는다."""
import json
from pathlib import Path
import pandas as pd
import plotly.io as pio
import streamlit as st
import yaml
from src.model import ROOT
from src.analysis.pipeline import TITLE
from src.regional_data.audit_evidence import assess_boundary_audit
from src.regional_data.audit_reporting import current_audit_fields
from src.regional_data.followup_reporting import (
    POLICY_SCOPE, TITLE as OPERATING_POLICY_TITLE, gis_note, program_display, program_evidence,
)
from src.regional_data.ordinance_evidence import current_ordinance_fields

MENU=["국내 통계 현황","재활용 지표 연구","지역·재질별 비교","시도 표준화 분석","해외 통계 비교","시설 및 비용 분석","가구 시간 분석","선행연구","자료 출처·품질","가정 기반 민감도 분석"]
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

def live_regional_audit_view(cached_summary, *, assessment=None):
    """Current geography evidence overrides historical report audit claims.

    Policy-document evidence stays separate from the current outcome join.
    This helper never modifies or silently regenerates the saved report.
    """
    current=assess_boundary_audit(ROOT) if assessment is None else assessment
    summary=dict(cached_summary)
    summary.update(current_audit_fields(ROOT,cached_summary,assessment=current))
    summary["cached_boundary_audit_status"]=cached_summary.get("administrative_boundary_audit_status","not_audited")
    summary["cached_report_stale"]=(summary["cached_boundary_audit_status"]=="code_name_roster_stable"
        and not summary["policy_join_boundary_input_verified"])
    return summary


def regional_boundary_caption(summary, *, county_report=False):
    if summary.get("boundary_input_binding_verified") is True:
        note="2024년 월별 코드·명칭 감사의 현재 입력과 증빙이 일치합니다."
    else:
        note="월별 코드·명칭 감사의 현재 입력 유효성을 확인하지 못했습니다. 저장된 완료 표시는 현재 검증으로 사용하지 않습니다."
    if county_report:
        prefix=f'공식 원표 기준 {summary.get("sigungu_count",0)}개 시군구의 R/S 기술 비교입니다. '
    else:
        prefix=f'시군구 자료 {summary.get("sigungu_verified_rows",0)}행을 기준으로 확인했습니다. '
    return prefix+note+" GIS 경계 도형과 정책 적용권역은 별도 검증 대상이며 지도·정책효과 추론의 근거로 사용하지 않습니다."


def live_ordinance_view(cached_summary):
    """Fresh legal-source linkage controls current counts and downloads."""
    summary=dict(cached_summary)
    summary.update(current_ordinance_fields(ROOT,cached_summary=cached_summary))
    law_counts=("law_ordinance_version_candidates","law_ordinance_detail_json_count",
                "law_article_evidence_rows","law_verified_document_version_rows")
    summary["cached_law_report_stale"]=(
        any(cached_summary.get(key,0)!=summary.get(key,0) for key in law_counts)
        or (bool(cached_summary.get("law_ordinance_version_candidates",0))
            and not summary.get("law_linkage_verified",False)))
    summary["cached_report_stale"]=bool(summary.get("cached_report_stale")) or summary["cached_law_report_stale"]
    return summary


def filter_ordinance_articles(frame, query):
    """Literal search of legal titles, localities and cited article text."""
    query=str(query or "").strip().casefold()
    if not query or frame.empty:return frame.copy()
    fields=[name for name in ("policy_name","locality","article_number","article_title",
                              "article_text","materials_mentioned","topics_mentioned") if name in frame]
    if not fields:return frame.iloc[0:0].copy()
    text=frame[fields].fillna("").astype(str).agg(" ".join,axis=1).str.casefold()
    return frame.loc[text.str.contains(query,regex=False)].copy()


def render_ordinance_evidence(summary):
    st.subheader("법령정보와 조문 근거")
    st.caption("2024년 시행일을 가진 연혁 버전의 제목 검색 결과입니다(nw=2, efYd=2024년). 2024년에 유효했던 모든 조례나 연중 적용기간을 확인한 목록은 아닙니다.")
    if not summary.get("law_linkage_verified",False):
        if summary.get("cached_law_report_stale"):
            st.warning("저장된 법령 연결의 입력·원문 근거를 현재 자료와 대조해 확인하지 못했습니다. 과거 건수를 현재 검증 결과로 표시하지 않으며 교차표·조문 다운로드를 보류합니다.")
        else:
            st.info("현재 입력과 원문에 연결된 법령 검토표가 아직 없습니다.")
        if summary.get("law_linkage_reasons"):
            st.caption("법령 연결 확인: "+"; ".join(str(reason) for reason in summary["law_linkage_reasons"]))
        st.code(r".\.venv\Scripts\python scripts/link_law_ordinances.py",language="powershell")
        return
    st.caption(
        f'연혁 후보 {summary.get("law_ordinance_version_candidates",0)}버전 · '
        f'통계단위 코드 일치 {summary.get("law_ordinance_matched_statistical_unit_rows",0)}행 · '
        f'본문 수집 {summary.get("law_ordinance_detail_json_count",0)}건 · '
        f'버전 메타데이터 대조 {summary.get("law_verified_document_version_rows",0)}건 · '
        f'조문 근거 {summary.get("law_article_evidence_rows",0)}행입니다.'
    )
    st.caption("조문에 재질·수거방식이 언급된 사실은 검토 단서입니다. 실제 사업 시행·대상범위·처리실적·정책효과와 구분합니다.")
    crosswalk_path=ROOT/"data/processed/regional_2024/policy_ordinance_geography_crosswalk.csv"
    if crosswalk_path.exists():
        with st.expander("법령 후보와 2024 행정코드 교차표"):
            legal=pd.read_csv(crosswalk_path,dtype=str).fillna("")
            columns=[name for name in ("policy_name","locality","effective_date","ordinance_serial",
                     "geography_match_status","matched_sigungu_code_2024","detail_status",
                     "legal_version_status","source_url") if name in legal]
            st.dataframe(legal[columns],hide_index=True,
                         column_config={"source_url":st.column_config.LinkColumn("공식 원문",display_text="원문")})
            st.download_button("자치법규 코드 교차표 CSV",crosswalk_path.read_bytes(),crosswalk_path.name,"text/csv",key="law_ordinance_crosswalk_download")
    article_path=ROOT/"data/processed/regional_2024/policy_ordinance_article_evidence.csv"
    if article_path.exists():
        articles=pd.read_csv(article_path,dtype=str).fillna("")
        with st.expander("법령·기관·조문 검색과 원문 근거",expanded=True):
            query=st.text_input("법령·기관·조문 검색",key="law_ordinance_article_query")
            selected=filter_ordinance_articles(articles,query)
            st.caption(f'검색 결과 {len(selected)}행 / 조문 근거 {len(articles)}행')
            labels={"policy_name":"법령명","locality":"기관","effective_date":"시행일",
                    "ordinance_serial":"버전 일련번호","article_number":"조문번호","article_title":"조제목",
                    "text_field":"본문 구분","article_text":"조문 내용","materials_mentioned":"재질 언급",
                    "topics_mentioned":"주제 언급","source_url":"공식 원문","source_locator":"원문 위치",
                    "json_pointer":"조문 위치","raw_detail_sha256":"원문 SHA-256",
                    "legal_version_status":"버전 대조 상태","geography_match_status":"지역 대조 상태"}
            columns=[name for name in labels if name in selected]
            st.dataframe(selected[columns].rename(columns=labels),hide_index=True,
                         column_config={"공식 원문":st.column_config.LinkColumn("공식 원문",display_text="원문")})
            st.download_button("검색한 조문 근거 CSV",selected.to_csv(index=False).encode("utf-8-sig"),
                               "ordinance_article_evidence_filtered.csv","text/csv",key="law_ordinance_articles_download")
            st.caption("원문 위치·조문 위치와 원문 해시는 수집한 버전으로 돌아가 대조하기 위한 정보입니다. 법령의 유효 종료일·개정 전후 적용관계는 별도 확인합니다.")


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
    meta=json.loads(path.read_text(encoding="utf-8"))
    current_audit=assess_boundary_audit(ROOT)
    summary=live_ordinance_view(live_regional_audit_view(meta["summary"],assessment=current_audit))
    st.subheader("2024년 시도별 재질 구성 표준화")
    st.markdown("지역별 4재질 발생량 비중을 전국 실측 발생량 비중으로 고정해 비교합니다. 정책효과나 최종 재생원료 생산률을 나타내지 않습니다.")
    columns=st.columns(4)
    columns[0].metric("시도 관측",f'{summary["sido_rows"]}개')
    columns[1].metric("시군구 자료 연결",f'{summary["sigungu_verified_rows"]}행')
    columns[2].metric("생활폐기물 결합용 정책",f'{summary["policy_verified_rows"]}건')
    columns[3].metric("연간 생활폐기물 결합",f'{summary["verified_join_rows"]}행' if summary["policy_join_boundary_input_verified"] else "재검증 전")
    if summary["cached_report_stale"]:
        st.warning("저장된 보고서의 감사·법령 연결·정책 결합 정보가 현재 입력과 일치하는지 다시 확인해야 합니다. 아래 그림과 다운로드는 과거 생성 결과입니다.")
    if not summary["policy_join_boundary_input_verified"]:
        prefix="지리 감사는 현재 유효하지만 저장된 정책·성과 결합의 입력 연결을 다시 확인해야 합니다. " if summary["boundary_input_binding_verified"] else "현재 정책·성과 결합은 지리 근거 재검증 전 상태입니다. "
        st.info(prefix+f'저장 보고서의 {summary["cached_verified_join_rows"]}행을 현재 검증된 결합으로 표시하지 않습니다. 정책 원문 자체의 검증 건수는 별도로 유지합니다.')
    if summary["boundary_audit_reasons"]:
        st.caption("감사 확인 상태: "+summary["administrative_boundary_audit_status"]+" · "+"; ".join(str(reason) for reason in summary["boundary_audit_reasons"]))
    with st.expander("현재 입력 감사 확인·재생성"):
        st.code(r".\.venv\Scripts\python scripts/audit_regional_boundaries.py --check-only",language="powershell")
        st.caption("이 확인 명령은 저장된 입력과 증빙만 검사합니다. 입력이 바뀌었으면 월별 감사를 다시 실행한 뒤 정책 결합과 보고서를 재생성하세요.")
        st.code(".\\.venv\\Scripts\\python scripts/audit_regional_boundaries.py\n.\\.venv\\Scripts\\python scripts/join_regional_policy.py --year 2024\n.\\.venv\\Scripts\\python run_statistical_analysis.py",language="powershell")
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
    st.info(regional_boundary_caption(summary))
    if "gis_boundary_status" in summary:
        gis = {
            "status": summary["gis_boundary_status"],
            "verified": summary["gis_boundary_verified"],
            "summary": summary["gis_boundary_summary"],
            "reasons": summary["gis_boundary_reasons"],
        }
        st.caption("보고서 생성 시 GIS 감사 · " + gis_note(gis))
    evidence = program_evidence(ROOT)
    if evidence is not None:
        st.subheader(OPERATING_POLICY_TITLE)
        st.caption(POLICY_SCOPE)
        st.dataframe(program_display(evidence), hide_index=True)
        st.download_button(
            "사업 자체 성과와 원문 출처 CSV",
            evidence.performance.to_csv(index=False).encode("utf-8-sig"),
            "operating_policy_performance.csv",
            "text/csv",
        )
    render_ordinance_evidence(summary)
    sigungu_report=OUTPUT/"reports/regional_indicator_sigungu"
    sigungu_manifest=sigungu_report/"manifest.json"
    if sigungu_manifest.exists():
        county=json.loads(sigungu_manifest.read_text(encoding="utf-8"))
        county_summary=live_ordinance_view(live_regional_audit_view(county["summary"],assessment=current_audit))
        st.divider();st.subheader("시군구 보조 기술 비교")
        st.caption(regional_boundary_caption(county_summary,county_report=True))
        if county_summary["cached_report_stale"]:
            st.warning("시군구 보고서도 과거 입력·증빙 상태를 포함한 저장 결과입니다. 현재 자료 확인과 보고서 재생성이 필요합니다.")
        st.metric("시군구 관측",f'{county_summary["sigungu_count"]}개 · {county_summary["material_rows"]} 재질행')
        for key,title,table_name in (("county_scatter","시군구 R과 S","scores"),("county_distribution","분포 비교","scores"),("county_extremes","표준화 상·하위","scores")):
            figure=artifact_path(f"figures/regional_indicator_sigungu/{key}.json")
            st.plotly_chart(pio.read_json(figure),width="stretch",key="regional_sigungu_"+key)
        county_scores=artifact_path("tables/regional_indicator_sigungu/scores.csv")
        with st.expander("시군구 전체 지표 CSV"):
            st.dataframe(pd.read_csv(county_scores),hide_index=True)
            st.download_button("시군구 지표 CSV",county_scores.read_bytes(),county_scores.name,"text/csv",key="regional_sigungu_scores")
        county_html=sigungu_report/"index.html"
        if county_html.exists():st.download_button("시군구 오프라인 보고서 HTML"+(" (과거 저장 결과)" if county_summary["cached_report_stale"] else ""),county_html.read_bytes(),county_html.name,"text/html",key="regional_sigungu_html")
    for name in ("index.html","report.md"):
        file=directory/name
        if file.exists():st.download_button("지역 분석 보고서 "+name+(" (과거 저장 결과)" if summary["cached_report_stale"] else ""),file.read_bytes(),name,"text/html" if name.endswith("html") else "text/markdown",key="regional_report_"+name)

def render_recycling_indicator():
    st.subheader("재활용률의 국제 비교: 지표 설계와 근거")
    directory=OUTPUT/"reports/recycling_indicator"
    manifest_path=directory/"manifest.json"
    if not manifest_path.exists():
        st.info("선행연구·실측 통계·설명 사례로 지표 연구 보고서를 생성합니다.")
        st.code(r".\.venv\Scripts\python scripts/run_recycling_indicator.py",language="powershell")
        if st.button("보유 자료로 지표 연구 보고서 생성",key="build_recycling_indicator"):
            from src.analysis.recycling_indicator_report import run
            run();st.rerun()
        return
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    summary=manifest["summary"]
    columns=st.columns(3)
    columns[0].metric("학술·공식·방법 근거",f'{summary["source_items"]}항목')
    columns[1].metric("에너지회수 포함/제외 차이",f'{summary["kosis_energy_gap_pp"]:.2f}%p')
    columns[2].metric("시도 구성 표준화 차이 최대",f'{summary["maximum_composition_gap_pp"]:.2f}%p')
    st.caption("수치 카드: KOSIS 2024 대응 4재질 처리량 기준. 최종 재생원료 산출률·정책효과와 구분합니다.")
    st.markdown("**H**는 같은 범위·원산지·발생연도의 폐기물에서 얻은 최종 재생물질의 비율입니다. **S**는 재질 구성을 공통 가중치로 고정한 비교값입니다.")
    st.latex(r"H=100\frac{\sum_m F_m}{\sum_m G_m},\qquad S=100\sum_m w_m^*\frac{F_m}{G_m}")
    st.info("현재 국내 자료는 처리량입니다. 새 최종 H/S 국가값과 특정 정책의 인과효과는 아직 식별되지 않았습니다. 아래 실측 그림과 가상 설명을 구분해 확인하세요.")
    st.caption("0.2·0.3·0.5는 한국 EPR 의무율 산정용 과거 실적 가중치입니다. 통상 의무율 산정연도 t에서 t−4·t−3·t−2에 적용하며 국가 연간 실적률의 보편 산식과 다릅니다.")
    from src.analysis.recycling_indicator_report import CHARTS
    actual,robust,examples=st.tabs(["실제 통계·문헌·기관 모형","가중치 범위 전체의 비교","지표 작동 설명·인과 경로"])
    for container,names in [(actual,["swiss_stages","nea_scope","kosis_energy","regional_scores","jrc_plastics"]),
                            (robust,["weight_pair_counts","weight_pair_matrix"]),
                            (examples,["composition_example","time_methods","partial_bounds","mass_flow"])]:
        with container:
            for name in names:
                _,title,label,note,_=CHARTS[name]
                st.markdown("**"+title+"**");st.caption(label)
                figure=artifact_path(f"figures/recycling_indicator/{name}.json")
                if not figure.exists():
                    st.info("이 그림은 2026-11-19 후속 보고서를 재생성하면 표시됩니다.")
                    continue
                st.plotly_chart(pio.read_json(figure),width="stretch",key="indicator_"+name)
                st.write(note)
                with st.expander("수치 CSV·발표용 PNG/SVG"):
                    for extension,folder,mime in [("csv","tables","text/csv"),("png","figures","image/png"),("svg","figures","image/svg+xml")]:
                        path=artifact_path(f"{folder}/recycling_indicator/{name}.{extension}")
                        st.download_button(extension.upper(),path.read_bytes(),path.name,mime,key="indicator_"+name+extension)
        if container is examples:
            with container:
                st.image(str(artifact_path("figures/recycling_indicator/causal_dag.png")),caption="인과 가설. 지역·시장 여건의 교란은 구성 표준화만으로 제거되지 않습니다.")
    with robust:
        st.caption("모든 비교에서 두 지역에 같은 가중치를 적용합니다. 허용 집합은 민감도 시나리오이며 확률분포나 합의된 최적 가중치가 아닙니다. 비음수 전체 검토에는 가중치 0의 극단도 포함합니다.")
        counts_path=artifact_path("tables/recycling_indicator/weight_pair_counts.csv")
        if counts_path.exists():
            counts=pd.read_csv(counts_path)
            st.dataframe(counts[["가중치 범위","pair_count","nonreversal_pairs","indeterminate_pairs"]].rename(columns={"pair_count":"전체 지역쌍","nonreversal_pairs":"방향 유지","indeterminate_pairs":"역전 가능"}),hide_index=True)
            selected=st.selectbox("비교할 가중치 허용 범위",counts["가중치 범위"].tolist(),key="indicator_weight_domain")
            domain=counts.loc[counts["가중치 범위"].eq(selected),"domain"].iloc[0]
            pairs=pd.read_csv(artifact_path("tables/recycling_indicator/weight_comparisons.csv"))
            pairs=pairs.loc[pairs.domain.eq(domain)]
            display_pairs=pairs[["entity_a","entity_b","gap_lower_pp","gap_upper_pp","comparison"]].copy()
            display_pairs["comparison"]=display_pairs.comparison.map({"a_strict":"A가 항상 높음","b_strict":"B가 항상 높음","a_no_reversal":"A가 낮아지지 않음·동점 가능","b_no_reversal":"B가 낮아지지 않음·동점 가능","tie":"항상 동점","indeterminate":"우열이 달라질 수 있음"})
            st.dataframe(display_pairs.rename(columns={"entity_a":"지역 A","entity_b":"지역 B","gap_lower_pp":"A−B 최소차(%p)","gap_upper_pp":"A−B 최대차(%p)","comparison":"비교 분류"}),hide_index=True)
            with st.expander("비교를 재현하는 가중치·순위 외곽 범위"):
                pair_labels=[f'{row.entity_a} / {row.entity_b}' for row in pairs.itertuples()]
                chosen=st.selectbox("극값 가중치를 확인할 지역쌍",pair_labels,key="indicator_weight_pair")
                pair=pairs.iloc[pair_labels.index(chosen)]
                witness=pd.read_csv(artifact_path("tables/recycling_indicator/weight_witnesses.csv"))
                witness=witness.loc[witness.domain.eq(domain)&witness.entity_a.eq(pair.entity_a)&witness.entity_b.eq(pair.entity_b)]
                witness=witness.copy();witness["endpoint"]=witness.endpoint.map({"lower":"A−B 최소차","upper":"A−B 최대차"})
                st.dataframe(witness[["endpoint","material","weight","rate_a","rate_b","gap_contribution_pp"]].rename(columns={"endpoint":"극값 방향","material":"재질","weight":"공통 가중치","rate_a":"A 처리비율(0–1)","rate_b":"B 처리비율(0–1)","gap_contribution_pp":"차이 기여도(%p)"}),hide_index=True)
                ranks=pd.read_csv(artifact_path("tables/recycling_indicator/weight_rank_outer.csv"))
                st.dataframe(ranks.loc[ranks.domain.eq(domain),["entity","rank_lower_outer","rank_upper_outer","score_lower_pct","score_upper_pct"]].rename(columns={"entity":"시도","rank_lower_outer":"순위 외곽 하한","rank_upper_outer":"순위 외곽 상한","score_lower_pct":"점수 하한(%)","score_upper_pct":"점수 상한(%)"}),hide_index=True)
                st.caption("순위는 쌍별 보장에서 얻은 보수적 외곽 범위입니다. 양 끝 순위가 실제 하나의 가중치에서 달성된다는 보장은 없으며 신뢰구간이 아닙니다.")
                for name in ("weight_comparisons","weight_witnesses","weight_rank_outer","weight_reference_vertices","weight_domain_bounds"):
                    path=artifact_path(f"tables/recycling_indicator/{name}.csv")
                    st.download_button(name+" CSV",path.read_bytes(),path.name,"text/csv",key="indicator_download_"+name)
    with st.expander("전체 연구·근거·독립 검증 계획"):
        st.markdown("측정 경계 감사 → 독립 최종 산출과의 일치 → 국가·가중치 민감도 → 정책 패널 인과분석 → 환경·비용 검증 순서로 진행합니다. 산식의 단조성·구성 불변성은 프로그램으로 검증하며 정책 인과효과는 추가 식별이 필요합니다.")
        sources=pd.read_csv(artifact_path("tables/recycling_indicator/sources.csv"))
        st.dataframe(sources[["source_id","title","year","verified","contribution","limitation"]],hide_index=True)
    for filename,label,mime in [("index.html","대화형 연구 보고서 HTML","text/html"),("study.md","초기 연구 논증 Markdown","text/markdown"),("weight_robustness.md","가중치 후속 논증 Markdown","text/markdown"),("followup_evidence.md","추가 근거 확인 Markdown","text/markdown"),("sources.json","출처·확인 범위 JSON","application/json")]:
        path=directory/filename
        if path.exists():
            st.download_button(label,path.read_bytes(),filename,mime,key="indicator_report_"+filename)


def main():
    st.set_page_config(page_title=TITLE,layout="wide")
    st.title(TITLE)
    st.caption("국내외 실제 통계 · 독립 연구 질문 · 출처와 정의 확인 · Python으로 재현")
    page=st.sidebar.radio("분석 영역",MENU,key="analysis_page")
    manifest=load_manifest()
    if page=="재활용 지표 연구":
        render_recycling_indicator();return
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
