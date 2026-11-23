"""AOCI native contracts survive compact and model-facing projections."""
from pathlib import Path
import hashlib
import importlib.util
import json
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("aocx_protected_test", SCRIPTS / "aocx.py")
aocx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aocx)


class ProtectedAOCITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bundle = Path(self.tmp.name) / "bundle"
        self.fixture = Path(__file__).parent / "fixtures/aoci/volumes"
        aocx.import_bundle(self.fixture, self.bundle, "test.aoci.protected", "aoci")
        self.records = [json.loads(line) for line in (self.bundle / "records.jsonl").read_text().splitlines()]
        self.entity = next(r for r in self.records if r["id"] == "aoci:code:services/queue.py")

    def tearDown(self):
        self.tmp.cleanup()

    def test_selected_handoff_retains_native_contract_and_dictionary(self):
        parsed = aocx.parse_capsule(aocx.capsule(self.bundle, select=[self.entity["id"]]))
        row = next(r for r in parsed["records"] if r["id"] == self.entity["id"])
        self.assertNotIn("body", row)
        self.assertEqual(row["anchors"], self.entity["anchors"])
        self.assertEqual(row["anchors"][0]["S"], "Commit the job and its receipt together")
        self.assertEqual(row["anchors"][0]["A"], "run")
        self.assertEqual(row["anchors"][0]["R"], "code:model.py,database://demo/public/jobs")
        binding = row["anchors"][1]["meta_dictionary"]
        self.assertEqual(binding["scope"], "code")
        self.assertIn("#A Layer: C-Code", binding["dictionary_text"])
        self.assertEqual(binding["asset_sha256"], hashlib.sha256((self.fixture / "aoci.meta.txt").read_bytes()).hexdigest())

    def test_semantic_view_cannot_change_native_constraints(self):
        manifest = json.loads((self.bundle / "aocx.json").read_text())
        protected = {k: v for k, v in self.entity.items() if k not in ("text", "body", "extensions")}
        view = {"format": "AOCX-VIEW", "version": "1.0", "codec": "babeltele-view/1", "namespace": manifest["namespace"],
                "source_records_sha256": hashlib.sha256((self.bundle / "records.jsonl").read_bytes()).hexdigest(),
                "source_relations_sha256": hashlib.sha256((self.bundle / "relations.jsonl").read_bytes()).hexdigest(),
                "task": "Continue work on the queue", "producer": {"model": "fixture", "prompt_sha256": "0" * 64},
                "consumer": {"model": "fixture", "tokenizer": "fixture"},
                "entries": [{"ref": {"id": self.entity["id"], "rev": "1"}, "text": "queue worker", "protected": protected}],
                "evaluation": {"status": "unassessed"}}
        self.assertEqual(aocx.check_view(self.bundle, view)["status"], "passed")
        view["entries"][0]["protected"]["anchors"][0]["S"] = ""
        self.assertEqual(aocx.check_view(self.bundle, view)["status"], "failed")

    def test_source_labels_do_not_repeat_native_code(self):
        source = next(r for r in self.records if r["id"] == "aoci:asset:aoci.code.txt")
        self.assertLess(len(source["text"]), 100)
        self.assertEqual(source["body"]["raw_text"], (self.fixture / "aoci.code.txt").read_text())
        self.assertNotIn("native_context", source["anchors"][0])
        meta = next(r for r in self.records if r["id"] == "aoci:asset:aoci.meta.txt")
        self.assertEqual(meta["anchors"][0]["native_context"], (self.fixture / "aoci.meta.txt").read_text())


if __name__ == "__main__":
    unittest.main()
