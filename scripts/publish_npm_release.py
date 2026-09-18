#!/usr/bin/env python3
"""Publish or accept and verify the exact npm release artifact."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, TypeVar

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / ".build" / "release"
SLSA_PREDICATE = "https://slsa.dev/provenance/v1"
PROPAGATION_SECONDS = 600
PROPAGATION_ATTEMPTS = 60
T = TypeVar("T")


class PublicationError(Exception):
    """npm publication or verification failed closed."""


class RegistryPending(PublicationError):
    """A read-only registry request can be retried."""


def wait_for_registry(
    stage: str,
    read: Callable[[], T | None],
    attempts: int,
    delay: float,
    deadline: float | None = None,
) -> T | None:
    end = deadline if deadline is not None else time.monotonic() + PROPAGATION_SECONDS
    last_error: RegistryPending | None = None
    for attempt in range(max(attempts, 1)):
        if time.monotonic() >= end:
            break
        try:
            result = read()
            last_error = None
            if result is not None:
                return result
        except RegistryPending as error:
            last_error = error
        remaining = end - time.monotonic()
        if attempt + 1 >= attempts or remaining <= 0:
            break
        pause = min(delay * 2 ** min(attempt, 4), 30, remaining)
        print(
            f"npm {stage}: waiting for registry propagation (attempt {attempt + 1}, "
            f"retry in {pause:g}s, {remaining:.0f}s remaining)",
            file=sys.stderr,
            flush=True,
        )
        time.sleep(pause)
    if last_error is not None:
        raise PublicationError(
            f"npm {stage}: transient registry errors exhausted the wait budget"
        ) from last_error
    return None


def request_json(url: str) -> dict[str, Any] | None:
    request = urllib.request.Request(url, headers={"User-Agent": "kisev-skills-release-check"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            value = json.loads(response.read())
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        if error.code in {408, 429} or 500 <= error.code < 600:
            raise RegistryPending(f"registry returned HTTP {error.code}") from error
        raise PublicationError(f"registry returned HTTP {error.code}") from error
    except (OSError, urllib.error.URLError) as error:
        raise RegistryPending("registry metadata transport error") from error
    except json.JSONDecodeError as error:
        raise PublicationError("registry metadata is not valid JSON") from error
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


def wait_for_metadata(
    name: str,
    version: str,
    attempts: int = PROPAGATION_ATTEMPTS,
    *,
    deadline: float | None = None,
) -> dict[str, Any] | None:
    return wait_for_registry(
        "metadata", lambda: request_json(registry_url(name, version)), attempts, 5, deadline
    )


def download_registry_tarball(
    url: str,
    attempts: int = PROPAGATION_ATTEMPTS,
    delay: float = 5,
    *,
    deadline: float | None = None,
) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "kisev-skills-release-check"})

    def read() -> bytes | None:
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                content = response.read()
                if not isinstance(content, bytes):
                    raise PublicationError("registry tarball response is invalid")
                return content
        except urllib.error.HTTPError as error:
            if error.code not in {404, 408, 429} and error.code < 500:
                raise PublicationError(f"registry tarball returned HTTP {error.code}") from error
            raise RegistryPending(f"registry tarball returned HTTP {error.code}") from error
        except (OSError, urllib.error.URLError):
            raise RegistryPending("registry tarball transport error") from None

    content = wait_for_registry("tarball", read, attempts, delay, deadline)
    if content is None:
        raise PublicationError("registry tarball did not become available")
    return content


def provenance_matches(document: dict[str, Any], expected_sha512: str, revision: str) -> bool:
    records = document.get("attestations") if document else None
    if not isinstance(records, list):
        return False
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
            return True
    return False


def verify_provenance(
    metadata: dict[str, Any],
    expected_sha512: str,
    revision: str,
    attempts: int = PROPAGATION_ATTEMPTS,
    delay: float = 5,
    *,
    deadline: float | None = None,
    metadata_url: str | None = None,
) -> None:
    def read() -> bool | None:
        nonlocal metadata
        dist = metadata.get("dist")
        if not isinstance(dist, dict):
            raise PublicationError("npm distribution metadata is missing")
        attestations = dist.get("attestations")
        if attestations is None and metadata_url is not None:
            refreshed = request_json(metadata_url)
            if refreshed is not None:
                if refreshed.get("dist", {}).get("integrity") != dist.get("integrity"):
                    raise PublicationError(
                        "registry integrity changed while waiting for provenance"
                    )
                metadata = refreshed
            return None
        if not isinstance(attestations, dict) or not isinstance(attestations.get("url"), str):
            raise PublicationError("npm provenance metadata is missing")
        provenance = attestations.get("provenance")
        if not isinstance(provenance, dict) or provenance.get("predicateType") != SLSA_PREDICATE:
            raise PublicationError("npm SLSA provenance declaration is invalid")
        document = request_json(attestations["url"])
        if document is None:
            return None
        if not provenance_matches(document, expected_sha512, revision):
            raise PublicationError(
                "npm provenance does not bind the artifact, workflow, and revision"
            )
        return True

    if wait_for_registry("provenance", read, attempts, delay, deadline):
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
    deadline = time.monotonic() + PROPAGATION_SECONDS

    def probe() -> tuple[dict[str, Any] | None]:
        # A definite 404 permits the single publish. Transport failure never does.
        return (request_json(registry_url(name, version)),)

    observed = wait_for_registry("version lookup", probe, PROPAGATION_ATTEMPTS, 5, deadline)
    if observed is None:
        raise PublicationError("could not establish whether the npm version already exists")
    metadata = observed[0]
    if metadata is None:
        try:
            command("npm", "publish", str(tarball), "--access", "public", "--provenance")
        except PublicationError:
            metadata = wait_for_metadata(name, version, deadline=deadline)
            if metadata is None:
                raise
        else:
            metadata = wait_for_metadata(name, version, deadline=deadline)
    if metadata is None:
        raise PublicationError("published npm metadata did not become available")
    dist = metadata.get("dist")
    if not isinstance(dist, dict) or dist.get("integrity") != npm.get("integrity"):
        raise PublicationError("registry npm artifact differs from the validated tarball")
    tarball_url = dist.get("tarball")
    if not isinstance(tarball_url, str):
        raise PublicationError("registry tarball URL is missing")
    registry_content = download_registry_tarball(tarball_url, deadline=deadline)
    if hashlib.sha512(registry_content).hexdigest() != npm.get("sha512"):
        raise PublicationError("downloaded registry tarball differs from the validated tarball")
    verify_provenance(
        metadata,
        str(npm["sha512"]),
        revision,
        deadline=deadline,
        metadata_url=registry_url(name, version),
    )
    registry_smoke(name, version)
    return metadata


def main() -> int:
    try:
        metadata = publish()
    except (PublicationError, OSError, ValueError, urllib.error.URLError) as error:
        raise SystemExit(
            f"{error}\nInspect the release run before retrying. For propagation failures, "
            "rerun failed jobs with the retained exact artifacts. Do not republish or move the tag."
        ) from error
    print(
        json.dumps({"status": "verified", "name": metadata["name"], "version": metadata["version"]})
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
