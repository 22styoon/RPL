"""가구별 반복 관측을 먼저 평균한 탐색적 시간 분석. 문헌 평균으로 표본을 만들지 않는다."""
import numpy as np
import pandas as pd
FIELDS=["cleaning_minutes","sorting_minutes","storage_minutes","walking_minutes"]

def summarize_diary(frame,*,seed=20261116,bootstrap_samples=2000):
    required=["household_id","week",*FIELDS]
    if not set(required)<=set(frame):
        raise ValueError("가구 ID·주차·작업별 시간 열이 필요합니다.")
    if frame.duplicated(["household_id","week"]).any():
        raise ValueError("가구·주차 중복 행을 먼저 정리하세요.")
    data=frame.copy()
    for field in FIELDS:
        data[field]=pd.to_numeric(data[field],errors="raise")
        if ((data[field]<0)|(~np.isfinite(data[field])&data[field].notna())).any():
            raise ValueError("시간은 유한한 0 이상 수치여야 합니다.")
    complete=data[["household_id","week",*FIELDS]].dropna()
    if complete.empty:
        return {"status":"자료 미확보","households":0,"excluded_rows":len(frame),"mean":None,"median":None,"ci95":None}
    complete=complete.assign(total_minutes=complete[FIELDS].sum(axis=1))
    by_household=complete.groupby("household_id").total_minutes.mean()
    ci=None
    if len(by_household)>=20:
        rng=np.random.default_rng(seed)
        bootstrap=np.mean(rng.choice(by_household.to_numpy(),size=(bootstrap_samples,len(by_household)),replace=True),axis=1)
        ci=[float(x) for x in np.quantile(bootstrap,[.025,.975])]
    return {"status":"탐색 표본","households":len(by_household),"excluded_rows":len(frame)-len(complete),
            "mean":float(by_household.mean()),"median":float(by_household.median()),"ci95":ci,"seed":seed,
            "limitation":"가구 단위 재표집. 대표성·정책 전후 인과효과를 주장하지 않음."}
