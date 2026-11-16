import numpy as np
import pandas as pd
from .common import AnalysisResult,require_unique,require_numeric

PATHS={"material_recycling_t":"물질재활용","energy_recovery_t":"에너지회수","incinerated_t":"소각","landfilled_t":"매립","other_t":"기타"}

def material_composition(frame,region="전국"):
    require_unique(frame,["geography","material","reference_year"])
    data=frame.loc[frame.geography==region].copy()
    if len(data)!=4:
        raise ValueError("검증된 대응 4품목만 분석합니다.")
    require_numeric(data,["generated_t",*PATHS])
    residual=data.generated_t-data[list(PATHS)].sum(axis=1)
    if (residual.abs()>0.6).any() or (data.generated_t<=0).any():
        raise ValueError("상호 배타 처리경로와 발생량의 수지를 확인하세요.")
    rows=[]
    for row in data.to_dict("records"):
        for field,label in PATHS.items():
            rows.append({"품목":row["material"],"처리경로":label,"처리량(t/년)":row[field],
                         "발생량(t/년)":row["generated_t"],"처리경로 비중(%)":row[field]/row["generated_t"]*100})
    table=pd.DataFrame(rows)
    return AnalysisResult("material_composition","지역·재질별 비교","4품목의 처리경로 구성",
        "종이·플라스틱·금속·유리의 물질재활용·에너지회수·처분 구성은 어떻게 다른가?",
        table,table,"stacked","품목","처리경로 비중(%)","처리경로","%","2024",
        sorted(set(data.source_url)),f"전국 대응 4품목 발생량 {data.generated_t.sum():,.1f}t 중 물질재활용 처리량 {data.material_recycling_t.sum():,.1f}t이다.",
        ["물질재활용 처리량은 최종 재생원료 생산량이 아니다.","에너지회수와 소각을 다른 원표 경로로 보존한다. 총 재활용 항목을 다시 더하지 않는다.","원표 반올림에 의한 수지 오차를 보존한다."],
        "src/analysis/composition.py",extra={"max_balance_error_t":float(residual.abs().max())})
