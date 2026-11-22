"""The CLI cannot turn failed local source verification into a successful link."""
import pytest

from scripts import link_law_ordinances as cli


@pytest.mark.parametrize("verified,expected", [(True, 0), (False, 2)])
def test_check_only_never_builds_or_fetches_evidence(monkeypatch, verified, expected, capsys):
    monkeypatch.setattr(cli, "assess_ordinance_linkage", lambda root: {
        "verified": verified, "status": "source_and_geography_bound" if verified else "input_changed"})
    def disallowed(*args, **kwargs):
        raise AssertionError("check-only attempted to rebuild")
    monkeypatch.setattr(cli, "link_ordinance_evidence", disallowed)
    assert cli.main(["--check-only"]) == expected
    assert '"verified"' in capsys.readouterr().out


def test_invalid_source_fails_link_with_safe_error(tmp_path, monkeypatch, capsys):
    directory = tmp_path / "data/processed/regional_2024"
    directory.mkdir(parents=True)
    for name in ("policy_ordinance_candidates.csv", "admin_codes_202412.csv", "sigungu_2024_materials_verified.csv"):
        (directory / name).write_text("fixture", encoding="utf-8")
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    def invalid(root):
        raise ValueError("LAW_COLLECTION_CANDIDATE_HASH_MISMATCH")
    monkeypatch.setattr(cli, "link_ordinance_evidence", invalid)
    assert cli.main([]) == 2
    assert "법령 연결 실패" in capsys.readouterr().err
