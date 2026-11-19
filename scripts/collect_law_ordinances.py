"""법제처 자치법규 연혁 검색 CLI. 검색 결과는 운영정책으로 자동 확정하지 않는다."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.regional_data.clients import load_law_oc
from src.regional_data.law_client import DEFAULT_KEYWORDS, collect_ordinances


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="법제처 2024년 자치법규 연혁 후보를 수집합니다. 인증값은 출력하지 않습니다.")
    parser.add_argument("--keyword", action="append", dest="keywords", help="자치법규명 검색어. 반복 지정 가능")
    parser.add_argument("--limit-pages", type=int, default=30, help="모든 검색어에 적용되는 전체 페이지 예산")
    parser.add_argument("--details", type=int, default=0, help="본문 원문을 추가로 받을 후보 수 (기본 0)")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--refresh", action="store_true", help="기존 실행 폴더를 재사용하지 않고 새 실행 생성")
    parser.add_argument("--dry-run", action="store_true", help="인증값 없이 검색 계획만 표시")
    args = parser.parse_args(argv)
    keywords = args.keywords or list(DEFAULT_KEYWORDS)
    if args.limit_pages < 1 or args.details < 0:
        parser.error("--limit-pages는 1 이상이고 --details는 0 이상이어야 합니다.")
    if args.dry_run:
        print(json.dumps({"source": "lawgo_ordinance_history", "keywords": keywords,
                          "effective_date_filter": "20240101~20241231", "history_mode": True,
                          "page_budget": args.limit_pages, "details_budget": args.details,
                          "network_requested": False}, ensure_ascii=False, indent=2))
        return 0
    try:
        load_law_oc()
        manifest = collect_ordinances(keywords=keywords, limit_pages=args.limit_pages,
                                      detail_budget=args.details, timeout=args.timeout, refresh=args.refresh)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    summary = {key: manifest[key] for key in ("status", "pages_used", "detail_count", "candidate_count", "candidate_csv")}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if manifest["status"] == "complete_within_page_budget" else 2


if __name__ == "__main__":
    raise SystemExit(main())
