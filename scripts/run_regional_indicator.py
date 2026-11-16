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
    parser.add_argument("--level",choices=("sido",),default="sido")
    parser.add_argument("--output-root",type=Path,default=ROOT/"outputs")
    args=parser.parse_args(argv)
    if args.year!=2024:parser.error("현재 검증된 원자료는 2024년입니다.")
    result=run(output_root=args.output_root)
    print(json.dumps({"status":result["status"],"summary":result["summary"],
        "html":str(args.output_root/"reports/regional_indicator/index.html"),
        "markdown":str(args.output_root/"reports/regional_indicator/report.md")},ensure_ascii=False,indent=2))
    return 0
if __name__=="__main__":raise SystemExit(main())
