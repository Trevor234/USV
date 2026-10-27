#!/usr/bin/env python3
"""Check an immutable SIM_SHARED_SUPPORT asset declaration, without accepting it.

This checks auxiliary asset identity only. It does not replace F5 or validate a
complete simulation dependency graph, control behavior, or a release decision.
No expected value or filesystem asset is ever written by this module.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys


MANIFEST_SCHEMA = "sim-shared-support-asset-lock/v1"
RESULT_SCHEMA = "sim-shared-support-asset-check/v1"
SCOPE = "SIM_SHARED_SUPPORT"
KINDS = {"file", "directory", "symlink_file", "symlink_directory"}
ASSET_FIELDS = {"path", "type", "resolved_path", "link_target", "sha256"}
SHA_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


def sha_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def _native_identity(path):
    return os.path.normcase(os.path.normpath(str(path)))


def _stat_identity(value):
    # Exclude atime: reading a file may update it without changing its content.
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


def _validate_manifest(document):
    if not isinstance(document, dict):
        raise ValueError("Manifest must be a JSON object")
    required = {"schema", "scope", "version", "assets"}
    optional = {"metadata"}
    if not required <= set(document) or set(document) - required - optional:
        raise ValueError("Manifest fields must be schema, scope, version, assets, optional metadata")
    if document["schema"] != MANIFEST_SCHEMA or document["scope"] != SCOPE:
        raise ValueError("Unsupported schema or auxiliary scope")
    if not isinstance(document["version"], str) or not document["version"].strip():
        raise ValueError("Version must be a nonempty string")
    if "metadata" in document and not isinstance(document["metadata"], dict):
        raise ValueError("Optional metadata must be an object")
    assets = document["assets"]
    if not isinstance(assets, list) or not assets:
        raise ValueError("At least one explicitly declared asset is required")
    seen = set()
    for index, asset in enumerate(assets):
        if not isinstance(asset, dict) or set(asset) != ASSET_FIELDS:
            raise ValueError(f"Asset {index}: expected exactly {sorted(ASSET_FIELDS)}")
        if asset["type"] not in KINDS:
            raise ValueError(f"Asset {index}: unsupported type")
        for key in ("path", "resolved_path"):
            value = asset[key]
            if not isinstance(value, str) or not Path(value).is_absolute():
                raise ValueError(f"Asset {index}: {key} must be an absolute native path")
        identity = _native_identity(asset["path"])
        if identity in seen:
            raise ValueError(f"Asset {index}: duplicate path")
        seen.add(identity)
        if asset["type"].startswith("symlink_"):
            if not isinstance(asset["link_target"], str) or not asset["link_target"]:
                raise ValueError(f"Asset {index}: a raw nonempty link_target is required")
        elif asset["link_target"] is not None:
            raise ValueError(f"Asset {index}: non-link assets require link_target=null")
        if asset["type"].endswith("file"):
            if not isinstance(asset["sha256"], str) or not SHA_PATTERN.fullmatch(asset["sha256"]):
                raise ValueError(f"Asset {index}: file SHA256 must be 64 lowercase hex characters")
        elif asset["sha256"] is not None:
            raise ValueError(f"Asset {index}: directory SHA256 must be null")


def _failure(index, asset, code, **detail):
    return {"index": index, "path": asset["path"], "code": code, **detail}


def _observe_asset(index, asset):
    path = Path(asset["path"])
    failures = []
    try:
        first_lstat = path.lstat()
    except FileNotFoundError:
        return {"path": asset["path"], "exists": False}, [
            _failure(index, asset, "asset_missing")]
    except OSError as exc:
        return {"path": asset["path"], "exists": None}, [
            _failure(index, asset, "asset_read_error", detail=type(exc).__name__)]
    is_link = stat.S_ISLNK(first_lstat.st_mode)
    try:
        raw_target = os.readlink(path) if is_link else None
    except OSError as exc:
        return {"path": asset["path"], "exists": True}, [
            _failure(index, asset, "asset_read_error", detail=type(exc).__name__)]
    observed = {"path": asset["path"], "exists": True, "link_target": raw_target}
    try:
        first_stat = path.stat()
        resolved = str(path.resolve(strict=True))
    except FileNotFoundError:
        code = "asset_broken_symlink" if is_link else "asset_identity_unstable"
        observed.update({"type": "broken_symlink" if is_link else None,
                         "target_exists": False, "resolved_path": None})
        return observed, [_failure(index, asset, code)]
    except (OSError, RuntimeError) as exc:
        return observed, [_failure(index, asset, "asset_read_error", detail=type(exc).__name__)]
    if stat.S_ISREG(first_stat.st_mode):
        kind = "symlink_file" if is_link else "file"
    elif stat.S_ISDIR(first_stat.st_mode):
        kind = "symlink_directory" if is_link else "directory"
    else:
        kind = "unsupported"
    observed.update({"type": kind, "target_exists": True, "resolved_path": resolved,
                     "sha256": None})
    if kind != asset["type"]:
        failures.append(_failure(index, asset, "asset_type_mismatch",
                                 expected=asset["type"], actual=kind))
    if observed["link_target"] != asset["link_target"]:
        failures.append(_failure(index, asset, "asset_link_target_mismatch",
                                 expected=asset["link_target"], actual=observed["link_target"]))
    if _native_identity(resolved) != _native_identity(asset["resolved_path"]):
        failures.append(_failure(index, asset, "asset_resolved_path_mismatch",
                                 expected=asset["resolved_path"], actual=resolved))
    try:
        if kind.endswith("file"):
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                opened_stat = os.fstat(stream.fileno())
                if _stat_identity(first_stat) != _stat_identity(opened_stat):
                    failures.append(_failure(index, asset, "asset_identity_unstable"))
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
                closed_stat = os.fstat(stream.fileno())
            observed["sha256"] = digest.hexdigest()
            if observed["sha256"] != asset["sha256"]:
                failures.append(_failure(index, asset, "asset_sha256_mismatch",
                                         expected=asset["sha256"], actual=observed["sha256"]))
            if _stat_identity(opened_stat) != _stat_identity(closed_stat):
                failures.append(_failure(index, asset, "asset_identity_unstable"))
        last_lstat = path.lstat()
        last_stat = path.stat()
        last_target = os.readlink(path) if stat.S_ISLNK(last_lstat.st_mode) else None
        if (_stat_identity(first_lstat) != _stat_identity(last_lstat)
                or _stat_identity(first_stat) != _stat_identity(last_stat)
                or observed["link_target"] != last_target
                or _native_identity(path.resolve(strict=True)) != _native_identity(resolved)):
            failures.append(_failure(index, asset, "asset_identity_unstable"))
    except (OSError, RuntimeError) as exc:
        failures.append(_failure(index, asset, "asset_read_error", detail=type(exc).__name__))
    return observed, failures


def check_manifest(manifest_path, expected_manifest_sha256=None):
    """Return evidence only; never add assets, repair files, or update expected."""
    result = {
        "schema": RESULT_SCHEMA, "scope": SCOPE,
        "manifest_path": str(Path(manifest_path).absolute()),
        "manifest_sha256": None, "expected_manifest_sha256": expected_manifest_sha256,
        "version": None, "assets_count": 0, "support_assets_match": False,
        "observations": [], "failures": [],
        "limitations": ["auxiliary_asset_identity_only",
                        "not_full_simulation_dependency_lock", "not_F5_replacement",
                        "no_functional_or_release_acceptance"],
    }
    manifest_path = Path(manifest_path)
    try:
        raw = manifest_path.read_bytes()
        result["manifest_sha256"] = sha_bytes(raw)
        if expected_manifest_sha256 is not None:
            if not isinstance(expected_manifest_sha256, str) or not SHA_PATTERN.fullmatch(expected_manifest_sha256):
                raise ValueError("Caller expected manifest SHA256 must be lowercase hex")
            if result["manifest_sha256"] != expected_manifest_sha256:
                result["failures"].append({"code": "manifest_sha256_mismatch",
                                           "expected": expected_manifest_sha256,
                                           "actual": result["manifest_sha256"]})
        document = json.loads(raw.decode("utf-8-sig"))
        _validate_manifest(document)
        result["version"] = document["version"]
        result["assets_count"] = len(document["assets"])
    except (OSError, ValueError, UnicodeError, TypeError) as exc:
        result["failures"].append({"code": "manifest_invalid", "detail": str(exc)})
        return result
    for index, asset in enumerate(document["assets"]):
        observed, failures = _observe_asset(index, asset)
        result["observations"].append(observed)
        result["failures"].extend(failures)
    try:
        if manifest_path.read_bytes() != raw:
            result["failures"].append({"code": "manifest_changed_during_check"})
    except OSError as exc:
        result["failures"].append({"code": "manifest_changed_during_check",
                                   "detail": type(exc).__name__})
    result["support_assets_match"] = not result["failures"]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--expected-manifest-sha256", default=None)
    args = parser.parse_args()
    result = check_manifest(args.manifest, args.expected_manifest_sha256)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
    return 0 if result["support_assets_match"] else 1


if __name__ == "__main__":
    sys.exit(main())
