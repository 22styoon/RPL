"""관측 통계·시각화 보고서 재생성. 기본 실행은 네트워크를 사용하지 않는다."""
import argparse,json
from pathlib import Path
import sys
from src.model import ROOT

def main(argv=None):
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,"reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description="RPL 실제 통계 분석·CSV·PNG/SVG·대화형 보고서")
    parser.add_argument("--output-root",type=Path,default=ROOT/"outputs")
    parser.add_argument("--refresh-external",action="store_true",help="분석 전 Eurostat·NEA·EPA 공식 자료 재수집")
    parser.add_argument("--skip-regional-indicator",action="store_true",help="별도 2024 시도 R/S 표준화 보고서 생성을 생략")
    args=parser.parse_args(argv)
    if args.refresh_external:
        from scripts.collect_international import collect_many
        results=collect_many(["eurostat","nea","epa"])
        if any(row["status"]=="failed" for row in results):
            print(json.dumps(results,ensure_ascii=False,indent=2),file=sys.stderr)
            return 2
    from src.analysis.pipeline import run
    manifest=run(output_root=args.output_root)
    regional=None
    regional_sigungu=None
    if not args.skip_regional_indicator:
        from src.analysis.regional_indicator_report import run as run_regional
        regional=run_regional(output_root=args.output_root)
        sigungu_input=ROOT/"data/processed/regional_2024/sigungu_2024_materials_verified.csv"
        if sigungu_input.exists():
            from src.analysis.sigungu_indicator_report import run as run_sigungu
            regional_sigungu=run_sigungu(output_root=args.output_root)
    print(json.dumps({"status":manifest["status"],"analysis_count":manifest["analysis_count"],
        "report":str(args.output_root/"reports/statistical_analysis/index.html"),
        "markdown":str(args.output_root/"reports/statistical_analysis/report.md"),
        "regional_indicator":str(args.output_root/"reports/regional_indicator/index.html") if regional else None,
        "regional_sigungu_indicator":str(args.output_root/"reports/regional_indicator_sigungu/index.html") if regional_sigungu else None},ensure_ascii=False,indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
