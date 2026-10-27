"""Focused baseline failure tests; no ROS or third-party Python dependency."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "collect_repair_baseline.py"
SPEC = importlib.util.spec_from_file_location("baseline_collector", MODULE_PATH)
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "USV"
        self.root.mkdir()
        self.output = self.root / ".sgh-research/baselines"
        self.active_wrong = False
        for relative in collector.REQUIRED_SOURCE:
            self.put(relative, ("source:" + relative).encode())
        for package in collector.PACKAGES:
            prefix = self.root / "usv_mpc_ws/install" / package
            self.put_at(prefix / "share/ament_index/resource_index/packages" / package, b"")
            self.put_at(prefix / "share" / package / "package.xml", b"<package/>")
            source_xml = self.root / "usv_mpc_ws/src" / package / "package.xml"
            if source_xml.exists():
                self.put_at(prefix / "share" / package / "package.xml", source_xml.read_bytes())
        self.put("usv_mpc_ws/install/usv_mpc_cpp/lib/usv_mpc_cpp/mpc_node", b"ELF test binary")
        self.put("usv_mpc_ws/install/usv_rl_ros/lib/usv_rl_ros/rl_policy_node", b"#!/usr/bin/python3")
        self.copy_installed("usv_bringup", "launch/vrx.launch.py", "share/usv_bringup/launch/vrx.launch.py")
        self.copy_installed("usv_mpc_cpp", "include/usv_mpc_cpp/mpc_node.hpp", "include/usv_mpc_cpp/mpc_node.hpp")
        for name in collector.MODEL_FILES:
            self.put(collector.MODEL_ROOT + "/" + name, ("asset:" + name).encode())
        document = {"contract_version": 1, "output_unit": "N", "input_dim": 43,
                    "output_dim": 2, "action_order": ["T_L", "T_R"],
                    "thrust_scale_n": 25.0, "physical_low_n": [-25.0, -25.0],
                    "physical_high_n": [25.0, 25.0], "normalization_embedded": True,
                    "onnx_sha256": collector.digest(self.root / collector.MODEL_ROOT / "policy_physical_n.onnx"),
                    "source_model_sha256": collector.digest(self.root / collector.MODEL_ROOT / "model.zip"),
                    "source_vecnormalize_sha256": collector.digest(self.root / collector.MODEL_ROOT / "vecnormalize.pkl")}
        self.put(collector.MODEL_ROOT + "/policy_physical_n.manifest.json",
                 json.dumps(document).encode())

    def put(self, relative, data):
        return self.put_at(self.root / relative, data)

    @staticmethod
    def put_at(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def copy_installed(self, package, relative_source, relative_install):
        source = self.root / "usv_mpc_ws/src" / package / relative_source
        destination = self.root / "usv_mpc_ws/install" / package / relative_install
        self.put_at(destination, source.read_bytes())

    def runner(self, argv, cwd=None):
        output = ""
        if argv[:3] == ["ros2", "pkg", "prefix"]:
            prefix = self.root / "usv_mpc_ws/install" / argv[3]
            if self.active_wrong and argv[3] == "usv_mpc_cpp":
                prefix = self.root / "wrong_install"
                prefix.mkdir(exist_ok=True)
            output = str(prefix) + "\n"
        elif argv[:3] == ["git", "rev-parse", "HEAD"]:
            output = "unchanged-head\n"
        elif argv[:3] == ["git", "branch", "--show-current"]:
            output = "dirty-test\n"
        elif argv[:3] == ["git", "status", "--short"]:
            output = " M usv_mpc_ws/src/usv_mpc_cpp/src/mpc_node.cpp\n"
        elif argv[:3] == ["git", "ls-files", "--others"]:
            output = "usv_mpc_ws/scripts/collect_repair_baseline.py\0"
        elif argv[:2] == ["git", "diff"]:
            output = (self.root / "usv_mpc_ws/src/usv_mpc_cpp/src/mpc_node.cpp").read_text()
        return {"argv": list(map(str, argv)), "returncode": 0, "stdout": output, "stderr": ""}

    def freeze(self, name="F1", **kwargs):
        return collector.collect(self.root, name, self.output, runner=self.runner, **kwargs)

    def test_good_static_freeze_keeps_runtime_unknown_and_snapshots_self(self):
        target, manifest = self.freeze()
        self.assertTrue(manifest["integrity"]["frozen_baseline_verified"], manifest["integrity"]["problems"])
        self.assertFalse(manifest["runtime_effective_verified"])
        self.assertEqual(manifest["model_count"], 5)
        self.assertTrue((target / "source_snapshot/usv_mpc_ws/scripts/collect_repair_baseline.py").is_file())
        self.assertTrue((target / "installed_snapshot/usv_mpc_ws/install/usv_mpc_cpp/lib/usv_mpc_cpp/mpc_node").is_file())

    def test_existing_destination_never_overwritten(self):
        target, _ = self.freeze()
        original = (target / "baseline_manifest.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.freeze()
        self.assertEqual((target / "baseline_manifest.json").read_bytes(), original)

    def test_same_head_dirty_source_differentiates_frozen_versions(self):
        first, manifest_a = self.freeze("F1")
        node = self.root / "usv_mpc_ws/src/usv_mpc_cpp/src/mpc_node.cpp"
        node.write_text("changed dirty implementation")
        second, manifest_b = self.freeze("F2")
        self.assertEqual(manifest_a["git"]["head"], manifest_b["git"]["head"])
        a = json.loads((first / "source_hashes.json").read_text())
        b = json.loads((second / "source_hashes.json").read_text())
        self.assertNotEqual(a, b)
        self.assertNotEqual((first / "tracked_changes.patch").read_bytes(),
                            (second / "tracked_changes.patch").read_bytes())

    def test_source_changes_during_capture_fail_and_keep_report(self):
        path = self.root / "usv_mpc_ws/src/usv_mpc_cpp/src/mpc_node.cpp"
        target, manifest = self.freeze(after_copy=lambda: path.write_text("mid collection mutation"))
        self.assertFalse(manifest["integrity"]["frozen_baseline_verified"])
        self.assertIn("source_changed_during_collection", manifest["integrity"]["problems"])
        self.assertTrue((target / "integrity_check.json").is_file())

    def test_installed_changes_during_capture_fail(self):
        path = self.root / "usv_mpc_ws/install/usv_mpc_cpp/lib/usv_mpc_cpp/mpc_node"
        _, manifest = self.freeze(after_copy=lambda: path.write_bytes(b"changed binary"))
        self.assertIn("installed_changed_during_collection", manifest["integrity"]["problems"])

    def test_wrong_active_overlay_fails(self):
        self.active_wrong = True
        _, manifest = self.freeze()
        self.assertIn("invalid_active_package_prefix:usv_mpc_cpp", manifest["integrity"]["problems"])
        self.assertFalse(manifest["integrity"]["frozen_baseline_verified"])

    def test_missing_model_manifest_fails(self):
        (self.root / collector.MODEL_ROOT / "policy_physical_n.manifest.json").unlink()
        _, manifest = self.freeze()
        self.assertFalse(manifest["integrity"]["frozen_baseline_verified"])
        self.assertTrue(any("manifest_missing_or_invalid" in p for p in manifest["integrity"]["problems"]))

    def test_new_onnx_asset_does_not_match_manifest_fails(self):
        (self.root / collector.MODEL_ROOT / "policy_physical_n.onnx").write_bytes(b"different model")
        _, manifest = self.freeze()
        self.assertIn("asset_hash_mismatch:onnx_sha256", manifest["integrity"]["problems"])

    def test_source_installed_header_mismatch_fails(self):
        (self.root / "usv_mpc_ws/install/usv_mpc_cpp/include/usv_mpc_cpp/mpc_node.hpp").write_text("stale header")
        _, manifest = self.freeze()
        self.assertTrue(any(p.startswith("source_installed_mismatch:") for p in manifest["integrity"]["problems"]))

    def test_no_secrets_bags_or_recursive_baselines_copied(self):
        self.put("usv_mpc_ws/src/usv_bringup/config/ntrip_params.yaml", b"secret content")
        self.put("usv_mpc_ws/src/usv_bringup/config/private_key.json", b"secret content")
        self.put("usv_mpc_ws/src/usv_bringup/.env", b"secret content")
        self.put("data/sim_bags/old/recording.mcap", b"bag")
        self.put(".sgh-research/baselines/old/source_snapshot/old.cpp", b"old baseline")
        target, _ = self.freeze()
        paths = [p.as_posix() for p in (target / "source_snapshot").rglob("*") if p.is_file()]
        self.assertFalse(any("ntrip_params" in p or "private_key" in p or "/.env" in p for p in paths))
        self.assertFalse(any("recording.mcap" in p or "old.cpp" in p for p in paths))

    def test_known_prior_effective_dir_is_named_only_and_runtime_stays_unknown(self):
        prior = self.root / ".sgh-research/experiments/prior/model"
        self.put_at(prior / "effective_vehicle.yaml", b"prior config")
        self.put_at(prior / "model_report.json", b"{}")
        self.put_at(prior / "irrelevant.txt", b"must not recurse")
        target, manifest = self.freeze(effective_config_dir=prior)
        config = json.loads((target / "effective_config/configuration_sources.json").read_text())
        self.assertEqual(len(config["generated_configuration"]), 2)
        self.assertFalse(manifest["runtime_effective_verified"])
        self.assertFalse(any("irrelevant.txt" in p.as_posix() for p in target.rglob("*")))

    def test_id_and_output_escape_rejected(self):
        with self.assertRaises(ValueError):
            self.freeze("../overwrite")
        with self.assertRaises(ValueError):
            collector.collect(self.root, "F1", self.root.parent / "outside", runner=self.runner)

    def add_research_interfaces(self, install=True):
        package = collector.RESEARCH_PACKAGE
        source = "usv_mpc_ws/src/" + package + "/"
        self.put(source + "package.xml", b"<package>interfaces</package>")
        self.put(source + "CMakeLists.txt", b"rosidl_generate_interfaces()")
        for name in collector.RESEARCH_MESSAGES:
            self.put(source + "msg/" + name + ".msg", b"uint64 sequence\n")
        if not install:
            return
        prefix = "usv_mpc_ws/install/" + package + "/"
        self.put(prefix + "share/ament_index/resource_index/packages/" + package, b"")
        self.copy_installed(package, "package.xml", "share/" + package + "/package.xml")
        for name in collector.RESEARCH_MESSAGES:
            self.copy_installed(package, "msg/" + name + ".msg", "share/" + package + "/msg/" + name + ".msg")
        self.put(prefix + "lib/lib" + package + "__rosidl_typesupport_cpp.so", b"ELF C++ typesupport")
        self.put(prefix + "lib/python3.12/site-packages/" + package + "/_typesupport.cpython-312-x86_64-linux-gnu.so", b"ELF python typesupport")
        self.put(prefix + "share/" + package + "/type_description/AppliedControl.json", b'{"type_hash":"test"}')

    def test_f2_interfaces_auto_detect_installed_messages_and_binary_hashes(self):
        self.add_research_interfaces()
        target, manifest = self.freeze("F2")
        self.assertTrue(manifest["integrity"]["frozen_baseline_verified"], manifest["integrity"]["problems"])
        installed = json.loads((target / "installed_hashes.json").read_text())
        self.assertIn(collector.RESEARCH_PACKAGE, installed["packages"])
        names = [record["path"] for record in installed["files"]]
        self.assertTrue(any("rosidl_typesupport_cpp.so" in p for p in names))
        self.assertTrue(any("_typesupport.cpython" in p for p in names))
        self.assertTrue(any("type_description/AppliedControl.json" in p for p in names))
        self.assertFalse(installed["binary_source_build_verified"])

    def test_f2_unbuilt_interfaces_fail_instead_of_using_source_only(self):
        self.add_research_interfaces(install=False)
        _, manifest = self.freeze("F2")
        self.assertFalse(manifest["integrity"]["frozen_baseline_verified"])
        self.assertIn("invalid_active_package_prefix:" + collector.RESEARCH_PACKAGE, manifest["integrity"]["problems"])
        self.assertIn("missing_installed_research_typesupport_cpp", manifest["integrity"]["problems"])

    def test_f2_missing_message_or_typesupport_fails(self):
        self.add_research_interfaces()
        prefix = self.root / "usv_mpc_ws/install" / collector.RESEARCH_PACKAGE
        (prefix / "share" / collector.RESEARCH_PACKAGE / "msg/AppliedControl.msg").unlink()
        (prefix / "lib" / ("lib" + collector.RESEARCH_PACKAGE + "__rosidl_typesupport_cpp.so")).unlink()
        _, manifest = self.freeze("F2")
        self.assertIn("missing_installed_research_message:AppliedControl", manifest["integrity"]["problems"])
        self.assertIn("missing_installed_research_typesupport_cpp", manifest["integrity"]["problems"])

    def test_runtime_capture_helper_and_test_are_explicitly_snapshotted(self):
        self.put("usv_mpc_ws/scripts/capture_p0_runtime_context.py", b"runtime context source")
        self.put("usv_mpc_ws/scripts/tests/test_p0_runtime_context.py", b"runtime context tests")
        target, _ = self.freeze()
        self.assertTrue((target / "source_snapshot/usv_mpc_ws/scripts/capture_p0_runtime_context.py").is_file())
        self.assertTrue((target / "source_snapshot/usv_mpc_ws/scripts/tests/test_p0_runtime_context.py").is_file())


if __name__ == "__main__":
    unittest.main()
