from __future__ import annotations

import json
from typing import Any

import pytest

from scripts import check_npm_audit


def _report(vulnerabilities: dict[str, Any]) -> dict[str, Any]:
    return {"vulnerabilities": vulnerabilities, "metadata": {"vulnerabilities": {}}}


ACKNOWLEDGED = "https://github.com/advisories/GHSA-ch52-4w7c-c8xp"
UNKNOWN = "https://github.com/advisories/GHSA-aaaaaaaaaaaa"


def test_cascade_references_do_not_create_advisories() -> None:
    report = _report(
        {
            "http-cache-semantics": {
                "severity": "high",
                "via": [{"title": "cache disclosure", "url": ACKNOWLEDGED}],
            },
            "make-fetch-happen": {"severity": "high", "via": ["http-cache-semantics"]},
        }
    )
    acknowledged, unknown = check_npm_audit.evaluate(report)
    assert unknown == []
    assert acknowledged == {"GHSA-ch52-4w7c-c8xp": ["http-cache-semantics"]}


def test_unknown_advisory_is_reported_as_failure() -> None:
    report = _report({"left-pad": {"severity": "high", "via": [{"url": UNKNOWN}]}})
    acknowledged, unknown = check_npm_audit.evaluate(report)
    assert acknowledged == {}
    assert unknown == ["GHSA-aaaaaaaaaaaa"]


def test_malformed_advisory_url_fails_closed() -> None:
    report = _report({"left-pad": {"severity": "high", "via": [{"url": "https://example.test"}]}})
    with pytest.raises(check_npm_audit.AuditError, match="no GHSA url"):
        check_npm_audit.evaluate(report)


def test_missing_vulnerabilities_object_fails_closed() -> None:
    with pytest.raises(check_npm_audit.AuditError, match="vulnerabilities object"):
        check_npm_audit.evaluate({"metadata": {}})


def test_main_fails_for_unknown_advisory(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        check_npm_audit,
        "run_npm_audit",
        lambda prefix: json.loads(json.dumps(_report({"left-pad": {"via": [{"url": UNKNOWN}]}}))),
    )
    exit_code = check_npm_audit.main([])
    assert exit_code == 1
    assert "unacknowledged advisory GHSA-aaaaaaaaaaaa" in capsys.readouterr().err


def test_main_accepts_acknowledged_advisory(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        check_npm_audit,
        "run_npm_audit",
        lambda prefix: _report({"http-cache-semantics": {"via": [{"url": ACKNOWLEDGED}]}}),
    )
    exit_code = check_npm_audit.main(["--prefix", "apps/docs-site"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "acknowledged GHSA-ch52-4w7c-c8xp" in captured.out
    assert "no patched version exists upstream" in captured.out
