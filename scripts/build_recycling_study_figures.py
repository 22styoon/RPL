"""Render the examples embedded in the research Markdown from saved inputs."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis.recycling_indicator_report import build_tables, save_static


EXAMPLES = (
    "swiss_stages",
    "nea_scope",
    "kosis_energy",
    "mass_flow",
    "composition_example",
    "weight_pair_counts",
    "time_methods",
    "partial_bounds",
    "regional_scores",
    "causal_dag",
)


def main():
    directory = ROOT / "docs" / "figures" / "recycling_indicator_study"
    directory.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as temporary:
        source_directory = Path(temporary)
        tables, *_ = build_tables(ROOT)
        save_static(tables, source_directory)
        for name in EXAMPLES:
            with Image.open(source_directory / f"{name}.png") as image:
                resized = image.convert("RGB")
                resized.thumbnail((1150, 900), Image.Resampling.LANCZOS)
                resized.quantize(colors=48, dither=Image.Dither.NONE).save(
                    directory / f"{name}.png", optimize=True
                )
    print(f"{len(EXAMPLES)} figures: {directory.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
