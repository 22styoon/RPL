"""Display program performance and GIS evidence alongside regional outcomes."""
from hashlib import sha256
from html import escape

from .gis_boundary import assess_gis_boundary
from .operating_policy import load_operating_policy_evidence

POLICY_CONFIG = "configs/regional_operating_policy_evidence_2024.yaml"
POLICY_TABLES = (
    "operating_policy_performance",
    "operating_policy_household_join_exclusions",
)
TITLE = "운영정책과 자체 성과"
POLICY_SCOPE = (
    "사업 참여 매장의 판매·반환 집계입니다. 시군구 전체 연간 생활폐기물 "
    "물질재활용 처리량과는 대상, 기간, 단위가 달라 별도 집계합니다. "
    "아래 컵 수량은 공표치의 만 개 단위를 개수로 표시합니다."
)
DISPLAY_FIELDS = {
    "policy_name": "정책",
    "geography": "지역",
    "period_start": "집계 시작일",
    "period_end": "집계 종료일",
    "cups_sold": "판매량(개)",
    "cups_returned": "반환량(개)",
    "cup_return_rate_percent": "반환율(%)",
}


def program_evidence(root):
    path = root / POLICY_CONFIG
    return load_operating_policy_evidence(path) if path.is_file() else None


def program_summary(evidence):
    return {
        "operating_policy_verified_count": len(evidence.policies) if evidence else 0,
        "operating_policy_performance_rows": len(evidence.performance) if evidence else 0,
    }


def program_display(evidence):
    return evidence.performance[list(DISPLAY_FIELDS)].rename(columns=DISPLAY_FIELDS)


def write_program_tables(evidence, directory):
    frames = dict(zip(POLICY_TABLES, (evidence.performance, evidence.household_join_exclusions)))
    for name, frame in frames.items():
        frame.to_csv(directory / f"{name}.csv", index=False, encoding="utf-8-sig")
    return frames


def gis_note(gis):
    if gis["verified"]:
        summary = gis["summary"]
        return (
            f"GIS {summary['reference_date']} 자료에서 "
            f"{summary['statistical_unit_count']}개 통계단위의 도형을 확인했습니다. "
            "기준일의 도형과 통계지역 대응을 다룹니다."
        )
    if gis["status"] == "source_pending":
        return "공식 2024년 GIS 도형 원본과 기준일 정보 확보가 필요합니다."
    return "GIS 검증 보류 (" + gis["status"] + "). " + " / ".join(gis["reasons"])


def followup_report(root, tables, summary, files):
    """Expose results and CSV lineage in both offline report formats."""
    evidence = program_evidence(root)
    gis = assess_gis_boundary(root)
    summary.update(program_summary(evidence))
    summary["gis_boundary_status"] = gis["status"]
    summary["gis_boundary_verified"] = gis["verified"]
    summary["gis_boundary_summary"] = gis.get("summary", {})
    summary["gis_boundary_reasons"] = gis["reasons"]
    markdown = [f"\n## GIS 경계\n\n{gis_note(gis)}\n"]
    section = f"<section><h2>GIS 경계</h2><p>{escape(gis_note(gis))}</p></section>"
    if evidence is None:
        return markdown, section

    source_bytes = (root / POLICY_CONFIG).read_bytes()
    summary["source_files"][POLICY_CONFIG] = {"sha256": sha256(source_bytes).hexdigest(), "bytes": len(source_bytes)}
    files.update(write_program_tables(evidence, tables))

    link_prefix = f"../../tables/{tables.name}"
    labels = ("사업 자체 성과 CSV", "생활폐기물 결합 보류 사유 CSV")
    links = [(label, f"{link_prefix}/{name}.csv") for label, name in zip(labels, POLICY_TABLES)]
    display = program_display(evidence)
    header = "| " + " | ".join(display.columns) + " |"
    divider = "| " + " | ".join("---" for _ in display.columns) + " |"
    rows = ["| " + " | ".join(str(value).replace("|", "&#124;") for value in row) + " |"
            for row in display.itertuples(index=False, name=None)]
    markdown.extend([
        f"\n## {TITLE}\n\n{POLICY_SCOPE}\n",
        "\n".join([header, divider, *rows]) + "\n",
        " · ".join(f"[{label}]({url})" for label, url in links) + "\n",
    ])
    html_links = " · ".join(f'<a href="{url}">{label}</a>' for label, url in links)
    section += (
        f"<section><h2>{TITLE}</h2><p>{POLICY_SCOPE}</p>"
        f"{display.to_html(index=False)}<p>{html_links}</p></section>"
    )
    return markdown, section
