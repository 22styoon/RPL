from pathlib import Path
from src.model import load_config, compare, sensitivity, best, evaluate
from src.presentation import korean_table
from src.provenance import inputs_table

def main():
    config = load_config()
    output = Path(__file__).resolve().parent / "outputs/tables"
    output.mkdir(parents=True, exist_ok=True)
    table = compare(config)
    for filename, frame in (("scenarios.csv", table), ("sensitivity.csv", sensitivity(config)),
                            ("input_evidence.csv", inputs_table(config))):
        korean_table(frame).to_csv(output / filename, index=False, encoding="utf-8-sig")
    for scenario in config["scenarios"]:
        _, flow = evaluate(config, scenario)
        korean_table(flow).to_csv(output / f"mass_balance_{scenario['id']}.csv", index=False, encoding="utf-8-sig")
    print("구로구 2024 공식 실적 보정 / 최종 수율·대안 효과는 가정")
    print("총사회적 비용이 아닌, 공공예산 대리값과 추가 투자 연간화의 조건부 비교입니다.")
    print("등록 대안 중 조건부 최소비용안:", best(table))
    print(korean_table(table[["id", "sorting_rate", "final_rate", "comparison_cost", "feasible"]]).to_string(index=False))

if __name__ == "__main__":
    main()
