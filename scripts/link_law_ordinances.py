"""자치법규 원문과 조문을 검증하고 2024 MOIS 기관명과 연결한다."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.regional_data.ordinance_evidence import link_ordinance_evidence, assess_ordinance_linkage


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="법령 후보·원문·조문 위치와 2024 지역 코드 연결")
    parser.add_argument("--check-only", action="store_true", help="현재 원문·입력 연결을 로컬에서 확인합니다. 수집·파일 수정은 하지 않습니다.")
    args = parser.parse_args(argv)
    if args.check_only:
        assessment = assess_ordinance_linkage(ROOT)
        print(json.dumps(assessment, ensure_ascii=False, indent=2))
        return 0 if assessment["verified"] else 2
    candidates_path = ROOT / "data/processed/regional_2024/policy_ordinance_candidates.csv"
    codes_path = ROOT / "data/processed/regional_2024/admin_codes_202412.csv"
    waste_path = ROOT / "data/processed/regional_2024/sigungu_2024_materials_verified.csv"
    if not all(path.exists() for path in (candidates_path, codes_path, waste_path)):
        print("먼저 조례 후보 수집과 지역자료 전처리를 완료하세요.", file=sys.stderr)
        return 2
    try:
        summary = link_ordinance_evidence(ROOT)
    except (ValueError, OSError, KeyError):
        print("법령 연결 실패: 원문·후보·지역 입력을 확인하고 수집 및 전처리를 다시 실행하세요.", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
