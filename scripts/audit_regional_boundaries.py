"""행정안전부 2024 월별 시군구 코드로 지리키를 감사한다."""
import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.regional_data.boundary_audit import run_boundary_audit


def main(argv=None):
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,"reconfigure"):stream.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description="2024년 월별 공식 행정코드·통계 지리단위 일관성 감사")
    parser.add_argument("--timeout",type=int,default=30)
    parser.add_argument("--delay-seconds",type=float,default=.2)
    parser.add_argument("--max-pages-per-query",type=int,default=20)
    parser.add_argument("--refresh",action="store_true",help="모든 월별 API 페이지를 다시 요청합니다.")
    args=parser.parse_args(argv)
    result=run_boundary_audit(timeout=args.timeout,delay_seconds=args.delay_seconds,
                              max_pages_per_query=args.max_pages_per_query,refresh=args.refresh)
    print(json.dumps({"status":result["status"],"summary":result["summary"],"artifacts":result["artifacts"]},
                     ensure_ascii=False,indent=2))
    return 0 if result["status"]=="complete" else 2


if __name__=="__main__":raise SystemExit(main())
