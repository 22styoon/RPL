"""2024 시군구 재질구성 표준화의 기술통계 보고서. 정책 추론은 포함하지 않는다."""
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,html,json
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
from src.model import ROOT
from .standardization import compute_standardization
from src.regional_data.audit_reporting import current_audit_fields,audit_note
from src.regional_data.ordinance_evidence import current_ordinance_fields

TITLE="2024년 시군구별 재활용 처리비율: 기술 비교"

def _md_table(frame):
    def cell(value):
        if pd.isna(value):return ""
        if isinstance(value,(float,np.floating)):return f"{value:.3f}"
        return str(value).replace("|","/").replace("\n"," ")
    columns=list(frame.columns)
    return "| "+" | ".join(columns)+" |\n| "+" | ".join("---" for _ in columns)+" |\n"+"\n".join("| "+" | ".join(cell(v) for v in row)+" |" for row in frame.itertuples(index=False,name=None))


def _plots(scores):
    highlight=scores.nlargest(10,"구성 차이 R-S(%p)",keep="all").copy()
    highlight=pd.concat([highlight,scores.nsmallest(10,"구성 차이 R-S(%p)",keep="all")]).drop_duplicates("시군구")
    fig1=go.Figure()
    lo=float(min(scores["관측 처리비율 R_r(%)"].min(),scores["전국 고정가중 표준화 S_r(%)"].min()))
    hi=float(max(scores["관측 처리비율 R_r(%)"].max(),scores["전국 고정가중 표준화 S_r(%)"].max()))
    fig1.add_trace(go.Scatter(x=scores["관측 처리비율 R_r(%)"],y=scores["전국 고정가중 표준화 S_r(%)"],
        mode="markers",text=scores["시군구"],marker={"size":7,"color":"#127c80","opacity":.68},
        hovertemplate="%{text}<br>관측 R=%{x:.2f}%<br>표준화 S=%{y:.2f}%<extra></extra>",name="시군구"))
    fig1.add_trace(go.Scatter(x=highlight["관측 처리비율 R_r(%)"],y=highlight["전국 고정가중 표준화 S_r(%)"],
        mode="text",text=highlight["시군구"],textposition="top center",textfont={"size":9,"color":"#263b50"},name="|R-S| 상·하위 사례"))
    fig1.add_trace(go.Scatter(x=[lo,hi],y=[lo,hi],mode="lines",line={"dash":"dash","color":"#777"},name="R=S"))
    fig1.update_layout(title="시군구 관측 R과 전국 고정가중 표준화 S",xaxis_title="관측 처리비율 R (%)",
        yaxis_title="표준화 처리비율 S (%)",template="plotly_white",font={"family":"Malgun Gothic, sans-serif"},height=650)

    dist=pd.concat([scores[["시군구","관측 처리비율 R_r(%)"]].rename(columns={"관측 처리비율 R_r(%)":"처리비율(%)"}).assign(지표="관측 R"),
        scores[["시군구","전국 고정가중 표준화 S_r(%)"]].rename(columns={"전국 고정가중 표준화 S_r(%)":"처리비율(%)"}).assign(지표="표준화 S")])
    fig2=px.histogram(dist,x="처리비율(%)",color="지표",barmode="overlay",opacity=.65,nbins=24,
        title="시군구별 관측·표준화 처리비율 분포")
    fig2.update_layout(template="plotly_white",font={"family":"Malgun Gothic, sans-serif"},height=460,yaxis_title="시군구 수")

    ordered=scores.sort_values("전국 고정가중 표준화 S_r(%)")
    extremes=pd.concat([ordered.head(15),ordered.tail(15)]).drop_duplicates("시군구")
    long=extremes.melt(id_vars="시군구",value_vars=["관측 처리비율 R_r(%)","전국 고정가중 표준화 S_r(%)"],var_name="지표",value_name="처리비율(%)")
    fig3=px.bar(long,x="처리비율(%)",y="시군구",color="지표",barmode="group",orientation="h",
        title="표준화 점수 상·하위 시군구 (각 15개)")
    fig3.update_layout(template="plotly_white",font={"family":"Malgun Gothic, sans-serif"},height=max(680,len(extremes)*27+120),legend_title_text="")
    return {"county_scatter":fig1,"county_distribution":fig2,"county_extremes":fig3},highlight


def _static(scores,highlight,figure_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    families={f.name for f in font_manager.fontManager.ttflist}
    font=next((name for name in ("Malgun Gothic","Noto Sans CJK KR","NanumGothic","AppleGothic") if name in families),"DejaVu Sans")
    plt.rcParams.update({"font.family":font,"axes.unicode_minus":False,"svg.fonttype":"path"})
    lo=float(min(scores["관측 처리비율 R_r(%)"].min(),scores["전국 고정가중 표준화 S_r(%)"].min()))
    hi=float(max(scores["관측 처리비율 R_r(%)"].max(),scores["전국 고정가중 표준화 S_r(%)"].max()))
    fig,ax=plt.subplots(figsize=(9,8));ax.scatter(scores["관측 처리비율 R_r(%)"],scores["전국 고정가중 표준화 S_r(%)"],s=18,alpha=.55,color="#127c80");ax.plot([lo,hi],[lo,hi],"--",color="#777",linewidth=1)
    for _,row in highlight.iterrows():
        ax.annotate(row["시군구"],(row["관측 처리비율 R_r(%)"],row["전국 고정가중 표준화 S_r(%)"]),fontsize=7,xytext=(3,3),textcoords="offset points")
    ax.set_xlabel("관측 처리비율 R (%)");ax.set_ylabel("표준화 처리비율 S (%)");ax.set_title("시군구 관측 R과 전국 고정가중 표준화 S",loc="left",fontweight="bold");ax.grid(alpha=.18);ax.set_axisbelow(True)
    for ext in ("png","svg"):fig.savefig(figure_dir/f"county_scatter.{ext}",dpi=160,bbox_inches="tight")
    plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,6));ax.hist(scores["관측 처리비율 R_r(%)"],bins=24,alpha=.55,label="관측 R",color="#315b96");ax.hist(scores["전국 고정가중 표준화 S_r(%)"],bins=24,alpha=.55,label="표준화 S",color="#d39745");ax.set_xlabel("처리비율 (%)");ax.set_ylabel("시군구 수");ax.set_title("시군구별 관측·표준화 처리비율 분포",loc="left",fontweight="bold");ax.legend();ax.grid(axis="y",alpha=.18)
    for ext in ("png","svg"):fig.savefig(figure_dir/f"county_distribution.{ext}",dpi=160,bbox_inches="tight")
    plt.close(fig)


def run(root=ROOT,output_root=None):
    root=Path(root).resolve();output=Path(output_root or root/"outputs").resolve()
    processed=root/"data/processed/regional_2024/sigungu_2024_materials_verified.csv"
    national_path=root/"data/processed/kosis_materials_2024.csv"
    if not processed.exists():raise FileNotFoundError("시군구 분석 입력 미확보: scripts/prepare_regional_recycling.py 실행 필요")
    counties=pd.read_csv(processed,dtype={"sigungu_code":str})
    if "geography" not in counties:counties["geography"]=counties["sido_name"].astype(str)+" "+counties["sigungu_name"].astype(str)
    areas=sorted(counties.geography.dropna().unique().tolist())
    national=pd.read_csv(national_path)
    national=national.loc[national.geography.eq("전국")].copy()
    combined=pd.concat([national,counties],ignore_index=True,sort=False)
    scores,contributions,sensitivity,sens_summary,weights=compute_standardization(combined,expected_regions=areas,region_label="시군구")
    by_region=sensitivity.pivot(index="시군구",columns="가중치 기준",values="표준화 처리비율(%)")
    ranks=sensitivity.pivot(index="시군구",columns="가중치 기준",values="순위(높은 값=1)")
    stability=pd.DataFrame({"시군구":by_region.index,"가중치별 점수 범위(%p)":by_region.max(axis=1)-by_region.min(axis=1),"가중치별 순위 범위":ranks.max(axis=1)-ranks.min(axis=1)}).reset_index(drop=True)
    report=output/"reports/regional_indicator_sigungu";tables=output/"tables/regional_indicator_sigungu";figures=output/"figures/regional_indicator_sigungu"
    for directory in (report,tables,figures):directory.mkdir(parents=True,exist_ok=True)
    descriptive_summary=pd.DataFrame([
        {"지표":"관측 처리비율 R","단위":"%","시군구 수":len(scores),"최소":scores["관측 처리비율 R_r(%)"].min(),"중앙값":scores["관측 처리비율 R_r(%)"].median(),"최대":scores["관측 처리비율 R_r(%)"].max()},
        {"지표":"표준화 처리비율 S","단위":"%","시군구 수":len(scores),"최소":scores["전국 고정가중 표준화 S_r(%)"].min(),"중앙값":scores["전국 고정가중 표준화 S_r(%)"].median(),"최대":scores["전국 고정가중 표준화 S_r(%)"].max()},
        {"지표":"구성 차이 R-S","단위":"%p","시군구 수":len(scores),"최소":scores["구성 차이 R-S(%p)"].min(),"중앙값":scores["구성 차이 R-S(%p)"].median(),"최대":scores["구성 차이 R-S(%p)"].max()},
    ])
    files={"scores":scores,"descriptive_summary":descriptive_summary,"contributions":contributions,"weight_sensitivity":sensitivity,"weight_sensitivity_summary":sens_summary,"weight_stability_by_region":stability,"national_weights":weights}
    for name,frame in files.items():frame.to_csv(tables/f"{name}.csv",index=False,encoding="utf-8-sig")
    figs,highlight=_plots(scores)
    for name,fig in figs.items():
        fig.write_json(figures/f"{name}.json");fig.write_html(figures/f"{name}.html",include_plotlyjs=True)
    _static(scores,highlight,figures)
    generated=datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")
    region_meta=root/"data/processed/regional_2024/manifest.json"
    metadata=json.loads(region_meta.read_text(encoding="utf-8")) if region_meta.exists() else {}
    law_summary_path=root/"data/processed/regional_2024/policy_ordinance_candidate_summary.json"
    source_files=[processed,national_path,region_meta,root/"data/processed/regional_2024/boundary_audit_manifest.json",law_summary_path,root/"data/processed/regional_2024/policy_ordinance_candidates.csv",root/"data/processed/regional_2024/policy_ordinance_geography_crosswalk.csv",root/"data/raw/regional_2024/law_ordinances/latest.json",root/"configs/regional_indicator.yaml",root/"src/analysis/standardization.py",root/"src/analysis/sigungu_indicator_report.py",root/"src/regional_data/policy_geography.py",root/"scripts/link_law_ordinances.py",root/"src/regional_data/law_client.py",root/"scripts/collect_law_ordinances.py"]
    source_hashes={str(path.relative_to(root)).replace("\\","/"):{"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"bytes":path.stat().st_size} for path in source_files if path.exists()}
    for relative in ("src/regional_data/audit_evidence.py","src/regional_data/audit_reporting.py",
                     "src/regional_data/ordinance_evidence.py",
                     "data/processed/regional_2024/policy_ordinance_article_evidence.csv",
                     "data/processed/regional_2024/admin_codes_monthly_2024.csv",
                     "data/processed/regional_2024/admin_codes_202412.csv",
                     "data/raw/regional_2024/kr_admin_codes_2024/checkpoint.json"):
        path=root/relative
        if path.exists():source_hashes[relative]={"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"bytes":path.stat().st_size}
    maxrow=scores.loc[scores["구성 차이 R-S(%p)"].abs().idxmax()]
    summary={"reference_year":2024,"sigungu_count":len(scores),"material_rows":len(counties),"policy_verified_rows":metadata.get("policy_verified_rows",0),"verified_join_rows":metadata.get("verified_join_rows",0),"code_snapshot":metadata.get("metadata_code_snapshot","unknown"),"administrative_boundary_audit_status":metadata.get("administrative_boundary_audit_status","not_audited"),"administrative_boundary_audit_geometry_assessed":metadata.get("administrative_boundary_audit_geometry_assessed",False),"max_abs_shift_area":maxrow["시군구"],"max_abs_shift_pp":float(maxrow["구성 차이 R-S(%p)"].__abs__()),"source_files":source_hashes}
    summary.update(current_audit_fields(root,metadata,waste_frame=counties))
    summary.update(current_ordinance_fields(root))
    if summary["law_linkage_verified"]:
        law_articles=root/"data/processed/regional_2024/policy_ordinance_article_evidence.csv"
        files["ordinance_article_evidence"]=pd.read_csv(law_articles,dtype=str).fillna("")
        files["ordinance_article_evidence"].to_csv(tables/"ordinance_article_evidence.csv",index=False,encoding="utf-8-sig")
    elif (tables/"ordinance_article_evidence.csv").exists():
        (tables/"ordinance_article_evidence.csv").unlink()
    summary["code_snapshot"]=summary["metadata_code_snapshot"]
    summary.update({
        "observed_r_min_pct":float(scores["관측 처리비율 R_r(%)"].min()),
        "observed_r_median_pct":float(scores["관측 처리비율 R_r(%)"].median()),
        "observed_r_max_pct":float(scores["관측 처리비율 R_r(%)"].max()),
        "standardized_s_min_pct":float(scores["전국 고정가중 표준화 S_r(%)"].min()),
        "standardized_s_median_pct":float(scores["전국 고정가중 표준화 S_r(%)"].median()),
        "standardized_s_max_pct":float(scores["전국 고정가중 표준화 S_r(%)"].max()),
        "positive_rs_regions":int(scores["구성 차이 R-S(%p)"].gt(0).sum()),
        "negative_rs_regions":int(scores["구성 차이 R-S(%p)"].lt(0).sum()),
    })
    manifest={"title":TITLE,"generated_at":generated,"status":"complete","summary":summary,
        "reproduction_command":r".\.venv\Scripts\python scripts/run_regional_indicator.py --year 2024 --level sigungu",
        "tables":{key:f"tables/regional_indicator_sigungu/{key}.csv" for key in files},
        "figures":{name:f"figures/regional_indicator_sigungu/{name}.png" for name in ("county_scatter","county_distribution","county_extremes")}}
    sections=[]
    for name,fig in figs.items():
        fragment=pio.to_html(fig,full_html=False,include_plotlyjs=True if not sections else False)
        sections.append(f'<section><h2>{html.escape(fig.layout.title.text)}</h2>{fragment}<p><a href="../../tables/regional_indicator_sigungu/scores.csv">전체 시군구 지표 CSV</a> · <a href="../../tables/regional_indicator_sigungu/weight_sensitivity.csv">가중치 민감도 CSV</a></p></section>')
    boundary_note=audit_note(summary)
    note=(f"공식 2024 원표의 지역명으로 {len(scores)}개 시군구·4재질 관측값을 비교했습니다. 처리행 {len(counties)}개. {boundary_note} 법제처 조례 연혁 후보 {summary['law_ordinance_version_candidates']}버전 중 {summary['law_ordinance_matched_statistical_unit_rows']}행이 통계단위 코드와 일치했고, 본문 {summary['law_ordinance_detail_json_count']}건을 받았습니다. "
          f"법령 연결 상태 {summary['law_linkage_status']}, 버전 메타데이터 대조 {summary['law_verified_document_version_rows']}건, 조문 근거 {summary['law_article_evidence_rows']}행입니다. "
          "2024년 시행일을 가진 연혁 버전의 제목 검색 결과이며, 2024년에 유효했던 전체 조례나 연중 적용기간을 확인한 목록은 아닙니다. "
          f"실제 정책-성과 검증 결합은 {summary['verified_join_rows']}행입니다.")
    md=[f"# {TITLE}",f"\n생성: {generated}\n","## 해석범위\n",note,"\n같은 전국 기준 재질 가중치로 각 시군구의 4재질별 실측 처리비율을 다시 계산한 **기술 비교**입니다. 지도화·정책노출 연결·시군구 회귀는 하지 않습니다.\n","## 요약\n",f"지역 수 {len(scores)} · 재질별 처리행 {len(counties)} · 최대 |R-S|: {maxrow['시군구']} {summary['max_abs_shift_pp']:.2f}%p.\n","## 시군구 전체 결과\n",_md_table(scores),"\n## 가중치 민감도 요약\n",_md_table(sens_summary),"\n## 제한\n","- 전국 기준비중은 KOSIS 2024 전국 4재질 발생량입니다. 분자는 물질재활용 처리량이며 최종 재생원료 수율이 아닙니다.\n- 행정코드·명칭 목록 감사는 GIS 경계 도형 또는 지역 간 반입·반출을 확인하지 않습니다. 행정명은 원표 기준입니다.\n- 시군구별 결과는 기술 통계입니다. 정책 자료가 없어 인과추론·정책 랭킹·회귀를 하지 않습니다.\n- 모든 지역에 같은 전국 가중치를 적용했습니다. 가중치 민감도 CSV에서 지역 평균·균등·해당 시군구 제외 전국 비중을 비교할 수 있습니다.\n","## 재현\n",f"`{manifest['reproduction_command']}`\n"]
    md.extend(["\n## 시군구 분포 요약\n",_md_table(descriptive_summary)])
    if summary["law_linkage_verified"]:
        md.extend(["\n## 법령 조문 근거\n","[조문 근거 CSV](../../tables/regional_indicator_sigungu/ordinance_article_evidence.csv)는 법령명·버전 일련번호·조문 위치·공식 원문 링크·원문 해시를 보존합니다. 재질·수거방식의 언급은 검토 단서이며 운영정책의 시행 증거가 아닙니다.\n"])
    (report/"report.md").write_text("\n".join(md)+"\n",encoding="utf-8")
    body=f'<header><h1>{TITLE}</h1><p>{html.escape(note)}</p><p><a href="report.md">Markdown 보고서</a></p></header><main>'+"".join(sections)+f'<section><h2>가중치 민감도 요약</h2>{sens_summary.to_html(index=False,float_format=lambda x:f"{x:.3f}")}<h2>상세 지표 전체</h2><p><a href="../../tables/regional_indicator_sigungu/scores.csv">scores.csv</a> · <a href="../../tables/regional_indicator_sigungu/contributions.csv">contributions.csv</a> · <a href="../../tables/regional_indicator_sigungu/weight_sensitivity.csv">weight_sensitivity.csv</a></p><p>재현: <code>{manifest["reproduction_command"]}</code></p></section></main>'
    summary_html=descriptive_summary.to_html(index=False,float_format=lambda x:f"{x:.3f}")
    body=body.replace("<main>",f'<main><section><h2>시군구 분포 요약</h2>{summary_html}</section>')
    if summary["law_linkage_verified"]:
        body=body.replace("</main>",'<section><h2>법령 조문 근거</h2><p><a href="../../tables/regional_indicator_sigungu/ordinance_article_evidence.csv">조문 근거 CSV</a>에서 법령 버전·조문 위치·공식 원문·해시를 확인할 수 있습니다. 조문 언급을 실제 운영정책의 증거로 환산하지 않습니다.</p></section></main>')
    page='<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+TITLE+'</title><style>body{margin:0;background:#f3f6f5;color:#172e35;font:16px/1.65 "Malgun Gothic",sans-serif}header,main{max-width:1200px;margin:auto;padding:28px}section{background:#fff;border:1px solid #dbe5e4;border-radius:12px;margin:22px 0;padding:24px;overflow:auto}a{color:#126c78}</style>'+body+'</html>'
    (report/"index.html").write_text(page,encoding="utf-8")
    manifest["artifacts"]={str(path.relative_to(output)).replace("\\","/"):{"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"bytes":path.stat().st_size} for base in (tables,figures,report) for path in sorted(base.iterdir()) if path.is_file() and path.name!="manifest.json"}
    (report/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return manifest
