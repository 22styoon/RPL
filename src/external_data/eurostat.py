"""Eurostat 공식 Statistics API JSON-stat 2.0, env_wasmun."""
from itertools import product
import json
import math
from urllib.parse import urlencode
from .common import ExternalDataError,fetch,metadata,save_records

PAGE="https://ec.europa.eu/eurostat/databrowser/view/env_wasmun/default/table"
API="https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/env_wasmun"

def normalize(payload,meta):
    if payload.get("class")!="dataset":
        raise ExternalDataError("Eurostat JSON-stat dataset가 아닙니다.")
    ids,sizes=payload["id"],payload["size"]
    if len(ids)!=len(sizes) or not {"geo","time","unit","wst_oper"}<=set(ids) or math.prod(sizes)>300000:
        raise ExternalDataError("검증되지 않은 차원 또는 과대한 통계 큐브입니다.")
    axes=[]
    for name,size in zip(ids,sizes):
        cat=payload["dimension"][name]["category"]
        index=cat["index"]
        if isinstance(index,dict) and set(index.values())!=set(range(size)):
            raise ExternalDataError("차원 인덱스가 연속된 위치가 아닙니다.")
        order=list(index) if isinstance(index,list) else sorted(index,key=index.get)
        if len(order)!=size:
            raise ExternalDataError("차원 크기가 맞지 않습니다.")
        axes.append(order)
    values,statuses=payload.get("value",{}),payload.get("status",{})
    def cell(obj,index):
        if isinstance(obj,list):
            return obj[index] if index<len(obj) else None
        return obj.get(str(index))
    rows=[]
    for offset,coords in enumerate(product(*axes)):
        codes=dict(zip(ids,coords))
        raw=cell(values,offset)
        flag=cell(statuses,offset)
        if raw is not None and (isinstance(raw,bool) or not isinstance(raw,(int,float)) or not math.isfinite(raw) or raw<0):
            raise ExternalDataError("잘못된 Eurostat 수치입니다.")
        unit=codes["unit"]
        value=None if raw is None else (raw*1000 if unit=="THS_T" else raw)
        label=lambda dim:payload["dimension"][dim]["category"].get("label",{}).get(codes[dim],codes[dim])
        rows.append(metadata(meta,country=codes["geo"],geography=label("geo"),year=int(codes["time"]),
            waste_scope="Eurostat municipal waste; national reporting definitions",material="전체",
            process_stage=label("wst_oper"),numerator_definition=label("wst_oper"),
            denominator_definition="inhabitants" if unit=="KG_HAB" else "annual municipal waste mass",
            metric=codes["wst_oper"],metric_label=label("wst_oper"),
            value=value,unit="t/year" if unit=="THS_T" else unit,mass_unit="kg/inhabitant" if unit=="KG_HAB" else "t",
            raw_value=raw,raw_unit=unit,status_flag=flag,source_locator="env_wasmun JSON-stat "+str(offset),
            measurement_type="official_estimate" if flag and "e" in flag else "official_statistic",
            comparability_flag="within_source_caution",missing=raw is None))
    return rows

def collect(*,root,year=2024):
    url=API+"?"+urlencode(dict(lang="EN",time=year,geoLevel="country"))
    raw,meta=fetch("eurostat",url,f"env_wasmun_{year}.json",root=root,
                   license="Eurostat reuse with attribution; dataset notes apply",redistribution="attribution_required")
    return save_records(normalize(json.loads(raw),meta),meta,root=root)
