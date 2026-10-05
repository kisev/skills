"""Configure the fixture-bound shell Runner during env:gitlab:up, never in tests."""

from __future__ import annotations

import json

from tests.integration.gitlab.scripts.stand import Stand, write_json


def runner(stand: Stand) -> bool:
    path = stand.state / "runner.json"
    if path.is_symlink():
        raise RuntimeError("Runner credentials must not be symlinks")
    if path.exists():
        identity = json.loads(path.read_text())
    else:
        identity = stand.request(
            "POST",
            "/user/runners",
            {
                "runner_type": "project_type",
                "project_id": stand.manifest["fixtures"]["id"],
                "description": "Owned shell harness",
                "run_untagged": True,
                "locked": True,
            },
        )
        write_json(path, identity)
    config = f"""concurrent = 2
check_interval = 1
[[runners]]
  name = "Owned shell harness"
  url = "http://gitlab"
  token = {json.dumps(identity["token"])}
  executor = "shell"
  clone_url = "http://gitlab"
  builds_dir = "/home/gitlab-runner/builds"
"""
    current = stand.docker(
        "exec",
        "-T",
        "runner",
        "sh",
        "-c",
        "if test -f /etc/gitlab-runner/config.toml; then cat /etc/gitlab-runner/config.toml; fi",
    )
    if current == config:
        return False
    stand.docker(
        "exec",
        "-T",
        "runner",
        "sh",
        "-c",
        "umask 077; cat > /etc/gitlab-runner/config.toml",
        data=config,
    )
    return True
