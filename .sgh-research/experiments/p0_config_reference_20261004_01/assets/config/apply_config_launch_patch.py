"""Apply four guarded local edits to F3 vrx.launch.py; no full-file replacement."""

import argparse
import ast
import hashlib
from pathlib import Path


F3_VRX_SHA256 = "090f40616d15567d03517632d41293b80fec762d2cb80915d00f68fa986e3259"
MARKER = "P0_INDEPENDENT_CONTROLLER_CONFIG"
EDITS = (
    ('    usv_params_sim = LaunchConfiguration("effective_vehicle")\n',
     '    # P0_INDEPENDENT_CONTROLLER_CONFIG: opt-in B override, legacy fallback.\n'
     '    usv_params_sim = LaunchConfiguration(\n'
     '        "controller_vehicle", default=LaunchConfiguration("effective_vehicle"))\n'),
    ('    def plant_parameter(name):\n'
     '        return ParameterValue(LaunchConfiguration("plant_" + name), value_type=float)\n',
     '    def plant_parameter(name):\n'
     '        return ParameterValue(LaunchConfiguration("plant_" + name), value_type=float)\n'
     '\n'
     '    def controller_parameter(name):\n'
     '        return ParameterValue(LaunchConfiguration(\n'
     '            "controller_" + name, default=LaunchConfiguration("plant_" + name)),\n'
     '            value_type=float)\n'),
    ('                "dynamic.T_max": plant_parameter("tmax"),\n',
     '                "dynamic.T_max": controller_parameter("tmax"),\n'),
    ('                "dynamic.T_min": plant_parameter("tmin"),\n',
     '                "dynamic.T_min": controller_parameter("tmin"),\n'),
)


def patched_bytes(raw, expected_sha256=F3_VRX_SHA256):
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Target SHA256 differs; inspect current local snippets before patching")
    text = raw.decode("utf-8")
    if MARKER in text:
        raise ValueError("Already patched")
    newline = "\r\n" if "\r\n" in text else "\n"
    if newline == "\r\n" and "\n" in text.replace("\r\n", ""):
        raise ValueError("Mixed source line endings require independent review")
    text = text.replace("\r\n", "\n")
    for before, _ in EDITS:
        if text.count(before) != 1:
            raise ValueError("Patch anchor must occur exactly once: " + repr(before))
    for before, after in EDITS:
        text = text.replace(before, after, 1)
    ast.parse(text)
    return text.replace("\n", newline).encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--expected-sha256", default=F3_VRX_SHA256)
    parser.add_argument("--apply", action="store_true", help="Default is a read-only preview")
    args = parser.parse_args()
    target = Path(args.target).resolve(strict=True)
    raw = target.read_bytes()
    patched = patched_bytes(raw, args.expected_sha256)
    result = {"target": str(target), "before_sha256": hashlib.sha256(raw).hexdigest(),
              "after_sha256": hashlib.sha256(patched).hexdigest(), "edits": len(EDITS),
              "applied": args.apply}
    if args.apply:
        backup = target.with_name(target.name + ".pre_p0_independent_config")
        with backup.open("xb") as stream:
            stream.write(raw)
        if target.read_bytes() != raw:
            raise ValueError("Target changed between review and application")
        target.write_bytes(patched)
    import json
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
