from pathlib import Path
from src.model import ROOT
import yaml
def sources():
    return yaml.safe_load((ROOT/"configs/regional_recycling_sources.yaml").read_text(encoding="utf-8"))["sources"]
