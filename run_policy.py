"""KOSIS 지역별 조건부 실험을 한글 표와 실행 스냅샷으로 저장한다."""
import argparse
from pathlib import Path
import json
from src.national_policy import (load_policy_config, compare_policies, selected_policy,
    target_curve, sensitivity, input_snapshot, export_bundle, translate_table, default_curve_targets)

def main():
    parser = argparse.ArgumentParser(description="KOSIS 기반 지역별 조건부 정책 실험")
    parser.add_argument("--config", type=Path, help="단가·효과·제약을 지정한 YAML")
    parser.add_argument("--region", help="전국 또는 KOSIS 시도명")
    parser.add_argument("--target", type=float, help="최소 가정 최종 전환비율, 0~1")
    parser.add_argument("--budget", type=float, help="연간 공공지출 상한, 원")
    parser.add_argument("--capacity", type=float, help="물질재활용 처리 용량, 톤/년")
    parser.add_argument("--scan-adoption", action="store_true", help="25·50·75·100% 도입비중 탐색")
    parser.add_argument("--output", type=Path, help="결과 저장 폴더")
    args = parser.parse_args()
    config = load_policy_config(args.config)
    if args.region is not None:
        config["region"] = args.region
    for value, key in ((args.target,"minimum_final_rate"),(args.budget,"annual_public_budget"),(args.capacity,"material_capacity_t")):
        if value is not None:
            config["constraints"][key] = value
    if args.scan_adoption:
        config["scan_adoption"] = True
    try:
        results, flows = compare_policies(config)
        curve = target_curve(config, default_curve_targets(config, results))
        experiments = sensitivity(config)
        snapshot = input_snapshot(config)
        output = args.output or Path(__file__).resolve().parent/"outputs/policy_runs/latest"
        output.mkdir(parents=True, exist_ok=True)
        for name, frame in (("policy_results.csv",results),("material_flows.csv",flows),
                            ("target_curve.csv",curve),("sensitivity.csv",experiments)):
            translate_table(frame).to_csv(output/name, index=False, encoding="utf-8-sig")
        (output/"inputs.json").write_text(json.dumps(snapshot,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
        (output/"policy_run.zip").write_bytes(export_bundle(config,results,flows))
    except (ValueError,KeyError) as error:
        parser.error(str(error))
    print("KOSIS 지역:",config["region"],"연도:",config["reference_year"])
    print("조건부 최소비용안:",selected_policy(results) or "비용 입력 또는 조건 충족 대안 필요")
    print(translate_table(results[["policy_id","final_rate","comparison_cost","costs_complete","feasible","rejection_reasons"]]).to_string(index=False))
    print("저장 위치:",output)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
