"""KOSIS·공식 2024 통계 원문을 추적 가능한 지역별 CSV로 정규화."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.regional_data.prepare import prepare

def main(argv=None):
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,"reconfigure"):stream.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description="2024 시도·시군구 실측 자료 정규화")
    parser.add_argument("--year",type=int,default=2024)
    args=parser.parse_args(argv)
    print(json.dumps(prepare(year=args.year),ensure_ascii=False,indent=2))
    return 0
if __name__=="__main__":raise SystemExit(main())
