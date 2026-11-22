"""The audit CLI distinguishes a completed audit from current input validity."""
import json
from unittest.mock import Mock

import pytest

from scripts import audit_regional_boundaries as cli


@pytest.mark.parametrize("status,verified,expected", [
    ("complete", True, 0),
    ("complete", False, 2),
    ("review_required", True, 2),
])
def test_normal_audit_reports_current_assessment_and_requires_both_successes(
        monkeypatch, capsys, status, verified, expected):
    historical = {"status": status, "summary": {"month_count": 12},
                  "artifacts": {"monthly": "monthly.csv"}}
    current = {"status": "code_name_roster_stable" if verified else "input_changed",
               "verified": verified, "reasons": [] if verified else ["selected_december_roster_changed"]}
    run = Mock(return_value=historical)
    assess = Mock(return_value=current)
    monkeypatch.setattr(cli, "run_boundary_audit", run)
    monkeypatch.setattr(cli, "assess_boundary_audit", assess)

    assert cli.main(["--timeout", "15", "--delay-seconds", "0", "--max-pages-per-query", "7", "--refresh"]) == expected

    assert json.loads(capsys.readouterr().out) == dict(historical, current_input_assessment=current)
    run.assert_called_once_with(timeout=15, delay_seconds=0, max_pages_per_query=7, refresh=True)
    assess.assert_called_once_with(cli.ROOT)


@pytest.mark.parametrize("verified,expected", [(True, 0), (False, 2)])
def test_check_only_never_runs_audit(monkeypatch, capsys, verified, expected):
    current = {"status": "code_name_roster_stable" if verified else "evidence_missing",
               "verified": verified, "reasons": []}
    run = Mock(side_effect=AssertionError("check-only must not run the network-capable audit"))
    assess = Mock(return_value=current)
    monkeypatch.setattr(cli, "run_boundary_audit", run)
    monkeypatch.setattr(cli, "assess_boundary_audit", assess)

    assert cli.main(["--check-only"]) == expected

    assert json.loads(capsys.readouterr().out) == current
    run.assert_not_called()
    assess.assert_called_once_with(cli.ROOT)
