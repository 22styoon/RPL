"""재질구성 표준화 지표·진단표·오프라인 보고서 생성."""
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib, html, json
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import yaml
from src.model import ROOT
from .standardization import compute_standardization
from .regional_inference import run_composition_diagnostics

TITLE = "2024년 시도별 재활용 처리비율: 재질 구성 표준화"


def _plot_figures(scores, contributions, sensitivity):
    ordered = scores.sort_values("관측 처리비율 R_r(%)")
    paired = ordered.melt(id_vars="시도", value_vars=["관측 처리비율 R_r(%)", "전국 고정가중 표준화 S_r(%)"],
                          var_name="지표", value_name="처리비율(%)")
    fig1 = px.bar(paired, x="처리비율(%)", y="시도", color="지표", barmode="group", orientation="h",
                  title="관측 비율 R과 전국 고정 가중 표준화 비율 S")
    fig1.update_layout(template="plotly_white", font={"family":"Malgun Gothic, sans-serif"}, height=680,
                       legend_title_text="", margin={"l":100,"r":30,"t":80,"b":50})

    pivot = contributions.pivot(index="시도", columns="재질", values="R-S 기여도(%p)").reindex(ordered.시도)
    fig2 = go.Figure()
    colors = ["#127c80", "#315b96", "#d39745", "#9a5973"]
    for material, color in zip(pivot.columns, colors):
        fig2.add_bar(y=pivot.index, x=pivot[material], name=material, orientation="h", marker_color=color)
    fig2.update_layout(title="재질별 구성 차이 기여도 (합계 = R-S)", barmode="relative", template="plotly_white",
                       font={"family":"Malgun Gothic, sans-serif"}, height=680, xaxis_title="기여도 (%p)",
                       legend_title_text="재질", margin={"l":100,"r":30,"t":80,"b":50})

    methods = ["전국 발생량 비중(기준)", "17개 시도 재질비중 평균", "4재질 균등", "해당 시도 제외 전국 비중"]
    wide = sensitivity.pivot(index="시도", columns="가중치 기준", values="표준화 처리비율(%)").reindex(ordered.시도)[methods]
    fig3 = px.imshow(wide, aspect="auto", color_continuous_scale="Tealrose", text_auto=".1f",
                     labels={"x":"고정 재질 가중치 기준","y":"시도","color":"S (%)"},
                     title="가중치 선택에 따른 표준화 점수 민감도")
    fig3.update_layout(template="plotly_white", font={"family":"Malgun Gothic, sans-serif"}, height=650,
                       margin={"l":100,"r":30,"t":80,"b":100})
    return {"scores": fig1, "contributions": fig2, "weight_sensitivity": fig3}, paired


def _save_static(scores, contributions, sensitivity, figure_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    families={f.name for f in font_manager.fontManager.ttflist}
    font=next((name for name in ("Malgun Gothic","Noto Sans CJK KR","NanumGothic","AppleGothic") if name in families),"DejaVu Sans")
    plt.rcParams.update({"font.family":font,"axes.unicode_minus":False,"svg.fonttype":"path"})
    ordered=scores.sort_values("관측 처리비율 R_r(%)")
    fig,ax=plt.subplots(figsize=(11,8)); y=np.arange(len(ordered)); h=.36
    ax.barh(y-h/2,ordered["관측 처리비율 R_r(%)"],h,label="관측 R",color="#315b96")
    ax.barh(y+h/2,ordered["전국 고정가중 표준화 S_r(%)"],h,label="표준화 S",color="#127c80")
    ax.set_yticks(y,ordered.시도);ax.set_xlabel("처리비율 (%)");ax.set_title("관측 비율 R과 전국 고정 가중 표준화 비율 S",loc="left",fontweight="bold");ax.legend();ax.grid(axis="x",alpha=.2);ax.set_axisbelow(True)
    for ext in ("png","svg"):fig.savefig(figure_dir/f"regional_scores.{ext}",dpi=160,bbox_inches="tight")
    plt.close(fig)
    pivot=contributions.pivot(index="시도",columns="재질",values="R-S 기여도(%p)").reindex(ordered.시도)
    fig,ax=plt.subplots(figsize=(11,8));bottom_pos=np.zeros(len(pivot));bottom_neg=np.zeros(len(pivot))
    colors=["#127c80","#315b96","#d39745","#9a5973"]
    for material,color in zip(pivot.columns,colors):
        vals=pivot[material].to_numpy();pos=np.maximum(vals,0);neg=np.minimum(vals,0)
        ax.barh(pivot.index,pos,left=bottom_pos,label=material,color=color);ax.barh(pivot.index,neg,left=bottom_neg,color=color)
        bottom_pos+=pos;bottom_neg+=neg
    ax.axvline(0,color="#344",linewidth=.8);ax.set_xlabel("기여도 (%p)");ax.set_title("재질별 구성 차이 기여도 (합계 = R-S)",loc="left",fontweight="bold");ax.legend(ncol=2);ax.grid(axis="x",alpha=.2);ax.set_axisbelow(True)
    for ext in ("png","svg"):fig.savefig(figure_dir/f"regional_contributions.{ext}",dpi=160,bbox_inches="tight")
    plt.close(fig)
    methods=["전국 발생량 비중(기준)","17개 시도 재질비중 평균","4재질 균등","해당 시도 제외 전국 비중"]
    wide=sensitivity.pivot(index="시도",columns="가중치 기준",values="표준화 처리비율(%)").reindex(ordered.시도)[methods]
    fig,ax=plt.subplots(figsize=(10,8));im=ax.imshow(wide.to_numpy(),aspect="auto",cmap="RdYlBu_r")
    ax.set_yticks(np.arange(len(wide)),wide.index);ax.set_xticks(np.arange(len(methods)),["전국","지역 평균","균등","지역 제외"],rotation=20,ha="right");ax.set_title("가중치 선택에 따른 표준화 점수 민감도",loc="left",fontweight="bold")
    fig.colorbar(im,ax=ax,label="S (%)");fig.tight_layout()
    for ext in ("png","svg"):fig.savefig(figure_dir/f"regional_weight_sensitivity.{ext}",dpi=160,bbox_inches="tight")
    plt.close(fig)


def _md_table(frame):
    def cell(value):
        if pd.isna(value):return ""
        if isinstance(value,(float,np.floating)):return f"{value:.3f}"
        return str(value).replace("|","/").replace("\n"," ")
    columns=list(frame.columns)
    return "| "+" | ".join(columns)+" |\n| "+" | ".join("---" for _ in columns)+" |\n"+"\n".join("| "+" | ".join(cell(v) for v in row)+" |" for row in frame.itertuples(index=False,name=None))


def run(root=ROOT, output_root=None):
    root=Path(root).resolve(); output=Path(output_root or root/"outputs").resolve()
    report=output/"reports/regional_indicator"; tables=output/"tables/regional_indicator"; figures=output/"figures/regional_indicator"
    for directory in (report,tables,figures):directory.mkdir(parents=True,exist_ok=True)
    source=root/"data/processed/kosis_materials_2024.csv"
    regional=root/"data/processed/regional_2024/manifest.json"
    raw_dir=root/"data/raw/regional_2024/kr_waste_2024_detail"
    raw_meta_path=raw_dir/"latest.json"
    raw_meta=json.loads(raw_meta_path.read_text(encoding="utf-8")) if raw_meta_path.exists() else {}
    raw=root/str(raw_meta["raw_file"]).replace("\\","/") if raw_meta.get("raw_file") else None
    if raw is not None:
        if not raw.resolve().is_relative_to(root):raise ValueError("지역 원본 경로가 저장소 밖을 가리킵니다.")
        if not raw.exists() or hashlib.sha256(raw.read_bytes()).hexdigest()!=raw_meta.get("sha256"):
            raise ValueError("지역 원본 ZIP SHA-256 검증 실패")
    materials=pd.read_csv(source)
    scores,contributions,sensitivity,sensitivity_summary,weights=compute_standardization(materials)
    thresholds=yaml.safe_load((root/"configs/regional_indicator.yaml").read_text(encoding="utf-8")).get("instability_thresholds",{})
    score_wide=sensitivity.pivot(index="시도",columns="가중치 기준",values="표준화 처리비율(%)")
    rank_wide=sensitivity.pivot(index="시도",columns="가중치 기준",values="순위(높은 값=1)")
    stability=pd.DataFrame({"시도":score_wide.index,
        "가중치별 점수 범위(%p)":score_wide.max(axis=1)-score_wide.min(axis=1),
        "가중치별 순위 범위":rank_wide.max(axis=1)-rank_wide.min(axis=1)})
    stability["점수 민감"] = stability["가중치별 점수 범위(%p)"].gt(float(thresholds.get("score_span_pp",5.0)))
    stability["순위 민감"] = stability["가중치별 순위 범위"].gt(int(thresholds.get("rank_span",3)))
    stability["종합 민감"] = stability["점수 민감"]|stability["순위 민감"]
    inference=run_composition_diagnostics(materials)
    files={"scores":scores,"contributions":contributions,"weight_sensitivity":sensitivity,
           "weight_stability_by_region":stability.reset_index(drop=True),
           "weight_sensitivity_summary":sensitivity_summary,"national_weights":weights}
    for name,frame in files.items():frame.to_csv(tables/f"{name}.csv",index=False,encoding="utf-8-sig")
    if inference["status"]=="computed":
        for key,name in (("tests","inference_tests"),("coefficients","inference_coefficients"),("vif","inference_vif"),("diagnostics","inference_diagnostics"),("leave_one_out","inference_leave_one_out")):
            inference[key].to_csv(tables/f"{name}.csv",index=False,encoding="utf-8-sig")
    else:
        pd.DataFrame([{"status":inference["status"],"reason":inference["reason"],"n":inference["n"]}]).to_csv(tables/"inference_withheld.csv",index=False,encoding="utf-8-sig")
    figs,paired=_plot_figures(scores,contributions,sensitivity)
    paired.to_csv(tables/"scores_plot.csv",index=False,encoding="utf-8-sig")
    for name,fig in figs.items():
        fig.write_json(figures/f"{name}.json")
        fig.write_html(figures/f"{name}.html",include_plotlyjs=True)
    _save_static(scores,contributions,sensitivity,figures)
    generated=datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")
    data_manifest={}
    code_files=[root/path for path in ("configs/regional_indicator.yaml","configs/regional_recycling_sources.yaml",
        "src/analysis/standardization.py","src/analysis/regional_inference.py","src/analysis/regional_indicator_report.py",
        "src/regional_data/clients.py","src/regional_data/geocodes.py","src/regional_data/parsers.py",
        "src/regional_data/policy_records.py","src/regional_data/prepare.py","src/regional_data/validation.py",
        "scripts/collect_regional_recycling.py","scripts/prepare_regional_recycling.py",
        "scripts/join_regional_policy.py","scripts/run_regional_indicator.py")]
    input_files=[source,regional,raw_meta_path,root/"data/processed/regional_2024/sido_2024_materials_verified.csv",
                 root/"data/processed/regional_2024/sigungu_2024_materials_verified.csv",
                 root/"data/processed/regional_2024/admin_codes_202412.csv",*code_files]
    if raw is not None:input_files.append(raw)
    for path in input_files:
        if path.exists():data_manifest[str(path.relative_to(root)).replace("\\","/")]={"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"bytes":path.stat().st_size}
    if regional.exists():regional_data=json.loads(regional.read_text(encoding="utf-8"))
    else:regional_data={"sido_rows":68,"sigungu_candidates":0,"sigungu_verified_rows":0,"sigungu_verified_regions":0,"policy_verified_rows":0,"verified_join_rows":0}
    summary={"reference_year":2024,"sido_rows":len(scores),"sigungu_candidates":regional_data.get("sigungu_candidates",0),
             "sigungu_verified_rows":regional_data.get("sigungu_verified_rows",0),"sigungu_verified_regions":regional_data.get("sigungu_verified_regions",0),
             "policy_candidates":regional_data.get("policy_candidates",0),"policy_verified_rows":regional_data.get("policy_verified_rows",0),
             "verified_join_rows":regional_data.get("verified_join_rows",0),"inference_status":inference["status"],"source_files":data_manifest}
    manifest={"title":TITLE,"generated_at":generated,"status":"complete","summary":summary,
              "reproduction_command":r".\.venv\Scripts\python scripts/run_regional_indicator.py --year 2024 --level sido",
              "tables":{key:f"tables/regional_indicator/{key}.csv" for key in files},
              "figures":{name:f"figures/regional_indicator/{name}.png" for name in ("regional_scores","regional_contributions","regional_weight_sensitivity")},
              "inference_status":inference["status"]}
    (report/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    weights_display=weights.copy();weights_display["전국 발생량 가중치"]*=100;weights_display=weights_display.rename(columns={"전국 발생량 가중치":"전국 발생 비중(%)"})
    sections=[]
    for name,fig in figs.items():
        svg_name={"scores":"regional_scores","contributions":"regional_contributions","weight_sensitivity":"regional_weight_sensitivity"}[name]
        fragment=pio.to_html(fig,full_html=False,include_plotlyjs=True if not sections else False)
        sections.append(f'<section><h2>{html.escape(fig.layout.title.text)}</h2>{fragment}<p><a href="../../tables/regional_indicator/{name}.csv">관련 CSV</a> · <a href="../../figures/regional_indicator/{svg_name}.svg">SVG</a></p></section>')
    # The report deliberately separates the verified 17-region indicator from the incomplete policy join.
    inference_html=""
    if inference["status"]=="computed":
        inference_html=("<h3>OLS 공동검정 및 강건성 참고</h3><p>귀무가설: 폐지·폐합성수지·폐금속 발생 구성비 계수가 모두 0. R은 같은 구성비와 재질별 비율의 산술 결합이므로 이 검정은 기계적 연관을 포함하며 지표 타당성이나 정책효과 증거가 아니다.</p>"+
                        inference["tests"].to_html(index=False,float_format=lambda x:f"{x:.4g}")+"<h3>계수와 불확실성 추정</h3>"+inference["coefficients"].to_html(index=False,float_format=lambda x:f"{x:.4g}")+"<p>이분산 진단: Breusch–Pagan LM p="+f"{inference['bp_lm_p']:.4g}"+"; HC0/HC3는 이분산 검정이 아니라 강건 공분산 추정이다. 표본은 17개 시도 전수 집계이며 일반 표본추출 가정의 p값 해석에는 한계가 있다.</p>")
    note=(f"시군구 원문 파싱 후보 {summary['sigungu_candidates']}행, 이름·2024년 말 행정코드 연결 자료 {summary['sigungu_verified_rows']}행 / {summary['sigungu_verified_regions']}개 시군구. "
          f"2024년 실제 정책 후보 {summary['policy_candidates']}건, 검증 정책 {summary['policy_verified_rows']}건, 검증 결합 {summary['verified_join_rows']}행. 행정코드는 2024년 12월 스냅샷이라 연중 경계변경 감사가 남았고, 정책 자료가 없어 결합결과는 0행이다.")
    md=[f"# {TITLE}",f"\n생성: {generated}\n","## 질문과 해석 범위\n", "같은 2024년 시도에서 4재질의 실제 발생량 구성을 전국 기준으로 고정했을 때, 관측 물질재활용 처리비율이 어떻게 달라지는가? 이 값은 재질구성 표준화 비교지표이며 최종 재생원료 생산률이나 정책의 인과효과가 아닙니다.\n",
        "## 산식\n", "재질별 관측 처리비율 `p_rm=M_rm/G_rm`, 지역 내 발생비중 `a_rm=G_rm/Σ_m G_rm`, 2024년 전국 발생량 기준비중 `w_m=G_전국,m/Σ_m G_전국,m`을 사용합니다. `R_r=100Σa_rm p_rm`, `S_r=100Σw_m p_rm`, 구성 차이 `R_r-S_r=100Σ(a_rm-w_m)p_rm`입니다. 전국 행은 17개 시도 합계에 더하지 않습니다.\n",
        "## 기준 가중치\n",_md_table(weights_display),"\n## 시도 결과\n",_md_table(scores),"\n## 구성 기여도\n",_md_table(contributions),"\n## 가중치 민감도\n",_md_table(sensitivity_summary),"\n## 보조 회귀와 진단\n"]
    if inference["status"]=="computed":md.extend([inference["interpretation"]+"\n",_md_table(inference["tests"]),"\n계수·HC3 신뢰구간, VIF, 레버리지/Cook 거리, 시도별 제외 결과는 같은 폴더의 CSV에 저장했습니다. Breusch–Pagan은 별도 이분산 진단입니다.\n"])
    else:md.append(f"회귀 보류: {inference.get('reason')}\n")
    md.extend(["\n## 지역별 가중치 안정성\n",f"불안정 기준은 점수 범위 {thresholds.get('score_span_pp',5.0)}%p 초과 또는 순위 범위 {thresholds.get('rank_span',3)} 초과입니다. 이는 가중치 민감성 경고선이며 통계적 유의성 기준이 아닙니다.\n",_md_table(stability),"\n## 시군구·정책 자료 상태\n",note,"\n## 재현\n",f"`{manifest['reproduction_command']}`","\n출처: [KOSIS 2024 생활폐기물 통계](https://kosis.kr/statHtml/statHtml.do?orgId=106&tblId=DT_106N_29_2020005), [한국폐기물협회 2024 전국 통계 원문](https://kwaste.or.kr/data/01.php).\n","## 한계\n","- 대응 4품목만 포함하며 복합·영농폐기물 등은 제외했습니다. 처리비율 분자는 물질재활용 처리량이고 최종 재생원료 생산량이 아닙니다.\n- 표준화는 관측 처리비율의 구성만 고정합니다. 지역 간 시설·반입·반출·집계경계·정책 차이는 통제하지 않습니다.\n- 민감도 기준은 전국 발생비중, 시도별 재질구성 평균, 균등, 해당 시도를 제외한 전국 구성입니다. 순위 변화는 가중치 선택에 대한 설명이지 정책 우열이 아닙니다.\n- 시도 17개는 관측 전수 집계입니다. p값과 신뢰구간은 모델 가정에 의존하고 인과효과나 외적 타당성을 입증하지 않습니다.\n- 정책 시행지역·대상범위의 공식 자료가 없으므로 정책별 비교는 하지 않습니다.\n"])
    (report/"report.md").write_text("\n".join(md)+"\n",encoding="utf-8")
    weights_html=weights_display.to_html(index=False,float_format=lambda x:f"{x:.3f}")
    scores_html=scores.to_html(index=False,float_format=lambda x:f"{x:.3f}")
    sensitivity_html=sensitivity_summary.to_html(index=False,float_format=lambda x:f"{x:.3f}")
    stability_html=stability.to_html(index=False)
    body=(f'<header><p>2024년 실제 KOSIS 행정통계 · 17개 시도 · 출처 해시 기록</p><h1>{TITLE}</h1><p>재질 구성을 전국 실측 발생량 비중으로 고정한 비교 지표입니다. 정책효과 또는 최종 재생원료 수율을 뜻하지 않습니다.</p><p><a href="report.md">Markdown 보고서</a></p></header><main><section><h2>기준 가중치와 시도별 지표</h2>'+weights_html+scores_html+'</section>'+"".join(sections)+'<section><h2>가중치 민감도 요약</h2>'+sensitivity_html+'<h2>시도별 안정성 표시</h2>'+stability_html+'<h2>통계검정</h2>'+inference_html+'<h2>시군구·정책 자료 상태</h2><p>'+html.escape(note)+'</p><h2>재현</h2><code>'+html.escape(manifest["reproduction_command"])+'</code></section><footer><p>자료: <a href="https://kosis.kr/statHtml/statHtml.do?orgId=106&amp;tblId=DT_106N_29_2020005">KOSIS 표</a> · <a href="https://kwaste.or.kr/data/01.php">2024 전국 폐기물 통계 원문</a></p></footer></main>')
    page='<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+TITLE+'</title><style>body{margin:0;background:#f3f6f5;color:#172e35;font:16px/1.65 "Malgun Gothic",sans-serif}header,main{max-width:1200px;margin:auto;padding:28px}header{padding-top:44px}section{background:white;border:1px solid #dbe5e4;border-radius:12px;margin:22px 0;padding:24px;overflow:auto}h1{font-size:32px}table{border-collapse:collapse;font-size:12px;display:block;overflow:auto;max-height:480px}td,th{padding:7px;border-bottom:1px solid #e1e8e7;white-space:nowrap;text-align:right}th{position:sticky;top:0;background:#eef4f3}a{color:#126c78}footer{max-width:1200px;margin:auto;padding:24px;color:#52666c}</style>'+body+'</html>'
    (report/"index.html").write_text(page,encoding="utf-8")
    manifest["artifacts"]={str(path.relative_to(output)).replace("\\","/"):{"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"bytes":path.stat().st_size}
        for base in (tables,figures,report) for path in sorted(base.iterdir()) if path.is_file() and path.name!="manifest.json"}
    (report/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return manifest
