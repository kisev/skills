from __future__ import annotations

import json
from typing import Any

import pytest

from scripts import check_npm_audit


def _report(vulnerabilities: dict[str, Any]) -> dict[str, Any]:
    return {"vulnerabilities": vulnerabilities, "metadata": {"vulnerabilities": {}}}


ACKNOWLEDGED = "https://github.com/advisories/GHSA-cccccccccccc"
UNKNOWN = "https://github.com/advisories/GHSA-aaaaaaaaaaaa"

FAKE_ACKNOWLEDGEMENTS = {"GHSA-cccccccccccc": "synthetic acknowledged advisory for the gate tests"}


def test_cascade_references_do_not_create_advisories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(check_npm_audit, "ADVISORY_ACKNOWLEDGEMENTS", FAKE_ACKNOWLEDGEMENTS)
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
    assert acknowledged == {"GHSA-cccccccccccc": ["http-cache-semantics"]}


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
    monkeypatch.setattr(check_npm_audit, "ADVISORY_ACKNOWLEDGEMENTS", FAKE_ACKNOWLEDGEMENTS)
    monkeypatch.setattr(check_npm_audit, "ADVISORY_ACKNOWLEDGEMENTS", FAKE_ACKNOWLEDGEMENTS)
    exit_code = check_npm_audit.main(["--prefix", "apps/docs-site"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "acknowledged GHSA-cccccccccccc" in captured.out
    assert "synthetic acknowledged advisory" in captured.out
