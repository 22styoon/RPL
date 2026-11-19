"""자치법규 후보의 기관명을 2024 MOIS 코드목록에 정확 연결한다."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.regional_data.policy_geography import link_ordinance_geography


def main():
    candidates_path = ROOT / "data/processed/regional_2024/policy_ordinance_candidates.csv"
    codes_path = ROOT / "data/processed/regional_2024/admin_codes_202412.csv"
    waste_path = ROOT / "data/processed/regional_2024/sigungu_2024_materials_verified.csv"
    if not all(path.exists() for path in (candidates_path, codes_path, waste_path)):
        print("먼저 조례 후보 수집과 지역자료 전처리를 완료하세요.", file=sys.stderr)
        return 2
    import pandas as pd
    candidates = pd.read_csv(candidates_path, dtype=str).fillna("")
    codes = pd.read_csv(codes_path, dtype=str).fillna("")
    waste = pd.read_csv(waste_path, dtype={"sigungu_code": str})
    linked, summary = link_ordinance_geography(candidates, codes, waste)
    output = ROOT / "data/processed/regional_2024/policy_ordinance_geography_crosswalk.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    linked.to_csv(output, index=False, encoding="utf-8-sig")
    summary_path = ROOT / "data/processed/regional_2024/policy_ordinance_candidate_summary.json"
    summary["crosswalk_csv"] = output.relative_to(ROOT).as_posix()
    api_manifest_path = ROOT / "data/raw/regional_2024/law_ordinances/latest.json"
    if api_manifest_path.exists():
        api_manifest = json.loads(api_manifest_path.read_text(encoding="utf-8"))
        summary.update({
            "law_api_status": api_manifest.get("status", "unknown"),
            "law_api_pages": api_manifest.get("pages_used", 0),
            "ordinance_detail_json_count": api_manifest.get("detail_count", 0),
            "ordinance_effective_date_filter": api_manifest.get("effective_date_filter", ""),
            "law_api_retrieved_at": api_manifest.get("retrieved_at", ""),
            "law_api_source_manifest": api_manifest_path.relative_to(ROOT).as_posix(),
        })
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
