#!/usr/bin/env python3
"""Publish or accept and verify the exact npm release artifact."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / ".build" / "release"
SLSA_PREDICATE = "https://slsa.dev/provenance/v1"


class PublicationError(Exception):
    """npm publication or verification failed closed."""


def request_json(url: str) -> dict[str, Any] | None:
    request = urllib.request.Request(url, headers={"User-Agent": "kisev-skills-release-check"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            value = json.loads(response.read())
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise PublicationError(f"registry returned HTTP {error.code}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise PublicationError(f"cannot read registry metadata: {error}") from error
    if not isinstance(value, dict):
        raise PublicationError("registry metadata is not an object")
    return value


def command(*arguments: str, cwd: Path = ROOT, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        list(arguments), cwd=cwd, env=env, capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise PublicationError(result.stderr.strip() or result.stdout.strip() or "command failed")
    return result.stdout


def require_trusted_publishing_npm() -> None:
    raw = command("npm", "--version").strip()
    try:
        version = tuple(int(part) for part in raw.split(".")[:3])
    except ValueError as error:
        raise PublicationError(f"npm returned an invalid version: {raw}") from error
    if len(version) != 3 or version < (11, 5, 1):
        raise PublicationError("npm 11.5.1 or newer is required for trusted publishing")


def manifest() -> tuple[dict[str, Any], Path]:
    try:
        value = json.loads((RELEASE / "release.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PublicationError(f"cannot read release manifest: {error}") from error
    if not isinstance(value, dict) or value.get("schema") != "@kisev/skills-release/v1":
        raise PublicationError("release manifest schema is invalid")
    npm = value.get("npm")
    if not isinstance(npm, dict) or not isinstance(npm.get("filename"), str):
        raise PublicationError("release manifest npm data is invalid")
    tarball = RELEASE / npm["filename"]
    content = tarball.read_bytes()
    integrity = "sha512-" + base64.b64encode(hashlib.sha512(content).digest()).decode("ascii")
    if (
        len(content) != npm.get("size")
        or hashlib.sha1(content).hexdigest() != npm.get("sha1")
        or hashlib.sha512(content).hexdigest() != npm.get("sha512")
        or integrity != npm.get("integrity")
    ):
        raise PublicationError("release tarball does not match its manifest")
    return value, tarball


def registry_url(name: str, version: str) -> str:
    registry = os.environ.get("NPM_CONFIG_REGISTRY", "https://registry.npmjs.org/").rstrip("/")
    return f"{registry}/{urllib.parse.quote(name, safe='')}/{urllib.parse.quote(version, safe='')}"


def wait_for_metadata(name: str, version: str, attempts: int = 24) -> dict[str, Any] | None:
    for attempt in range(attempts):
        result = request_json(registry_url(name, version))
        if result is not None:
            return result
        if attempt + 1 < attempts:
            time.sleep(5)
    return None


def verify_provenance(metadata: dict[str, Any], expected_sha512: str, revision: str) -> None:
    dist = metadata.get("dist")
    if not isinstance(dist, dict):
        raise PublicationError("npm distribution metadata is missing")
    attestations = dist.get("attestations")
    if not isinstance(attestations, dict) or not isinstance(attestations.get("url"), str):
        raise PublicationError("npm provenance metadata is missing")
    provenance = attestations.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("predicateType") != SLSA_PREDICATE:
        raise PublicationError("npm SLSA provenance declaration is invalid")
    document = request_json(attestations["url"])
    records = document.get("attestations") if document else None
    if not isinstance(records, list):
        raise PublicationError("npm attestations document is invalid")
    for record in records:
        if not isinstance(record, dict) or record.get("predicateType") != SLSA_PREDICATE:
            continue
        bundle = record.get("bundle")
        envelope = bundle.get("dsseEnvelope") if isinstance(bundle, dict) else None
        payload = envelope.get("payload") if isinstance(envelope, dict) else None
        if not isinstance(payload, str):
            continue
        try:
            statement = json.loads(base64.b64decode(payload, validate=True))
        except (ValueError, json.JSONDecodeError):
            continue
        subjects = statement.get("subject") if isinstance(statement, dict) else None
        predicate = statement.get("predicate") if isinstance(statement, dict) else None
        build = predicate.get("buildDefinition") if isinstance(predicate, dict) else None
        parameters = build.get("externalParameters") if isinstance(build, dict) else None
        workflow = parameters.get("workflow") if isinstance(parameters, dict) else None
        dependencies = build.get("resolvedDependencies") if isinstance(build, dict) else None
        subject_matches = isinstance(subjects, list) and any(
            isinstance(subject, dict)
            and isinstance(subject.get("digest"), dict)
            and subject["digest"].get("sha512") == expected_sha512
            for subject in subjects
        )
        workflow_matches = (
            isinstance(workflow, dict)
            and workflow.get("path") == ".github/workflows/publish.yml"
            and workflow.get("repository") == "https://github.com/kisev/skills"
        )
        revision_matches = isinstance(dependencies, list) and any(
            isinstance(dependency, dict)
            and isinstance(dependency.get("digest"), dict)
            and dependency["digest"].get("gitCommit") == revision
            for dependency in dependencies
        )
        if subject_matches and workflow_matches and revision_matches:
            return
    raise PublicationError("npm provenance does not bind the artifact, workflow, and revision")


def registry_smoke(name: str, version: str) -> None:
    with tempfile.TemporaryDirectory(prefix="skills-registry-smoke-") as temporary:
        root = Path(temporary)
        (root / "package.json").write_text('{"private":true}\n', encoding="utf-8")
        env = {**os.environ, "NPM_CONFIG_CACHE": str(root / "npm-cache")}
        command(
            "npm",
            "install",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
            f"{name}@{version}",
            "@opencode-ai/plugin@1.18.29",
            cwd=root,
            env=env,
        )
        command(
            "node",
            "--input-type=module",
            "--eval",
            "await import('@kisev/skills-opencode'); await import('@kisev/skills-opencode/plugins/rules-injector'); await import('@kisev/skills-opencode/plugins/rtk'); await import('@kisev/skills-opencode/plugins/zed-bell');",
            cwd=root,
            env=env,
        )
        executable = root / "node_modules" / ".bin" / "skills-opencode"
        if command(str(executable), "--version", cwd=root, env=env).strip() != version:
            raise PublicationError("installed npm CLI reports the wrong version")
        command(str(executable), "--help", cwd=root, env=env)
        capabilities = json.loads(
            command(str(executable), "capabilities", "--json", cwd=root, env=env)
        )
        if capabilities.get("status") != "ok" or capabilities.get("version") != version:
            raise PublicationError("installed npm CLI capabilities are invalid")
        command("npm", "audit", "signatures", "--json", cwd=root, env=env)


def publish() -> dict[str, Any]:
    require_trusted_publishing_npm()
    release, tarball = manifest()
    npm = release["npm"]
    name, version, revision = npm.get("name"), release.get("version"), release.get("revision")
    if not isinstance(name, str) or not name:
        raise PublicationError("release npm name is invalid")
    if not isinstance(version, str) or not version:
        raise PublicationError("release version is invalid")
    if not isinstance(revision, str) or not revision:
        raise PublicationError("release identity is invalid")
    metadata = wait_for_metadata(name, version, attempts=1)
    if metadata is None:
        try:
            command("npm", "publish", str(tarball), "--access", "public", "--provenance")
        except PublicationError:
            metadata = wait_for_metadata(name, version)
            if metadata is None:
                raise
        else:
            metadata = wait_for_metadata(name, version)
    if metadata is None:
        raise PublicationError("published npm metadata did not become available")
    dist = metadata.get("dist")
    if not isinstance(dist, dict) or dist.get("integrity") != npm.get("integrity"):
        raise PublicationError("registry npm artifact differs from the validated tarball")
    tarball_url = dist.get("tarball")
    if not isinstance(tarball_url, str):
        raise PublicationError("registry tarball URL is missing")
    with urllib.request.urlopen(tarball_url, timeout=30) as response:
        registry_content = response.read()
    if hashlib.sha512(registry_content).hexdigest() != npm.get("sha512"):
        raise PublicationError("downloaded registry tarball differs from the validated tarball")
    verify_provenance(metadata, str(npm["sha512"]), revision)
    registry_smoke(name, version)
    return metadata


def main() -> int:
    try:
        metadata = publish()
    except (PublicationError, OSError, ValueError, urllib.error.URLError) as error:
        raise SystemExit(str(error)) from error
    print(
        json.dumps({"status": "verified", "name": metadata["name"], "version": metadata["version"]})
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
