"""JSON and exit-code contract shared by portable skill runners."""

from __future__ import annotations

import argparse
import json
import sys
from typing import NoReturn

ERROR_EXIT_CODE = 2
ESCALATE_EXIT_CODE = 3


def report_error(code: str, message: str, *, retryable: bool = False) -> None:
    """Emit an expected failure as JSON and explain it on stderr."""
    print(
        json.dumps(
            {
                "status": "error",
                "error": {
                    "code": code,
                    "message": message,
                    "retryable": retryable,
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    print(message, file=sys.stderr)


def emit_escalation(reason: str, details: dict[str, object]) -> NoReturn:
    """Emit an unavailable or out-of-scope outcome and stop."""
    print(
        json.dumps(
            {"status": "escalate", "reason": reason, "details": details},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    print(reason, file=sys.stderr)
    raise SystemExit(ESCALATE_EXIT_CODE)


class ContractArgumentParser(argparse.ArgumentParser):
    """Keep argument errors on the same JSON contract as runner failures."""

    def add_subparsers(
        self, **kwargs: object
    ) -> argparse._SubParsersAction[argparse.ArgumentParser]:
        kwargs.setdefault("parser_class", type(self))
        return super().add_subparsers(**kwargs)

    def error(self, message: str) -> NoReturn:
        report_error("invalid_arguments", message)
        raise SystemExit(ERROR_EXIT_CODE)
