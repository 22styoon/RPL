"""검증된 정책만 실측자료와 엄격 결합; 추정 정책은 입력하지 않음."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.regional_data.prepare import prepare
from src.regional_data.followup_reporting import program_evidence, program_summary, write_program_tables

def main(argv=None):
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,"reconfigure"):stream.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description="정책 후보 CSV를 재검증하여 2024 실측자료와 결합")
    parser.add_argument("--year",type=int,default=2024)
    args=parser.parse_args(argv)
    result=prepare(year=args.year)
    evidence = program_evidence(ROOT)
    if evidence is not None:
        write_program_tables(evidence, ROOT / "data/processed/regional_2024")
    print(json.dumps({"year":args.year,"policy_candidates":result["policy_candidates"],
        "verified_policy_rows":result["policy_verified_rows"],"verified_join_rows":result["verified_join_rows"],
        **program_summary(evidence),
        "join_csv":"data/processed/regional_2024/sigungu_2024_policy_material_join_verified.csv",
        "exclusions_csv":"data/processed/regional_2024/join_exclusions.csv"},ensure_ascii=False,indent=2))
    return 0
if __name__=="__main__":raise SystemExit(main())
