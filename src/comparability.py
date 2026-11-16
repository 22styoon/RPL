"""정의가 확인된 지표만 비교한다. 출처 이름만으로 호환성을 추정하지 않는다."""
from math import isfinite

DIMENSIONS=("year","waste_scope","material","process_stage","numerator_definition","denominator_definition","mass_unit","geography_level")
MASS_FACTORS={"t":1.0,"metric_tonne":1.0,"US short ton":0.90718474,"kg":0.001,"1000 tonnes":1000.0}

def convert_mass(value,source_unit,target_unit="t"):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not isfinite(value):
        raise ValueError("유한한 질량 수치가 필요합니다.")
    if source_unit not in MASS_FACTORS or target_unit not in MASS_FACTORS:
        raise ValueError("검증된 질량 단위가 아닙니다.")
    return value*MASS_FACTORS[source_unit]/MASS_FACTORS[target_unit]

def assess_comparability(left,right,*,monetary=False,purpose="cross_country"):
    reasons=[]
    fields=(*DIMENSIONS,*(("currency","price_year") if monetary else ()))
    for field in fields:
        a,b=left.get(field),right.get(field)
        if a is None or b is None or a=="" or b=="":
            reasons.append(field+":missing")
        elif a!=b:
            reasons.append(field+":different")
    if purpose=="korean_model_input" and right.get("country")!="KR":
        reasons.append("foreign_value_is_not_korean_observation")
    return {"compatible":not reasons,"reasons":reasons,"purpose":purpose}
