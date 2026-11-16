"""공식 해외 데이터 수집. 정책 모형 설정에는 쓰지 않는다."""
import argparse,json
from importlib import import_module
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.model import ROOT
from src.external_data.common import ExternalDataError

def collect_many(names,root=ROOT,year=2024):
    results=[]
    for name in names:
        if name not in ("eurostat","nea","uk_waste","epa","oecd"):
            raise ValueError("등록하지 않은 해외 출처입니다.")
        module=import_module("src.external_data."+name)
        try:
            selected_year=2018 if name=="epa" else year
            result=module.collect(root=root,year=selected_year)
        except (ExternalDataError,ValueError,OSError) as error:
            result={"source_id":name,"status":"failed","error_type":type(error).__name__}
        results.append(result)
    return results

def main(argv=None):
    if hasattr(sys.stdout,"reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description="공식 해외 통계 원자료·SHA-256 보존")
    parser.add_argument("--sources",nargs="+",choices=["eurostat","nea","uk_waste","epa","oecd"],default=["eurostat","nea","epa"])
    parser.add_argument("--year",type=int,default=2024)
    parser.add_argument("--root",type=Path,default=ROOT)
    args=parser.parse_args(argv)
    results=collect_many(args.sources,args.root,args.year)
    print(json.dumps(results,ensure_ascii=False,indent=2))
    return int(any(row["status"]=="failed" for row in results))

if __name__=="__main__":
    raise SystemExit(main())
