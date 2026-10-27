"""Install the new usv_bringup helper package via one guarded setup keyword."""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re


F3_SETUP_SHA256 = "ed3a5482a30a3915fe719bb0397c2e97ec0148c0a5cba830886e6c3d7ec13728"
EMPTY_PACKAGES = re.compile(r"\bpackages[ \t]*=[ \t]*\[\]")


def patched_bytes(raw, expected_sha256=F3_SETUP_SHA256):
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("setup.py SHA256 differs; inspect current setup before patching")
    source = raw.decode("utf-8")
    tree = ast.parse(source)
    names = [n for n in tree.body if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == "package_name" for t in n.targets)]
    if len(names) != 1 or not isinstance(names[0].value, ast.Constant) or names[0].value.value != "usv_bringup":
        raise ValueError("Expected unique package_name = usv_bringup assignment")
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "setup"]
    if len(calls) != 1:
        raise ValueError("Expected one setuptools setup call")
    package_keywords = [k for k in calls[0].keywords if k.arg == "packages"]
    if len(package_keywords) != 1 or not isinstance(package_keywords[0].value, ast.List) or package_keywords[0].value.elts:
        raise ValueError("Expected unique setup(packages=[]) keyword; already changed")
    if len(EMPTY_PACKAGES.findall(source)) != 1:
        raise ValueError("Empty packages textual anchor must occur exactly once")
    patched = EMPTY_PACKAGES.sub("packages=[package_name]", source, count=1)
    ast.parse(patched)
    return patched.encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--expected-sha256", default=F3_SETUP_SHA256)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    target = Path(args.target).resolve(strict=True)
    raw = target.read_bytes()
    patched = patched_bytes(raw, args.expected_sha256)
    if args.apply:
        backup = target.with_name(target.name + ".pre_p0_python_helper_package")
        with backup.open("xb") as stream:
            stream.write(raw)
        if target.read_bytes() != raw:
            raise ValueError("setup.py changed during review")
        target.write_bytes(patched)
    print(json.dumps({"target": str(target), "before_sha256": hashlib.sha256(raw).hexdigest(),
                      "after_sha256": hashlib.sha256(patched).hexdigest(),
                      "applied": args.apply, "edits": 1}, indent=2))


if __name__ == "__main__":
    main()
