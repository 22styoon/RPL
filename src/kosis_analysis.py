"""KOSIS 메타데이터의 부모 코드를 이용한 계층 복원과 중복 없는 품목 집계."""
import json
from pathlib import Path
import pandas as pd
from src.kosis import KosisError
from src.model import ROOT

TABLE_ID = "DT_106N_29_2020005"
MATERIALS = {
    "폐지류": {"폐지류"},
    "폐합성수지류": {"폐합성수지류"},
    "폐금속류": {"폐금속류", "고철류", "금속캔"},
    "폐유리류": {"폐유리류", "폐유리병류"},
}
ROUTES = ("종량제방식 등 혼합배출", "재활용 가능자원 분리배출")
METHODS = {"10001":"generated_t", "10003":"recycling_total_t", "10004":"incinerated_t",
           "10005":"landfilled_t", "10006":"other_t", "10008":"material_recycling_t", "10009":"energy_recovery_t"}

def classification_paths(metadata, dimension):
    index = {r["ITM_ID"]: r for r in metadata if str(r.get("OBJ_ID_SN", "")) == str(dimension)}
    def path(code):
        chain, seen = [], set()
        while code:
            if code in seen or code not in index:
                raise KosisError("분류 계층에 순환 또는 누락된 부모 코드가 있습니다.")
            seen.add(code)
            row = index[code]
            chain.append(row)
            code = row.get("UP_ITM_ID")
        return list(reversed(chain))
    return {code: path(code) for code in index}

def annotate_classifications(frame, metadata):
    output = frame.copy()
    paths_1, paths_2 = classification_paths(metadata, 1), classification_paths(metadata, 2)
    for dimension, paths in ((1, paths_1), (2, paths_2)):
        column = f"class_{dimension}_id"
        if column not in frame or not set(frame[column]).issubset(paths):
            raise KosisError("관측 분류와 메타데이터가 일치하지 않습니다.")
        output[f"class_{dimension}_path"] = frame[column].map(
            lambda code: " > ".join(r["ITM_NM"] for r in paths[code]))
    output["geography"] = frame.class_1_id.map(lambda code: paths_1[code][0]["ITM_NM"])
    output["emission_route"] = frame.class_1_id.map(lambda code: paths_1[code][1]["ITM_NM"] if len(paths_1[code]) > 1 else "지역 계층")
    output["processing_method"] = frame.class_2_id.map(
        lambda code: "재활용 소계(물질+에너지)" if paths_2[code][-1]["ITM_NM"] == "소계"
        and any(r["ITM_NM"] == "재활용" for r in paths_2[code]) else paths_2[code][-1]["ITM_NM"])
    return output

def aggregate_materials(frame, metadata):
    if set(frame.table_id) != {TABLE_ID} or set(frame.unit) != {"톤/년"} or frame.reference_year.astype(str).nunique() != 1:
        raise KosisError("집계 대상 통계표·단위·연도가 일치하지 않습니다.")
    if frame.duplicated(["class_1_id", "class_2_id", "reference_year"]).any():
        raise KosisError("원표 관측 셀이 중복되었습니다.")
    paths = classification_paths(metadata, 1)
    groups = {}
    for code in frame.class_1_id.unique():
        chain = paths[code]
        if len(chain) < 3 or chain[1]["ITM_NM"] not in ROUTES:
            continue
        labels = {r["ITM_NM"] for r in chain[2:]}
        for material, aliases in MATERIALS.items():
            if labels & aliases:
                key = (chain[0]["ITM_NM"], chain[1]["ITM_NM"], material)
                groups.setdefault(key, set()).add(code)
    rows = []
    for (region, route, material), candidates in groups.items():
        # 관측된 상위 품목이 존재하면 하위 품목을 다시 더하지 않는다.
        selected = {code for code in candidates if not any(
            r["ITM_ID"] in candidates for r in paths[code][:-1])}
        sample = frame.loc[frame.class_1_id.isin(selected)]
        record = dict(geography=region, emission_route=route, material=material,
                      reference_year=str(frame.reference_year.iloc[0]), unit="톤/년",
                      source_codes=";".join(sorted(selected)), evidence_grade="A",
                      source_url=frame.source_url.iloc[0], source_title=frame.source_title.iloc[0],
                      retrieved_at=frame.retrieved_at.iloc[0],
                      waste_scope="원표 대응 4품목의 파생그룹; 영농·복합제품 재질은 제외",
                      transformation="지역·배출방식별 대응 품목 중 관측 상위행 또는 그 하위 관측잎만 합산")
        for suffix, name in METHODS.items():
            cells = sample.loc[sample.class_2_id == "13102134417T." + suffix, "value"]
            if len(cells) != len(selected):
                raise KosisError("처리방법별 집계에 필요한 관측 셀이 누락되었습니다.")
            values = pd.to_numeric(cells, errors="coerce")
            record[name] = values.sum(min_count=len(selected))
        rows.append(record)
    if not rows:
        raise KosisError("집계할 대응 품목이 없습니다.")
    detail = pd.DataFrame(rows)
    combined = []
    for (region, material), group in detail.groupby(["geography", "material"], sort=False):
        if set(group.emission_route) != set(ROUTES):
            raise KosisError("대응 품목의 두 배출방식 중 하나가 누락되었습니다.")
        row = group.iloc[0].to_dict()
        row["emission_route"] = "혼합배출 + 재활용 가능자원 분리배출"
        row["source_codes"] = ";".join(group.source_codes)
        for name in METHODS.values():
            row[name] = group[name].sum(min_count=len(group))
        row["material_treatment_rate_pct"] = 100 * row["material_recycling_t"] / row["generated_t"] if row["generated_t"] > 0 else None
        combined.append(row)
    return detail, pd.DataFrame(combined)

def process_saved_table(table_id=TABLE_ID, year="2024", root=ROOT):
    root = Path(root)
    metadata = json.loads((root/f"data/raw/kosis/{table_id}_metadata.json").read_text(encoding="utf-8-sig"))
    path = root/f"data/processed/kosis/{table_id}_{year}.csv"
    frame = pd.read_csv(path, dtype={"class_1_id":str,"class_2_id":str,"item_id":str,"reference_year":str})
    frame = annotate_classifications(frame, metadata)
    detail, combined = aggregate_materials(frame, metadata)
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    detail.to_csv(root/f"data/processed/kosis_material_routes_{year}.csv", index=False, encoding="utf-8-sig")
    combined.to_csv(root/f"data/processed/kosis_materials_{year}.csv", index=False, encoding="utf-8-sig")
    output = root / "outputs/tables"
    output.mkdir(parents=True, exist_ok=True)
    display_materials(combined).to_csv(output/f"kosis_materials_{year}.csv", index=False, encoding="utf-8-sig")
    display_materials(detail).to_csv(output/f"kosis_material_routes_{year}.csv", index=False, encoding="utf-8-sig")
    return frame, combined

def display_materials(frame):
    labels = {"geography":"지역", "emission_route":"배출방식", "material":"품목 그룹",
              "reference_year":"기준연도", "generated_t":"발생량(톤/년)",
              "material_recycling_t":"물질재활용 처리량(톤/년)", "energy_recovery_t":"에너지회수(톤/년)",
              "recycling_total_t":"재활용 소계(물질+에너지)(톤/년)", "incinerated_t":"소각(톤/년)",
              "landfilled_t":"매립(톤/년)", "other_t":"기타 처리(톤/년)",
              "material_treatment_rate_pct":"물질재활용 처리비율(%)", "unit":"단위",
              "source_codes":"합산한 원표 코드", "evidence_grade":"근거등급", "source_url":"KOSIS 원표",
              "source_title":"통계표명", "retrieved_at":"수집일", "waste_scope":"대상 범위",
              "transformation":"집계 방식"}
    return frame.rename(columns=labels)
