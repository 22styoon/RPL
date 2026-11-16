"""저장 원자료로 분석·PNG/SVG·대화형 HTML·CSV를 한 번에 재생성한다."""
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,html,json,os
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.io as pio
from src.model import ROOT
from src.comparability import assess_comparability
from .trend import yearly_trend
from .composition import material_composition
from .regional import regional_profiles
from .costs import guro_flows,guro_budgets
from .quality import facility_quality
from .international import eurostat_generation,nea_materials,uk_facility_receipts

TITLE="RPL | 분리배출 정책 통계분석 및 시각화"
COLORS=["#127c80","#315b96","#d39745","#9a5973","#8d9b9f","#82679e"]

def build_analyses(root=ROOT):
    root=Path(root)
    public=pd.read_csv(root/"data/processed/kosis_public_waste.csv")
    materials=pd.read_csv(root/"data/processed/kosis_materials_2024.csv")
    guro=pd.read_csv(root/"data/processed/guro_recycling.csv")
    results=[yearly_trend(public),material_composition(materials),regional_profiles(materials),guro_flows(guro),guro_budgets(guro)]
    sources=[root/"data/processed"/name for name in ("kosis_public_waste.csv","kosis_materials_2024.csv","guro_recycling.csv")]
    unavailable=[]
    facility=root/"data/processed/public_data/facilities/latest_complete.json"
    if facility.exists():
        meta=json.loads(facility.read_text(encoding="utf-8"))
        path=facility.parent/meta["run_id"]/"records.json"
        if path.exists():
            results.append(facility_quality(pd.DataFrame(json.loads(path.read_text(encoding="utf-8")))))
            sources.extend([facility,path])
    for source,analyzer in (("eurostat",eurostat_generation),("nea",nea_materials),("uk_waste",uk_facility_receipts)):
        directory=root/"data/processed/international"/source
        path=directory/"records.csv"
        manifest=directory/"manifest.json"
        if not path.exists() or not manifest.exists():
            unavailable.append({"topic":source,"reason":"정규화 통계 미확보"})
            continue
        meta=json.loads(manifest.read_text(encoding="utf-8"))
        raw_path=root/str(meta["raw_file"]).replace("\\","/")
        if not raw_path.exists() or hashlib.sha256(raw_path.read_bytes()).hexdigest()!=meta["sha256"]:
            raise ValueError(source+": 보존 원자료 SHA-256 검증 실패")
        if hashlib.sha256(path.read_bytes()).hexdigest()!=meta.get("processed_sha256"):
            raise ValueError(source+": 정규화 자료 SHA-256 검증 실패")
        frame=pd.read_csv(path)
        results.append(analyzer(frame))
        sources.extend([path,manifest,raw_path])
    for topic,reason in (
        ("가구 시간 분포·부트스트랩","국내 가구별 실측 시간일지 미확보. 문헌 평균으로 가상 표본을 생성하지 않음."),
        ("검증 처리단가 분포","동일 서비스기간·지역·품목·공정의 금액/처리톤수 검증 완료 0건."),
        ("한국·해외 동일 그래프","분자·분모·범위 호환성 미검증으로 직접 국가 순위·통합 회귀 차단."),
        ("OECD 플라스틱 흐름","모형 추정치의 구조화 테이블·SDMX 식별자 미검증."),
        ("영국 최종 수율·오염도","반입 자료만 확보. 반출·공정손실·재고·품질 측정자료 미연결.")
    ):
        unavailable.append({"topic":topic,"reason":reason})
    return results,sources,unavailable

def plotly_figure(result):
    frame=result.plot
    common=dict(data_frame=frame,title=result.title,color=result.series,color_discrete_sequence=COLORS)
    if result.kind=="line":
        fig=px.line(x=result.x,y=result.y,markers=True,**common)
        fig.update_xaxes(dtick=1)
    elif result.kind=="barh":
        fig=px.bar(x=result.y,y=result.x,orientation="h",**common)
    else:
        fig=px.bar(x=result.x,y=result.y,barmode="stack" if result.kind=="stacked" else "group",**common)
    fig.update_layout(template="plotly_white",font={"family":"Malgun Gothic, sans-serif","size":13},
        height=max(450,min(1100,len(frame)*25+150)) if result.kind=="barh" else 460,
        legend_title_text=result.series,margin={"b":100,"t":80},paper_bgcolor="white")
    caption=f"{result.measurement_type} · {result.year_label} · 단위 {result.unit} · 분석표 {len(result.table)}행 · 행정집계 기술통계, 표본 신뢰구간 미산출"
    fig.add_annotation(text=caption,xref="paper",yref="paper",x=0,y=-.2,showarrow=False,xanchor="left",font={"size":11,"color":"#58656c"})
    fig.update_layout(meta={"analysis_id":result.analysis_id,"measurement_type":result.measurement_type,"source_urls":result.sources})
    return fig

def save_static(result,path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    families={font.name for font in font_manager.fontManager.ttflist}
    font=next((name for name in ("Malgun Gothic","Noto Sans CJK KR","NanumGothic","AppleGothic") if name in families),"DejaVu Sans")
    plt.rcParams.update({"font.family":font,"axes.unicode_minus":False,"svg.fonttype":"path"})
    frame=result.plot
    fig,ax=plt.subplots(figsize=(11,max(5,min(13,len(frame)*.25+1.7))) if result.kind=="barh" else (11,5.8))
    if result.kind=="line":
        groups=frame.groupby(result.series,sort=False) if result.series else [(result.y,frame)]
        for index,(label,part) in enumerate(groups):
            ax.plot(part[result.x],part[result.y],marker="o",label=str(label),color=COLORS[index%len(COLORS)])
        ax.set_xticks(sorted(frame[result.x].unique()))
        if result.series:
            ax.legend()
    elif result.kind=="barh":
        ax.barh(frame[result.x].astype(str),frame[result.y],color=COLORS[0])
    elif result.kind=="stacked":
        pivot=frame.pivot(index=result.x,columns=result.series,values=result.y).reindex(index=frame[result.x].drop_duplicates(),columns=frame[result.series].drop_duplicates())
        bottom=np.zeros(len(pivot))
        for index,column in enumerate(pivot):
            values=pivot[column].to_numpy()
            ax.bar(pivot.index.astype(str),values,bottom=bottom,label=column,color=COLORS[index%len(COLORS)])
            bottom=bottom+values
        ax.legend(loc="upper left",bbox_to_anchor=(1.01,1),fontsize=9)
    else:
        ax.bar(frame[result.x].astype(str),frame[result.y],color=COLORS[0])
    ax.set_title(result.title,pad=16,loc="left",fontweight="bold")
    ax.set_xlabel(result.unit if result.kind=="barh" else result.x)
    ax.set_ylabel(result.x if result.kind=="barh" else result.unit)
    ax.grid(axis="x" if result.kind=="barh" else "y",alpha=.15)
    ax.set_axisbelow(True)
    for spine in ("top","right"):
        ax.spines[spine].set_visible(False)
    fig.text(.02,.015,f"{result.measurement_type} | {result.year_label} | 분석표 {len(result.table)}행 | 출처: "+"; ".join(result.sources),fontsize=7,wrap=True)
    fig.tight_layout(rect=(0,.06,1,1))
    for extension in ("png","svg"):
        fig.savefig(path.with_suffix("."+extension),dpi=160,bbox_inches="tight")
    plt.close(fig)

def comparability_table():
    korea=dict(country="KR",year=2024,waste_scope="KOSIS corresponding four household waste materials",
        material="paper_plastics_metal_glass",process_stage="material treatment",
        numerator_definition="material recycling treatment mass",denominator_definition="generated four-material mass",
        mass_unit="t",geography_level="national")
    candidates=[
        ("Eurostat",dict(country="multiple",year=2024,waste_scope="municipal waste; national reporting definitions",material="all",process_stage="generation",numerator_definition="GEN",denominator_definition="inhabitants",mass_unit="kg/inhabitant",geography_level="national")),
        ("NEA",dict(country="SG",year=2024,waste_scope="domestic and non-domestic; includes C&D",material="all",process_stage="reported broad recycling",numerator_definition="reported recycled includes wood fuel",denominator_definition="generated all waste",mass_unit="t",geography_level="national")),
        ("EPA",dict(country="US",year=2018,waste_scope="US MSW excluding C&D",material="all",process_stage="generation",numerator_definition="estimated generation",denominator_definition="US MSW",mass_unit="t",geography_level="national"))
    ]
    return pd.DataFrame([{"한국 기준":"KOSIS 대응 4품목","비교 출처":name,"직접 비교 가능":assessment["compatible"],"제외 사유":"; ".join(assessment["reasons"])}
        for name,other in candidates for assessment in [assess_comparability(korea,other)]])

def _markdown_table(frame):
    def cell(value):
        return "" if pd.isna(value) else str(value).replace("|","/").replace("\n"," ")
    columns=list(frame.columns)
    return "| "+" | ".join(map(str,columns))+" |\n| "+" | ".join("---" for _ in columns)+" |\n"+"\n".join("| "+" | ".join(cell(v) for v in row)+" |" for row in frame.itertuples(index=False,name=None))

def run(root=ROOT,output_root=None):
    root=Path(root).resolve()
    output=Path(output_root or root/"outputs").resolve()
    report_dir=output/"reports/statistical_analysis"
    figure_dir=output/"figures/statistical_analysis"
    table_dir=output/"tables/statistical_analysis"
    for directory in (report_dir,figure_dir,table_dir):
        directory.mkdir(parents=True,exist_ok=True)
    results,sources,unavailable=build_analyses(root)
    generated=datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")
    md=[f"# {TITLE}",f"\n생성: {generated}\n",f"독립 분석 {len(results)}개. 저장한 실데이터로 재생성하며 정책 시나리오·해외 수치를 한국 실측으로 적용하지 않는다.\n"]
    sections=[]
    entries=[]
    include_js=True
    for result in results:
        table_path=table_dir/(result.analysis_id+".csv")
        plot_path=table_dir/(result.analysis_id+"_plot.csv")
        result.table.to_csv(table_path,index=False,encoding="utf-8-sig")
        result.plot.to_csv(plot_path,index=False,encoding="utf-8-sig")
        fig=plotly_figure(result)
        figure_base=figure_dir/result.analysis_id
        save_static(result,figure_base)
        fig.write_json(figure_base.with_suffix(".json"))
        fig.write_html(figure_base.with_suffix(".html"),include_plotlyjs=True)
        fragment=pio.to_html(fig,full_html=False,include_plotlyjs=True if include_js else False,div_id=result.analysis_id+"-plot")
        include_js=False
        relative=lambda path:os.path.relpath(path,report_dir).replace("\\","/")
        md.extend([f"\n## {result.title}\n",f"질문: {result.question}\n",f"구분: {result.measurement_type} · 기준: {result.year_label} · 단위: {result.unit} · 표 {len(result.table)}행\n",
            result.interpretation+"\n",f"![{result.title}]({relative(figure_base.with_suffix('.png'))})\n",_markdown_table(result.table),"\n",
            "출처: "+", ".join(f"[원자료]({url})" for url in result.sources)+"\n",f"분석 코드: {result.code_source}\n",
            "한계: "+" / ".join(result.limitations)+"\n"])
        safe=html.escape
        source_links=" · ".join(f'<a href="{safe(url,quote=True)}">공식 출처</a>' for url in result.sources)
        section=f'<section id="{result.analysis_id}"><span class="tag">{safe(result.measurement_type)} · {safe(result.year_label)}</span><h2>{safe(result.title)}</h2><p class="question">{safe(result.question)}</p><p>{safe(result.interpretation)}</p>{fragment}<details><summary>분석표 {len(result.table)}행 · CSV · 정의와 한계</summary>{result.table.to_html(index=False,na_rep="미입력",float_format=lambda x:f"{x:,.3f}")}<p><a href="{relative(table_path)}">분석표 CSV</a> · <a href="{relative(plot_path)}">그래프 수치 CSV</a> · <a href="{relative(figure_base.with_suffix(".svg"))}">SVG</a> · {source_links}</p><p>분석 코드: {safe(result.code_source)}</p><ul>'+ "".join("<li>"+safe(note)+"</li>" for note in result.limitations)+"</ul></details></section>"
        sections.append(section)
        entries.append(dict(analysis_id=result.analysis_id,title=result.title,category=result.category,
            question=result.question,interpretation=result.interpretation,limitations=result.limitations,
            measurement_type=result.measurement_type,year_label=result.year_label,unit=result.unit,
            row_count=len(result.table),sources=result.sources,code_source=result.code_source,
            table=str(table_path.relative_to(output)),plot_data=str(plot_path.relative_to(output)),
            figure_json=str(figure_base.with_suffix(".json").relative_to(output)),
            png=str(figure_base.with_suffix(".png").relative_to(output)),
            svg=str(figure_base.with_suffix(".svg").relative_to(output)),
            table_sha256=hashlib.sha256(table_path.read_bytes()).hexdigest(),
            plot_sha256=hashlib.sha256(plot_path.read_bytes()).hexdigest(),extra=result.extra))
    compatibility=comparability_table()
    compatibility.to_csv(table_dir/"comparability.csv",index=False,encoding="utf-8-sig")
    unavailable_frame=pd.DataFrame(unavailable)
    unavailable_frame.to_csv(table_dir/"unavailable.csv",index=False,encoding="utf-8-sig")
    md.extend(["\n## 직접 국가 비교 검사\n",_markdown_table(compatibility),"\n## 자료 공백\n",_markdown_table(unavailable_frame)])
    manifest=dict(title=TITLE,generated_at=generated,status="complete",analysis_count=len(results),analyses=entries,
        source_files=[{"path":str(path.relative_to(root)),"sha256":hashlib.sha256(path.read_bytes()).hexdigest()} for path in sources],
        unavailable=unavailable,reproduction_command=r".\.venv\Scripts\python run_statistical_analysis.py",
        method="행정통계·공개 예산의 기술통계. 회귀·인과추론·가상 표본 생성 없음.")
    (report_dir/"manifest.json").write_bytes((json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode("utf-8"))
    (report_dir/"report.md").write_bytes(("\n".join(md)+"\n").encode("utf-8"))
    toc="".join(f'<a href="#{r.analysis_id}">{html.escape(r.title)}</a>' for r in results)
    page='<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+TITLE+'</title><style>body{margin:0;background:#f2f5f5;color:#162d36;font-family:"Malgun Gothic",sans-serif;line-height:1.65}header,main{max-width:1180px;margin:auto;padding:32px}header{padding-top:48px}h1{font-size:32px;letter-spacing:-1px}h2{margin:10px 0}section{background:white;border:1px solid #dde6e7;border-radius:14px;margin:24px 0;padding:28px;overflow:hidden}.tag{color:#127c80;font-size:13px;font-weight:700}.question{font-size:18px}.cards{display:flex;gap:16px}.card{padding:18px;background:white;border-radius:10px;flex:1}.card strong{display:block;font-size:28px}nav{display:flex;flex-wrap:wrap;gap:8px}a{color:#126c78}nav a{background:#e2eded;padding:6px 12px;border-radius:5px;text-decoration:none}table{border-collapse:collapse;width:100%;font-size:12px;display:block;overflow:auto}td,th{text-align:left;padding:8px;border-bottom:1px solid #e1e7e8;white-space:nowrap}summary{cursor:pointer;color:#126c78}details{margin-top:18px}li{margin:6px 0}footer{font-size:12px;color:#52666c}@media(max-width:650px){header,main{padding:16px}section{padding:16px}.cards{display:block}}</style><header><span class="tag">실제 통계 · 출처 추적 · Python으로 재생성</span><h1>'+TITLE+'</h1><p>발생·처리·시설·비용을 각각의 연구 질문으로 분석합니다. 관측 통계와 예산 대리값, 추정치와 자료 공백을 구분합니다.</p><div class="cards"><div class="card">독립 분석<strong>'+str(len(results))+'</strong></div><div class="card">국내 비용 사례<strong>115.29억원</strong>구로구 2024 공개 예산 · 총사회비용과 구분</div><div class="card">정의가 다른 국가 지표<strong>직접 비교 차단</strong>한국 수치와 임의 결합하지 않음</div></div><p>생성 '+generated+'</p><nav>'+toc+'</nav></header><main>'+"".join(sections)+'<section><h2>직접 국가 비교 검사</h2>'+compatibility.to_html(index=False)+'<h2>자료 공백과 다음 수집</h2>'+unavailable_frame.to_html(index=False)+'<p>가구별 원자료가 없어 시간 분포·부트스트랩 신뢰구간은 생성하지 않았습니다. 검증된 원/t 단가도 아직 없습니다.</p></section><footer>재생성: .venv/Scripts/python run_statistical_analysis.py · PNG/SVG·그래프 수치 CSV·출처 SHA-256은 함께 저장됩니다. 외부 CDN 없이 그래프를 열 수 있습니다.</footer></main></html>'
    (report_dir/"index.html").write_bytes(page.encode("utf-8"))
    return manifest
