"""2024년 지역 폐기물 통계 원문·행정코드 자료 수집 CLI."""
import argparse, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.regional_data.clients import collect_file, collect_mois, load_mois_key

SOURCES=("kr_waste_2024_detail","kr_admin_codes_2024")

def main(argv=None):
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,"reconfigure"):stream.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description="공식 2024 지역 폐기물 자료를 수집합니다. 인증값은 출력하지 않습니다.")
    parser.add_argument("--source",required=True,choices=SOURCES)
    parser.add_argument("--year",type=int,default=2024)
    parser.add_argument("--region")
    parser.add_argument("--dry-run",action="store_true")
    parser.add_argument("--refresh",action="store_true")
    parser.add_argument("--page-budget",type=int,default=20)
    parser.add_argument("--timeout",type=int,default=30)
    parser.add_argument("--resume",action="store_true")
    args=parser.parse_args(argv)
    if args.dry_run:
        configured=True
        if args.source=="kr_admin_codes_2024":
            try:load_mois_key()
            except ValueError:configured=False
        print(json.dumps({"source":args.source,"year":args.year,"dry_run":True,
                          "credential_configured":configured if args.source=="kr_admin_codes_2024" else None,
                          "network_requested":False},ensure_ascii=False,indent=2))
        return 0 if configured else 2
    if args.source=="kr_admin_codes_2024":
        state=collect_mois(year=args.year,page_budget=args.page_budget,timeout=args.timeout,resume=args.resume,refresh=args.refresh,region=args.region)
        summary={k:state.get(k) for k in ("source_id","reference_year","reference_month","completeness","retrieved_at")}
        summary["record_count"]=len(state.get("records",[]));summary["completed_roots"]=len(state.get("completed_roots",[]))
    else:
        state=collect_file(args.source,year=args.year,refresh=args.refresh,resume=args.resume,timeout=args.timeout,page_budget=args.page_budget,region=args.region)
        summary={k:state.get(k) for k in ("source_id","reference_year","completeness","bytes","raw_file","sha256","failure_reason")}
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return 0 if summary.get("completeness") in ("complete","archive_received") else 2

if __name__=="__main__":raise SystemExit(main())
