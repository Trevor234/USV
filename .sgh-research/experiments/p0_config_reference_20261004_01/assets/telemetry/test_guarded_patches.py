import importlib.util
import os
from pathlib import Path
import re
import unittest

HERE = Path(__file__).resolve().parent
LOCAL_WORKSPACE = HERE.parents[1] / "p0_contract_impl_2026-10-03/source/usv_mpc_ws"
# Supply the immutable pre-patch F3 snapshot on Ubuntu. Both its workspace
# directory and the workspace/src package directory are accepted.
supplied_root = os.environ.get("P0_TEST_SOURCE_ROOT")
WORKSPACE = Path(supplied_root).expanduser().resolve() if supplied_root else LOCAL_WORKSPACE
if supplied_root and WORKSPACE.name == "src":
    WORKSPACE = WORKSPACE.parent


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


patch = module("telemetry_patch", "apply_telemetry_patch.py")
tests = module("telemetry_tests", "apply_telemetry_tests.py")
runtime = module("telemetry_runtime", "apply_runtime_capture_patch.py")


class GuardTests(unittest.TestCase):
    def test_every_existing_source_anchor_matches_verified_local_mirror(self):
        for relative, edit in patch.PATCHES.items():
            old = (WORKSPACE / relative).read_text(encoding="utf-8")
            new = edit(old)
            self.assertNotEqual(old, new, relative)
            self.assertIn(patch.MARKER, new)

    def test_cpp_formatter_whitespace_changes_are_supported(self):
        old = 'std::variant<ResearchState, ResearchApplied, ResearchCycle>'
        formatted = 'std::variant < ResearchState ,\n ResearchApplied , ResearchCycle >'
        self.assertEqual(patch.replace_once(formatted, old, "new"), "new")

    def test_duplicate_anchor_refused(self):
        with self.assertRaises(ValueError):
            patch.replace_once("int x; int x;", "int x;", "int y;")

    def test_missing_anchor_refused(self):
        with self.assertRaises(ValueError):
            patch.replace_once("int x;", "int z;", "int y;")

    def test_existing_norm_gate_outside_edited_functions_is_preserved(self):
        old = (WORKSPACE / "src/usv_mpc_cpp/src/mpc_node.cpp").read_text(encoding="utf-8")
        new = patch.patch_node(old)
        # Compare the complete real callbacks byte-for-byte. This works both
        # with the old local mirror and the formatted F3 quaternion gate,
        # without synthesizing a formatting-dependent pretend gate line.
        for name in ("odom_callback_", "imu_callback_"):
            original_sections, changed_sections = [], []

            def original(section):
                original_sections.append(section)
                return section

            def changed(section):
                changed_sections.append(section)
                return section

            patch.edit_function(old, name, original)
            patch.edit_function(new, name, changed)
            self.assertEqual(len(original_sections), 1)
            self.assertEqual(original_sections, changed_sections, name)

    def test_no_new_solver_call_or_shifted_getter(self):
        old = (WORKSPACE / "src/usv_mpc_cpp/src/mpc_node.cpp").read_text(encoding="utf-8")
        new = patch.patch_node(old)
        solver_pattern = r"\bmpc_\s*->\s*solve\s*\("
        getter_pattern = r"\bget_predicted_trajectory\s*\("
        self.assertEqual(len(re.findall(solver_pattern, old)), 1)
        self.assertEqual(len(re.findall(solver_pattern, old)), len(re.findall(solver_pattern, new)))
        self.assertEqual(len(re.findall(getter_pattern, old)), len(re.findall(getter_pattern, new)))
        self.assertIn("info.X_pred.data()", new)
        self.assertIn("info.U_pred.data()", new)

    def test_all_old_messages_unchanged(self):
        old = (WORKSPACE / "src/usv_mpc_cpp/include/usv_mpc_cpp/research_logger.hpp").read_text(encoding="utf-8")
        new = patch.patch_logger(old)
        v1_pattern = patch.pattern('msg.schema_version = "p0-contract-v1";')
        self.assertEqual(len(re.findall(v1_pattern, old)), 1)
        self.assertEqual(len(re.findall(v1_pattern, old)), len(re.findall(v1_pattern, new)))
        self.assertIn('msg.schema_version = "p0-reference-prediction-v1";', new)

    def test_test_patch_preserves_existing_cases_and_appends_five(self):
        old = (WORKSPACE / "src/usv_mpc_cpp/test/test_research_contract.cpp").read_bytes()
        new = tests.prepare(old).decode("utf-8")
        old_case_pattern = r"TEST_F\s*\(\s*ResearchContract\s*,\s*(\w+)\s*\)"
        old_names = re.findall(old_case_pattern, old.decode("utf-8"))
        self.assertGreaterEqual(len(old_names), 12)
        self.assertEqual(old_names, re.findall(old_case_pattern, new))
        self.assertEqual(len(re.findall(r"TEST_F\s*\(\s*ReferencePredictionContract\s*,\s*\w+\s*\)", new)), 5)

    def test_test_patch_duplicate_refused(self):
        old = (WORKSPACE / "src/usv_mpc_cpp/test/test_research_contract.cpp").read_bytes()
        with self.assertRaises(ValueError):
            tests.prepare(tests.prepare(old))

    def test_runtime_capture_default_preserved_optional_extra_gate(self):
        old = (WORKSPACE / "scripts/capture_p0_runtime_context.py").read_bytes()
        new = runtime.prepare(old).decode("utf-8")
        compile(new, "capture_p0_runtime_context.py", "exec")
        self.assertIn('if args.reference_prediction:', new)
        self.assertIn('topics["/research/reference_prediction"]', new)
        with self.assertRaises(ValueError):
            runtime.prepare(runtime.prepare(old))


if __name__ == "__main__":
    unittest.main()
