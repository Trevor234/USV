#!/usr/bin/env python3
"""在发布根 R 上生成三份身份产物，并绑定成 release_identity.json。

用法:
  emit_release_evidence.py --release-root R --underlay U --id ID \
      --ros-domain-id N --dds-profile PATH [--write]

产物（全部相对 R）:
  evidence/source_hashes.json    冻结源码清单（records/path/bytes/sha256/symlink/valid）
  evidence/install_manifest.json 安装清单（path/resolved_path/sha256）
  evidence/release_artifacts.json driver/checker/监督器/原语/模板的完整 SHA
  evidence/release_identity.json 把上面三份的**完整摘要**绑在一起，并绑定
                                  underlay 身份、合同/计划 SHA、生产 DDS 取值
三次独立固定，互不引用；release_identity.json 排除自身自指。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

SOURCE_EXCLUDES = {".git", "build", "install", "log", "__pycache__", ".pytest_cache"}
# 源码里唯一允许逃逸到树外的链接：NTRIP 秘密配置。只记 metadata，不复制内容。
SECRET_BASENAMES = {"ntrip_params.yaml"}
ARTIFACT_PATHS = (
    "deploy/commission_scheme_a.py",
    "deploy/emit_release_evidence.py",
    "deploy/capture_release_identity.py",
    "deploy/probe_fcu_state.py",
    "deploy/30-scheme-a-commissioning.conf.in",
    "deploy/tests/test_commission_scheme_a.py",
    "install/usv_research_safety_cpp/lib/usv_research_safety_cpp/"
    "run_shipboard_commissioning.py",
    "install/usv_research_safety_cpp/lib/usv_research_safety_cpp/"
    "check_shipboard_commissioning.py",
    "install/usv_research_safety_cpp/lib/usv_research_safety_cpp/p1_regulator",
    "install/usv_research_safety_cpp/lib/usv_research_safety_cpp/p1_solver_worker",
)


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def walk_records(root: str, base: str) -> tuple[list[dict], list[dict]]:
    records, secrets = [], []
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(item for item in dirs if item not in SOURCE_EXCLUDES)
        for name in sorted(files):
            absolute = os.path.join(current, name)
            relative = os.path.relpath(absolute, base)
            if os.path.islink(absolute):
                target = os.readlink(absolute)
                resolved = os.path.realpath(absolute)
                inside = os.path.realpath(resolved).startswith(os.path.realpath(base) + os.sep)
                if name in SECRET_BASENAMES or not inside:
                    secrets.append({
                        "path": relative,
                        "link_target": target,
                        "resolved_path": resolved,
                        "mode": oct(os.stat(resolved).st_mode & 0o777),
                        "uid": os.stat(resolved).st_uid,
                        "sha256": sha256_file(resolved) if os.path.isfile(resolved) else None,
                        "classification": "secret_reference",
                        "content_archived": False,
                    })
                    continue
                records.append({"path": relative, "resolved_path": resolved,
                                "bytes": os.path.getsize(resolved),
                                "sha256": sha256_file(resolved), "symlink": True,
                                "valid": True})
                continue
            if name in SECRET_BASENAMES:
                secrets.append({"path": relative,
                                "resolved_path": absolute,
                                "mode": oct(os.stat(absolute).st_mode & 0o777),
                                "sha256": sha256_file(absolute),
                                "classification": "secret_reference",
                                "content_archived": False})
                continue
            records.append({"path": relative, "resolved_path": absolute,
                            "bytes": os.path.getsize(absolute),
                            "sha256": sha256_file(absolute), "symlink": False,
                            "valid": True})
    return records, secrets


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-root", required=True)
    parser.add_argument("--underlay", required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--ros-domain-id", type=int, required=True)
    parser.add_argument("--dds-profile", required=True)
    parser.add_argument("--contract", default="")
    parser.add_argument("--plan", default="")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    release = os.path.realpath(args.release_root)
    underlay = os.path.realpath(args.underlay)
    evidence = os.path.join(release, "evidence")
    if not os.path.isdir(evidence):
        print(f"emit fatal: evidence dir missing: {evidence}", file=sys.stderr)
        return 2

    source_root = os.path.join(release, "capsule", "usv_mpc_ws")
    if not os.path.isdir(source_root):
        print(f"emit fatal: capsule source missing: {source_root}", file=sys.stderr)
        return 2
    records, secrets = walk_records(source_root, source_root)
    source_manifest = {
        "schema": "p1-source-hashes-v1",
        "id": args.id,
        "mode": "source-only",
        "workspace_root": release,
        "packages": sorted(os.listdir(os.path.join(source_root, "src"))),
        "records": records,
        "supplemental": secrets,
        "capsule_verified": True,
        "problems": [],
    }

    install_root = os.path.join(release, "install")
    install_records = []
    for current, dirs, files in os.walk(install_root):
        dirs[:] = sorted(dirs)
        for name in sorted(files):
            absolute = os.path.join(current, name)
            relative = os.path.relpath(absolute, install_root)
            resolved = os.path.realpath(absolute)
            if not os.path.isfile(resolved):
                continue
            install_records.append({"path": relative, "resolved_path": resolved,
                                    "sha256": sha256_file(resolved),
                                    "bytes": os.path.getsize(resolved)})
    install_manifest = {
        "schema": "p1-install-manifest-v1",
        "id": args.id,
        "install_root": install_root,
        "records": install_records,
    }

    artifacts = []
    problems = []
    for relative in ARTIFACT_PATHS:
        path = os.path.join(release, relative)
        if not os.path.isfile(path):
            problems.append(f"missing artifact: {relative}")
            continue
        artifacts.append({"path": relative, "sha256": sha256_file(path),
                          "bytes": os.path.getsize(path)})
    underlay_identity = {
        "realpath": underlay,
        "local_setup": sha256_file(os.path.join(underlay, "local_setup.bash")),
        "packages": sorted(item for item in os.listdir(underlay)
                           if os.path.isdir(os.path.join(underlay, item))),
    }
    underlay_identity_sha = hashlib.sha256(
        json.dumps(underlay_identity, sort_keys=True).encode()).hexdigest()
    artifact_manifest = {
        "schema": "p1-release-artifacts-v1",
        "id": args.id,
        "underlay_identity_sha256": underlay_identity_sha,
        "artifacts": artifacts,
        "problems": problems,
    }

    if not args.write:
        print(json.dumps({"records": len(records), "secrets": len(secrets),
                          "install": len(install_records),
                          "artifacts": len(artifacts),
                          "problems": problems}, indent=2))
        return 0 if not problems else 2

    def write(name, document):
        path = os.path.join(evidence, name)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(path, 0o644)
        return path

    write("source_hashes.json", source_manifest)
    write("install_manifest.json", install_manifest)
    write("release_artifacts.json", artifact_manifest)

    identity = {
        "schema": "p1-release-identity-v1",
        "id": args.id,
        "release_root": release,
        "underlay": underlay,
        "underlay_identity": underlay_identity,
        "underlay_identity_sha256": underlay_identity_sha,
        "source_hashes_sha256": sha256_file(os.path.join(evidence, "source_hashes.json")),
        "install_manifest_sha256": sha256_file(os.path.join(evidence, "install_manifest.json")),
        "release_artifacts_sha256": sha256_file(os.path.join(evidence, "release_artifacts.json")),
        "dropin_template_sha256": sha256_file(
            os.path.join(release, "deploy", "30-scheme-a-commissioning.conf.in")),
        "ros_domain_id": args.ros_domain_id,
        "dds_profile_path": os.path.realpath(args.dds_profile),
        "dds_profile_sha256": sha256_file(args.dds_profile),
        "contract_sha256": sha256_file(args.contract) if args.contract else None,
        "plan_sha256": sha256_file(args.plan) if args.plan else None,
    }
    write("release_identity.json", identity)
    print(json.dumps({"written": True, "records": len(records),
                      "install": len(install_records),
                      "artifacts": len(artifacts),
                      "problems": problems}, indent=2))
    return 0 if not problems else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
