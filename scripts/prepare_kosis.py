"""저장된 KOSIS 원표/메타데이터로 지역·품목 집계를 재현한다."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.kosis_analysis import process_saved_table, display_materials

if __name__ == "__main__":
    frame, materials = process_saved_table()
    print("KOSIS 원표", len(frame), "행 계층 복원 완료")
    print(display_materials(materials.loc[materials.geography == "전국", ["material","generated_t","material_recycling_t"]]).to_string(index=False))
