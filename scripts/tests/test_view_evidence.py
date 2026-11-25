"""Acceptance checks for source-bound, host-verified BabelTele evidence."""
from __future__ import annotations

from copy import deepcopy
import importlib
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
core = importlib.import_module("aocx")

from aocx_core.common import _digest, _dump, _json
from aocx_core.contracts import context_digest, protected_record, snapshot
from aocx_core.storage import _load_bundle
from aocx_core.views import capsule, check_view, parse_capsule, view_digest


def record(name="N", revision="1", **extra):
    return {"id": name, "rev": revision, "kind": "note", "text": "Open question: 语义 λ?", **extra}


class ViewEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aocx-view-evidence-")
        self.root = Path(self.temp.name)
        self.path = self.root / "bundle"
        self.records = [record(revision="1"), record(revision="2")]
        core.create_bundle(self.records, [], self.path, "test.evidence", heads={"N": "1"})
        source = _load_bundle(self.path)
        self.view = {
            "format": "AOCX-VIEW", "version": "1.0", "codec": "babeltele-view/1",
            "namespace": "test.evidence", "source_records_sha256": source["records_sha256"],
            "source_relations_sha256": source["relations_sha256"], "task": "Explain the open question.",
            "producer": {"model": "fixture-producer", "prompt_sha256": "0" * 64},
            "consumer": {"model": "fixture-reader", "tokenizer": "fixture-tokenizer"},
            "entries": [{"ref": {"id": r["id"], "rev": r["rev"]}, "text": "Task-conditioned text.",
                         "protected": protected_record(r)} for r in self.records],
            "evaluation": {"status": "unassessed"},
        }

    def tearDown(self):
        self.temp.cleanup()

    def write_asset(self, raw, name="reports/evaluation.json"):
        target = self.path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        manifest_path = self.path / "aocx.json"
        manifest = _json(manifest_path.read_bytes())
        manifest["assets"] = [item for item in manifest["assets"] if item["path"] != name]
        manifest["assets"].append({"path": name, "sha256": _digest(raw), "bytes": len(raw), "role": "evaluation"})
        manifest_path.write_bytes(_dump(manifest))
        return name

    def bind_report(self, **updates):
        report = {
            "format": "AOCX-EVALUATION", "version": "1.0", "view_sha256": view_digest(self.view),
            "source_snapshot_sha256": context_digest(snapshot(_load_bundle(self.path))),
            "measurements": {"fixture": True, "semantic_claim": "Host chooses its acceptance rule."},
        }
        report.update(updates)
        name = self.write_asset(_dump(report))
        self.view["evaluation"] = {"status": "passed", "report": name}
        return report

    def assert_error(self, result, code):
        self.assertEqual(result["status"], "failed", result)
        self.assertFalse(result["eligible"])
        self.assertFalse(result["semantic_evaluation_verified"])
        self.assertEqual(result["errors"][0]["code"], code, result)

    def test_unassessed_view_retains_structural_success(self):
        calls = []
        result = check_view(self.path, self.view, evaluator=lambda **kwargs: calls.append(kwargs))
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["structural"], "passed")
        self.assertEqual(result["warnings"], [])
        self.assertFalse(result["evidence_bound"])
        self.assertFalse(result["eligible"])
        self.assertFalse(result["semantic_evaluation_verified"])
        self.assertEqual(calls, [])

    def test_bound_evidence_requires_host_verification(self):
        self.bind_report()
        result = check_view(self.path, self.view)
        self.assertEqual(result["status"], "passed", result)
        self.assertTrue(result["evidence_bound"])
        self.assertFalse(result["eligible"])
        self.assertFalse(result["semantic_evaluation_verified"])
        self.assertEqual(result["warnings"][0]["code"], "semantic_evaluator_required")

    def test_host_receives_explicit_independent_values(self):
        report = self.bind_report()
        expected_view = deepcopy(self.view)
        expected_source = snapshot(_load_bundle(self.path))
        calls = []

        def evaluator(*, report, view, source):
            calls.append((deepcopy(report), deepcopy(view), deepcopy(source)))
            report.clear()
            view["entries"].clear()
            source["heads"].clear()
            return True

        result = check_view(self.path, self.view, evaluator=evaluator)
        self.assertEqual(result["status"], "passed", result)
        self.assertTrue(result["evidence_bound"])
        self.assertTrue(result["eligible"])
        self.assertTrue(result["semantic_evaluation_verified"])
        self.assertEqual(calls, [(report, expected_view, expected_source)])
        self.assertEqual(self.view, expected_view)
        self.assertEqual(snapshot(_load_bundle(self.path)), expected_source)
        self.assertEqual(_json((self.path / "reports/evaluation.json").read_bytes()), report)

    def test_only_explicit_true_is_host_acceptance(self):
        self.bind_report()
        for verdict in (False, None, 1, "passed", {"status": "passed"}):
            with self.subTest(verdict=verdict):
                result = check_view(self.path, self.view, evaluator=lambda **kwargs: verdict)
                self.assertEqual(result["structural"], "passed", result)
                self.assertTrue(result["evidence_bound"])
                self.assertFalse(result["eligible"])
                self.assertFalse(result["semantic_evaluation_verified"])
                self.assertEqual(result["warnings"][0]["code"], "semantic_evaluation_not_verified")

        def unavailable(**kwargs):
            raise RuntimeError("Fixture evaluator unavailable")

        result = check_view(self.path, self.view, evaluator=unavailable)
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["structural"], "passed")
        self.assertFalse(result["eligible"])
        self.assertEqual(result["warnings"][0]["code"], "semantic_evaluator_error")

    def test_legacy_reports_remain_structural_and_unbound(self):
        for raw in (b"Legacy narrative evidence.\n", _dump({"status": "passed"})):
            with self.subTest(raw=raw):
                name = self.write_asset(raw)
                self.view["evaluation"] = {"status": "passed", "report": name}
                calls = []
                result = check_view(self.path, self.view, evaluator=lambda **kwargs: calls.append(kwargs))
                self.assertEqual(result["status"], "passed", result)
                self.assertEqual(result["structural"], "passed")
                self.assertFalse(result["evidence_bound"])
                self.assertFalse(result["eligible"])
                self.assertEqual(result["warnings"][0]["code"], "unbound_evaluation_report")
                self.assertEqual(calls, [])

    def test_changed_view_content_invalidates_report(self):
        self.bind_report()
        variations = []
        changed = deepcopy(self.view)
        changed["entries"][0]["text"] = "A different claim."
        variations.append(("entry", changed))
        changed = deepcopy(self.view)
        changed["task"] = "A different task."
        variations.append(("task", changed))
        for group, field in (("consumer", "model"), ("consumer", "tokenizer"), ("producer", "model"),
                             ("producer", "prompt_sha256")):
            changed = deepcopy(self.view)
            changed[group][field] = "1" * 64 if field.endswith("sha256") else "changed"
            variations.append((group + "." + field, changed))
        changed = deepcopy(self.view)
        changed["future"] = {"reader_setting": True}
        variations.append(("unknown field", changed))
        for label, view in variations:
            with self.subTest(field=label):
                calls = []
                result = check_view(self.path, view, evaluator=lambda **kwargs: calls.append(kwargs))
                self.assert_error(result, "evaluation_view_digest_mismatch")
                self.assertEqual(calls, [])

    def test_source_heads_profiles_and_metadata_invalidate_report(self):
        self.bind_report()
        manifest_path = self.path / "aocx.json"
        original = _json(manifest_path.read_bytes())
        variations = [("heads", {"N": "2"}), ("profiles", ["core/1", "logic/1"]),
                      ("extensions", {"interpretation": "revised"})]
        for field, value in variations:
            with self.subTest(field=field):
                manifest = deepcopy(original)
                manifest[field] = value
                manifest_path.write_bytes(_dump(manifest))
                self.assert_error(check_view(self.path, self.view), "evaluation_source_digest_mismatch")
        manifest_path.write_bytes(_dump(original))
        self.assertTrue(check_view(self.path, self.view)["evidence_bound"])

    def test_asset_bytes_and_explicit_binding_fields_are_checked(self):
        report = self.bind_report()
        asset_path = self.path / "reports/evaluation.json"
        asset_path.write_bytes(asset_path.read_bytes() + b" ")
        self.assert_error(check_view(self.path, self.view), "hash_mismatch")
        for field in ("view_sha256", "source_snapshot_sha256"):
            with self.subTest(field=field):
                changed = deepcopy(report)
                changed[field] = "0" * 64
                self.write_asset(_dump(changed))
                code = "evaluation_view_digest_mismatch" if field == "view_sha256" else "evaluation_source_digest_mismatch"
                self.assert_error(check_view(self.path, self.view), code)
        for updates in ({"version": "2.0"}, {"view_sha256": None}, {"source_snapshot_sha256": "bad"}):
            with self.subTest(updates=updates):
                self.write_asset(_dump({**report, **updates}))
                self.assert_error(check_view(self.path, self.view), "invalid_evaluation_report")

    def test_report_must_be_a_listed_asset_and_declared_passed(self):
        self.view["evaluation"] = {"status": "passed"}
        self.assert_error(check_view(self.path, self.view), "missing_evaluation_report")
        self.view["evaluation"] = {"status": "passed", "report": "unlisted.json"}
        self.assert_error(check_view(self.path, self.view), "missing_evaluation_report")
        self.bind_report()
        self.view["evaluation"]["status"] = "unassessed"
        calls = []
        result = check_view(self.path, self.view, evaluator=lambda **kwargs: calls.append(kwargs))
        self.assertEqual(result["status"], "passed", result)
        self.assertTrue(result["evidence_bound"])
        self.assertFalse(result["eligible"])
        self.assertEqual(calls, [])

    def test_digest_ignores_only_evaluation_and_object_key_order(self):
        original = view_digest(self.view)
        changed = deepcopy(self.view)
        changed["evaluation"] = {"status": "passed", "report": "different-report.json"}
        self.assertEqual(view_digest(changed), original)
        self.assertEqual(view_digest(dict(reversed(list(self.view.items())))), original)
        changed["extra"] = True
        boolean_digest = view_digest(changed)
        changed["extra"] = 1
        self.assertNotEqual(view_digest(changed), boolean_digest)


class LegacyCapsuleProjectionTests(unittest.TestCase):
    def test_projection_preserves_legacy_rows_selection_and_actual_omissions(self):
        records = [record("A", "1", unknown={"value": None}), record("A", "2"),
                   record("B", body="Long body.", extensions={"opaque": True})]
        relations = [{"id": "E", "from": {"id": "B", "rev": "1"}, "kind": "depends_on",
                      "to": {"id": "A", "rev": "1"}, "body": "Detail.", "future": [True, 1]}]
        with tempfile.TemporaryDirectory(prefix="aocx-capsule-projection-") as root:
            path = Path(root) / "bundle"
            core.create_bundle(records, relations, path, "test.legacy", heads={"A": "2", "B": "1"})
            full = parse_capsule(capsule(path, full=True))
            self.assertEqual(full["records"], records)
            self.assertEqual(full["relations"], relations)
            self.assertEqual(full["header"]["omitted_fields"], [])
            self.assertEqual(capsule(path, select=[], full=True), capsule(path, full=True))
            self.assertEqual(capsule(path, select=[]), capsule(path))
            self.assertEqual(capsule(path, select=["B", "B"]), capsule(path, select=["B"]))
            selected = parse_capsule(capsule(path, select=["B"]))
            self.assertEqual(selected["records"], [records[0], {k: v for k, v in records[2].items() if k not in ("body", "extensions")}])
            self.assertEqual(selected["relations"], [{k: v for k, v in relations[0].items() if k != "body"}])
            self.assertEqual(selected["header"]["omitted_fields"], ["body", "extensions"])
            self.assertEqual(selected["header"]["selection"], {"mode": "heads", "refs": [{"id": "B", "rev": "1"}]})
            self.assertEqual(selected["header"]["omitted_records"], 1)
            clean = parse_capsule(capsule(path, select=["A"]))
            self.assertEqual(clean["records"], [records[1]])
            self.assertEqual(clean["header"]["omitted_fields"], [])
            selected_full = parse_capsule(capsule(path, select=["B"], full=True))
            self.assertEqual(selected_full["records"], [records[0], records[2]])
            self.assertEqual(selected_full["relations"], relations)
            self.assertEqual(selected_full["header"]["omitted_fields"], [])


if __name__ == "__main__":
    unittest.main()
