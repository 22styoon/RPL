"""공공데이터포털 수집 CLI. 실행 전 --dry-run으로 요청 계획을 확인한다."""
import argparse
from datetime import date
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.model import ROOT
from src.public_data.client import PublicDataClient, PublicDataError, MissingServiceKey, load_service_key
from src.public_data.collector import build_queries, collect_dataset, CollectionFailure


def parser():
    result = argparse.ArgumentParser(description="처리시설 명부·나라장터 용역계약 수집 (모형 단가 자동 변경 없음)")
    result.add_argument("--dataset",choices=["facilities","contracts","all"],required=True)
    dates = result.add_argument_group("계약 등록·변경·삭제 조회일 (실제 서비스 연도와 다름)")
    dates.add_argument("--year",type=int,help="조회일 연도. --begin/--end와 함께 사용할 수 없음")
    dates.add_argument("--begin",type=date.fromisoformat)
    dates.add_argument("--end",type=date.fromisoformat)
    result.add_argument("--limit-pages",type=int,default=1,help="전체 데이터셋·기간·operation에 걸친 페이지 예산 (기본 1)")
    result.add_argument("--page-size",type=int,default=100)
    result.add_argument("--format",choices=["json","xml"],default="json")
    result.add_argument("--region",help="로컬 검색어. 계약은 제목/기관명 검색이며 실제 처리지역으로 확정하지 않음")
    result.add_argument("--operation",action="append",help="데이터셋의 정확한 operation 이름. 반복 지정 가능")
    result.add_argument("--output-root",type=Path,default=ROOT)
    result.add_argument("--dry-run",action="store_true",help="키 없이 계획만 표시 (호출·파일 저장 없음)")
    return result


def main(argv=None):
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,"reconfigure"):
            stream.reconfigure(encoding="utf-8")
    command = parser()
    args = command.parse_args(argv)
    try:
        if args.year is not None and (args.begin or args.end):
            raise ValueError("--year 또는 --begin/--end 중 하나만 지정하세요.")
        begin,end = args.begin,args.end
        if args.year is not None:
            begin,end = date(args.year,1,1),date(args.year,12,31)
        if args.limit_pages < 1:
            raise ValueError("--limit-pages는 1 이상입니다.")
        datasets = ["facilities","contracts"] if args.dataset=="all" else [args.dataset]
        plans = {name:build_queries(name,begin,end,args.page_size,args.format,args.operation) for name in datasets}
        if args.dry_run:
            print(json.dumps({"limit_pages_global":args.limit_pages,"plan":plans},ensure_ascii=False,indent=2))
            return 0
        remaining = args.limit_pages
        reports = []
        for name in datasets:
            if remaining <= 0:
                reports.append({"dataset":name,"status":"not_started","reason":"global_page_budget_exhausted"})
                continue
            try:
                key = load_service_key(name="JODAL") if name=="contracts" else load_service_key()
            except MissingServiceKey:
                key = load_service_key()
            client = PublicDataClient(key)
            manifest = collect_dataset(name,client=client,begin=begin,end=end,limit_pages=remaining,
                page_size=args.page_size,response_format=args.format,region=args.region,
                output_root=args.output_root,operations=args.operation)
            remaining -= len(manifest["pages"])
            reports.append({key:manifest[key] for key in ("dataset","status","complete","record_count","candidate_count","normalized_path")})
        print(json.dumps(reports,ensure_ascii=False,indent=2))
        return 0
    except CollectionFailure as error:
        print(str(error),file=sys.stderr)
        return 2
    except (PublicDataError,ValueError,TypeError) as error:
        print(str(error),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
