"""Build the indicator research report using saved data, with no network calls."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.model import ROOT
from src.analysis.recycling_indicator_report import run


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="재활용 지표: 선행연구·정의 비교·실측/가상 그래프·인과 논증")
    parser.add_argument("--output-root", type=Path, default=ROOT / "outputs")
    args = parser.parse_args(argv)
    manifest = run(output_root=args.output_root)
    print(json.dumps({"status": manifest["status"], "report": str(args.output_root / "reports/recycling_indicator/index.html"),
                      **manifest["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
