#!/usr/bin/env python3
"""
Canonical integrity checker.

This is the single source of truth for validation logic. Both the positive
check (test.yml, against committed files) and the negative-test workflow
(test-negative.yml, against mutated scratch copies) must call this exact
script — never a reimplementation.

Usage:
    python3 check.py <target_dir>

<target_dir> must contain:
    sample-a.manifest.json
    sample-a.json  (or whatever files the manifest's "fixtures" keys name)

Exit code 0 = all checks passed.
Exit code 1 = one or more checks failed; failure reasons are printed to stdout,
               prefixed by FIXTURE_INTEGRITY_FAILURE.
Exit code 2 = invalid command-line usage.

Stable named failure reasons:
    malformed_manifest
    manifest_is_empty
    missing_fixture
    sha256_mismatch
    target_dir_not_found
"""

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Optional

SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
failures: list[str] = []


def fail(message: str) -> None:
    failures.append(message)


def sha256_of_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(target_dir: Path) -> Optional[dict]:
    manifest_path = target_dir / "sample-a.manifest.json"

    try:
        raw = manifest_path.read_bytes()
    except OSError as exc:
        fail(f"malformed_manifest: cannot read manifest ({exc})")
        return None

    try:
        manifest = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        fail(f"malformed_manifest: invalid JSON ({exc})")
        return None

    if not isinstance(manifest, dict):
        fail("malformed_manifest: manifest root must be an object")
        return None

    return manifest


def resolve_fixture_path(target_dir: Path, name: object) -> Optional[Path]:
    if not isinstance(name, str) or not name:
        fail("malformed_manifest: fixture name must be a non-empty string")
        return None

    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        fail(f"malformed_manifest: unsafe fixture path '{name}'")
        return None

    resolved = (target_dir / relative).resolve()

    try:
        resolved.relative_to(target_dir)
    except ValueError:
        fail(f"malformed_manifest: fixture path escapes target directory '{name}'")
        return None

    return resolved


def validate(target_dir: Path) -> None:
    manifest = load_manifest(target_dir)
    if manifest is None:
        return

    fixtures = manifest.get("fixtures")
    if not isinstance(fixtures, dict) or not fixtures:
        fail("manifest_is_empty")
        return

    for name, entry in fixtures.items():
        if not isinstance(entry, dict):
            fail(f"malformed_manifest: entry for '{name}' is not an object")
            continue

        expected = entry.get("sha256")
        if not isinstance(expected, str) or not SHA256_PATTERN.fullmatch(expected):
            fail(f"malformed_manifest: missing or invalid sha256 for '{name}'")
            continue

        fixture_path = resolve_fixture_path(target_dir, name)
        if fixture_path is None:
            continue

        if not fixture_path.is_file():
            fail(f"missing_fixture: {name}")
            continue

        try:
            actual = sha256_of_file(fixture_path)
        except OSError as exc:
            fail(f"missing_fixture: {name} ({exc})")
            continue

        if actual != expected.lower():
            fail(f"sha256_mismatch: {name} expected={expected} actual={actual}")


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python3 check.py <target_dir>")
        sys.exit(2)

    target_dir = Path(sys.argv[1]).resolve()

    if not target_dir.is_dir():
        print("FIXTURE_INTEGRITY_FAILURE:")
        print(f"- target_dir_not_found: {target_dir}")
        sys.exit(1)

    validate(target_dir)

    if failures:
        print("FIXTURE_INTEGRITY_FAILURE:")
        for failure in failures:
            print(f"- {failure}")
        sys.exit(1)

    print("fixture_integrity: all checks passed")
    sys.exit(0)


if __name__ == "__main__":
    main()
