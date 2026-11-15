"""KOSIS 인증키를 출력하지 않는 수집 명령."""
import argparse
import sys
from src.kosis import KosisError, load_api_key, load_tables, collect_table, fetch_metadata

def main():
    parser = argparse.ArgumentParser(description="KOSIS 생활폐기물 통계 수집")
    parser.add_argument("--metadata", action="store_true", help="분류·항목 메타데이터만 조회")
    parser.add_argument("--public-summary", action="store_true", help="인증키 없이 공개 전국 지표만 수집")
    args = parser.parse_args()
    try:
        if args.public_summary:
            from src.kosis_public import collect_public_summary
            frame = collect_public_summary()
            print("KOSIS 공개 전국 지표", len(frame), "개 시점 저장")
            return 0
        key = load_api_key()
        for table in load_tables():
            if args.metadata:
                rows = fetch_metadata(table, key)
                print(table["name"], "분류·항목", len(rows), "개 저장")
            else:
                frame = collect_table(table, key)
                print(table["name"], table["year"], "년", len(frame), "행 저장")
    except KosisError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
