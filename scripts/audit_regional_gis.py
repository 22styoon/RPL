"""Check a local 2024 GIS boundary snapshot against the current MOIS audit."""

import argparse
import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.regional_data.gis_boundary import assess_gis_boundary, propose_gis_crosswalk


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="2024년 기준일 GIS 경계 도형 감사")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--manifest", type=Path, help="경계 출처·대응표·파일 지문 JSON 경로")
    mode.add_argument("--propose-crosswalk", type=Path, help="경계 파일의 정식 명칭으로 검토용 대응표를 제안합니다.")
    parser.add_argument("--compare-manifest", type=Path, help="다른 기준일의 같은 경계 시리즈를 비교하는 출처 JSON 경로")
    parser.add_argument("--crosswalk-output", type=Path, help="검토용 대응표를 쓸 새 CSV 파일 경로")
    parser.add_argument("--code-namespace", choices=("sgis", "mois"), default="sgis")
    parser.add_argument("--code-field", default="ADM_CD")
    parser.add_argument("--name-field", default="ADM_NM")
    parser.add_argument("--date-field", default="BASE_DATE")
    parser.add_argument("--encoding", help="원본 SHP의 DBF 인코딩")
    args = parser.parse_args(argv)
    if args.propose_crosswalk is not None:
        if args.compare_manifest is not None:
            parser.error("--propose-crosswalk와 --compare-manifest는 함께 사용할 수 없습니다.")
        try:
            rows = propose_gis_crosswalk(ROOT, args.propose_crosswalk, code_namespace=args.code_namespace,
                                        code_field=args.code_field, name_field=args.name_field,
                                        date_field=args.date_field, encoding=args.encoding)
            if args.crosswalk_output is not None:
                with args.crosswalk_output.open("x", encoding="utf-8-sig", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)
        except (ImportError, OSError, ValueError) as exc:
            print(json.dumps({"status": "crosswalk_proposal_unavailable", "reason": str(exc)}, ensure_ascii=False, indent=2))
            return 2
        result = {"status": "crosswalk_proposed_for_review", "row_count": len(rows), "reference_date": rows[0]["reference_date"]}
        if args.crosswalk_output is None:
            result["proposed_rows"] = rows
        else:
            result["crosswalk_file"] = str(args.crosswalk_output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.crosswalk_output is not None:
        parser.error("--crosswalk-output은 --propose-crosswalk에 사용합니다.")
    result = assess_gis_boundary(ROOT, manifest_path=args.manifest, compare_manifest_path=args.compare_manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    comparison = result["comparison"]
    return 0 if result["verified"] and (comparison is None or comparison["verified"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
