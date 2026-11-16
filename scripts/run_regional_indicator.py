"""2024 시도 표준화 지표 및 검증 보고서를 오프라인 재생성."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.analysis.regional_indicator_report import run

def main(argv=None):
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,"reconfigure"):stream.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description="R/S 표준화 지표·기여도·가중치 민감도·회귀진단 생성")
    parser.add_argument("--year",type=int,default=2024)
    parser.add_argument("--level",choices=("sido","sigungu"),default="sido")
    parser.add_argument("--output-root",type=Path,default=ROOT/"outputs")
    args=parser.parse_args(argv)
    if args.year!=2024:parser.error("현재 검증된 원자료는 2024년입니다.")
    if args.level=="sido":
        result=run(output_root=args.output_root)
        report="reports/regional_indicator"
    else:
        from src.analysis.sigungu_indicator_report import run as run_sigungu
        result=run_sigungu(output_root=args.output_root)
        report="reports/regional_indicator_sigungu"
    print(json.dumps({"status":result["status"],"summary":result["summary"],
        "html":str(args.output_root/report/"index.html"),
        "markdown":str(args.output_root/report/"report.md")},ensure_ascii=False,indent=2))
    return 0
if __name__=="__main__":raise SystemExit(main())
