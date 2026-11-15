from pathlib import Path
from src.model import load_config, compare, sensitivity, best

def main():
    config = load_config()
    output = Path(__file__).resolve().parent / 'outputs/tables'
    output.mkdir(parents=True, exist_ok=True)
    table = compare(config)
    table.to_csv(output / 'scenarios.csv', index=False, encoding='utf-8-sig')
    sensitivity(config).to_csv(output / 'sensitivity.csv', index=False, encoding='utf-8-sig')
    print('SYNTHETIC ASSUMPTIONS ONLY; conditional finite-scenario optimum:', best(table))
    print(table[['id', 'final_rate', 'social_cost', 'feasible']].to_string(index=False))

if __name__ == '__main__':
    main()
