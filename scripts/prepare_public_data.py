"""보존된 API 공개 응답으로 정규화·비용 후보를 재생성한다."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.model import ROOT
from src.public_data.collector import prepare_saved_run


def main(argv=None):
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,"reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="서비스키·네트워크 없이 저장한 수집 결과 재처리")
    parser.add_argument("manifest",type=Path)
    parser.add_argument("--output-root",type=Path,default=ROOT)
    args = parser.parse_args(argv)
    try:
        print(prepare_saved_run(args.manifest,output_root=args.output_root))
        return 0
    except (ValueError,KeyError,OSError) as error:
        print("재처리 실패: "+type(error).__name__+" (manifest와 보존본을 확인하세요)",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
