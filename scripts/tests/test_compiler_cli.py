"""Process-level acceptance checks for the compiler's public command path."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from aocx_core.contracts import make_contract
from aocx_core.storage import create_bundle


class CompilerCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aocx-cli-")
        self.root = Path(self.temp.name)
        self.bundle = self.root / "source"
        self.records = [{"id": "H", "rev": "1", "kind": "assumption", "text": "前提 H"},
                        {"id": "C", "rev": "1", "kind": "claim", "text": "H ⇒ C",
                         "body": {"detail": "原始内容"},
                         "conditions": [{"text": "H", "ref": {"id": "H", "rev": "1"}}]}]
        create_bundle(self.records, [], self.bundle, "test.cli")

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *args, status="passed"):
        run = subprocess.run([sys.executable, str(SCRIPTS / "aocx.py"), *map(str, args)],
                             cwd=self.root, capture_output=True, check=False)
        self.assertEqual(run.returncode, 0 if status == "passed" else 2, run.stderr.decode())
        report = json.loads(run.stdout)
        self.assertEqual(report["status"], status, report)
        return report

    def test_compile_verify_decode_from_external_working_directory(self):
        wire, report_file = self.root / "context.aocx", self.root / "compile.json"
        original = {p.name: p.read_bytes() for p in self.bundle.iterdir()}
        report = self.run_cli("compile", self.bundle, "--out", wire, "--report", report_file)
        self.assertEqual(report, json.loads(report_file.read_text()))
        self.assertEqual(report["cost"], len(wire.read_bytes()))
        self.assertEqual(report["fidelity"], "exact")
        verified = self.run_cli("verify", self.bundle, wire)
        self.assertTrue(verified["source_verified"])
        output = self.root / "context.json"
        decoded = self.run_cli("decode", wire, "--out", output)
        self.assertFalse(decoded["source_verified"])
        self.assertEqual(json.loads(output.read_text())["records"], self.records)
        self.assertEqual({p.name: p.read_bytes() for p in self.bundle.iterdir()}, original)

    def test_projection_and_expected_contract_are_explicit(self):
        wire = self.root / "selection.aocx"
        self.run_cli("optimize", self.bundle, "--out", wire, "--mode", "projection", "--select", "C")
        output = self.root / "context.json"
        self.run_cli("decode", wire, "--out", output)
        context = json.loads(output.read_text())
        self.assertEqual({r["id"] for r in context["records"]}, {"H", "C"})
        self.assertNotIn("body", context["records"][1])
        contract = self.root / "expected.json"
        contract.write_text(json.dumps(make_contract()))
        result = self.run_cli("verify", self.bundle, wire, "--contract", contract, status="failed")
        self.assertEqual(result["errors"][0]["code"], "contract_mismatch")

    def test_reader_filter_and_character_metric_reach_compiler(self):
        reader = self.root / "reader.json"
        reader.write_text(json.dumps({"codecs": ["json/1"], "profiles": ["core/1"]}))
        wire = self.root / "context.aocx"
        report = self.run_cli("compile", self.bundle, "--out", wire, "--reader", reader,
                              "--codec", "aocx-expr/1", "--codec", "json/1", "--metric", "characters")
        self.assertEqual(report["selected_codec"], "json/1")
        self.assertEqual(report["cost"], len(wire.read_bytes().decode("utf-8")))

    def test_failed_candidates_and_missing_tokenizer_leave_no_output(self):
        for extra in [("--codec", "unsupported/1"), ("--metric", "tokens"), ("--select", "C")]:
            wire = self.root / "rejected.aocx"
            self.run_cli("compile", self.bundle, "--out", wire, *extra, status="failed")
            self.assertFalse(wire.exists())

    def test_output_collision_and_existing_report_preserve_user_files(self):
        wire = self.root / "context.aocx"
        self.run_cli("compile", self.bundle, "--out", wire, "--report", wire, status="failed")
        self.assertFalse(wire.exists())
        report = self.root / "existing.json"
        report.write_text("user content")
        self.run_cli("compile", self.bundle, "--out", wire, "--report", report, status="failed")
        self.assertFalse(wire.exists())
        self.assertEqual(report.read_text(), "user content")

    def test_symbolic_expression_and_unicode_are_public_inputs(self):
        expression = 'S[x="GenshinImpact"]⊢x∈{y|SelfDev(Dev(x),y)∧OpenAdvGame(y)}'
        output = self.root / "logic.json"
        report = self.run_cli("logic", "--expression", expression, "--out", output)
        self.assertEqual(report["declaration"]["format"], "aocx-logic/1")
        rendered = self.run_cli("logic", "--input", output)
        self.assertEqual(rendered["declaration"], json.loads(output.read_text()))
        self.assertEqual(rendered["rendered"], report["rendered"])
        chinese = self.run_cli("logic", "--expression", "自研(开发者(x),x)∧开放冒险(x)")
        self.assertIn("自研", chinese["rendered"])

    def test_explicit_logic_profile_validates_shape_and_preserves_open_data(self):
        valid = dict(self.records[0], logic={"format": "aocx-logic/1",
                                            "expression": {"op": "domain:custom", "text": "自由扩展"}})
        report = create_bundle([valid], [], self.root / "valid", "test.logic",
                               profiles=["core/1", "logic/1"], required_profiles=["core/1", "logic/1"])
        self.assertEqual(report["status"], "passed")
        invalid = dict(valid, logic={"format": "aocx-logic/1", "expression": {"op": "var"}})
        with self.assertRaises(ValueError):
            create_bundle([invalid], [], self.root / "invalid", "test.logic")
        free = dict(valid, logic={"description": "开放文本，不声明 AST"})
        self.assertEqual(create_bundle([free], [], self.root / "free", "test.logic")["status"], "passed")


if __name__ == "__main__":
    unittest.main()
