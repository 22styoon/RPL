from dataclasses import dataclass,field
import pandas as pd

@dataclass
class AnalysisResult:
    analysis_id:str
    category:str
    title:str
    question:str
    table:pd.DataFrame
    plot:pd.DataFrame
    kind:str
    x:str
    y:str
    series:str|None
    unit:str
    year_label:str
    sources:list[str]
    interpretation:str
    limitations:list[str]
    code_source:str
    measurement_type:str="관측 행정통계"
    extra:dict=field(default_factory=dict)

def require_unique(frame,keys):
    if frame.duplicated(keys).any():
        raise ValueError("중복 관측 키: "+", ".join(keys))

def require_numeric(frame,columns,*,allow_missing=False):
    import numpy as np
    for column in columns:
        values=pd.to_numeric(frame[column],errors="raise")
        if ((values<0)|(~np.isfinite(values)&values.notna())).any() or (not allow_missing and values.isna().any()):
            raise ValueError(column+": 음수·비유한 수치·미입력을 확인하세요.")
