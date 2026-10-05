"""CLI surface tests: commands, exit codes, and error mapping."""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from shopmatic.cli import main


def run_cli(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert "shopmatic" in capsys.readouterr().out


def test_no_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    code = main([])
    assert code == 2
    assert "usage" in capsys.readouterr().out.lower()


def test_search_command_prints_unified_json(
    capsys: pytest.CaptureFixture[str],
    fake_cli: Path,
) -> None:
    code, out, err = run_cli(
        capsys,
        "search",
        "wildberries",
        "клавиатура",
        "--max-price",
        "5000",
        "--limit",
        "5",
    )
    assert code == 0, err
    payload = json.loads(out)
    assert payload["schema"] == "kisev-skills/shopmatic-result/v1"
    assert payload["items"][0]["name"] == "Клавиатура тест"


def test_compare_command_lists_marketplaces(
    capsys: pytest.CaptureFixture[str],
    fake_cli: Path,
) -> None:
    code, out, _err = run_cli(capsys, "compare", "клавиатура", "--limit", "3")
    assert code == 0
    payload = json.loads(out)
    assert [entry["marketplace"] for entry in payload["comparisons"]] == [
        "wildberries",
        "yandex-market",
    ]


def test_blocked_marketplace_exit_code(
    capsys: pytest.CaptureFixture[str],
    fake_cli: Path,
) -> None:
    code, _out, err = run_cli(capsys, "search", "ozon", "клавиатура")
    assert code == 1
    assert "spike" in err


def test_product_command(
    capsys: pytest.CaptureFixture[str],
    fake_cli: Path,
) -> None:
    code, out, _err = run_cli(capsys, "product", "wildberries", "123")
    assert code == 0
    payload = json.loads(out)
    assert payload["kind"] == "product"


def test_login_command_creates_profile(
    capsys: pytest.CaptureFixture[str],
    fake_cli: Path,
    fake_environment: Path,
) -> None:
    code, out, _err = run_cli(capsys, "login", "wildberries")
    assert code == 0
    assert str(fake_environment / "accounts" / "wildberries") in out


def test_invalid_limit_maps_to_exit_two(
    capsys: pytest.CaptureFixture[str],
    fake_cli: Path,
) -> None:
    code, _out, err = run_cli(
        capsys,
        "search",
        "wildberries",
        "клавиатура",
        "--limit",
        "99",
    )
    assert code == 2
    assert "limit" in err


def test_unknown_marketplace_choice_is_argparse_error() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["search", "avito", "query"])
    assert excinfo.value.code == 2


def test_serve_subcommand_uses_stdio_loop(
    fake_browser: Path,
    fake_environment: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shopmatic.server import serve

    request_line = (
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/list",
            }
        )
        + "\n"
    )
    output_stream = io.StringIO()
    monkeypatch.setattr("sys.stdin", io.StringIO(request_line))
    monkeypatch.setattr("sys.stdout", output_stream)
    code = serve()
    assert code == 0
    payload = json.loads(output_stream.getvalue().splitlines()[0])
    assert payload["id"] == 7
    assert payload["result"]["tools"]
