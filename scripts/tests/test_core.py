"""Independent acceptance checks for the AOCX file-exchange contract.

Run with ``python3 -m unittest discover -s scripts/tests -v`` from the skill root.
The suite uses temporary directories and never mutates the delivered examples.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
core = importlib.import_module("aocx")


def record(name="N", revision="1", text="An exploratory note.", **fields):
    return {"id": name, "rev": revision, "kind": "note", "text": text, **fields}


def ref(name, revision="1"):
    return {"id": name, "rev": revision}


def relation(name, source, target, kind="depends_on"):
    return {"id": name, "from": ref(source), "to": ref(target), "kind": kind}


class CoreContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aocx-contract-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def bundle(self, name, records=None, relations=None, **kwargs):
        out = self.root / name
        report = core.create_bundle(
            records or [record()], relations or [], out, "test.example", **kwargs
        )
        self.assertEqual(report["status"], "passed", report)
        return out

    def cli(self, *args, expect=0):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "aocx.py"), *map(str, args)],
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, expect, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def bad_create(self, raw_records, relations=""):
        r = self.root / "input.jsonl"
        e = self.root / "relations.jsonl"
        r.write_text(raw_records, encoding="utf-8")
        e.write_text(relations, encoding="utf-8")
        report = self.cli(
            "create", "--records", r, "--relations", e,
            "--out", self.root / "bad", "--namespace", "test.example", expect=2,
        )
        self.assertEqual(report["status"], "failed")

    def test_01_free_text_and_novel_kind_are_valid(self):
        r = record(kind="fiction:possible-world", text="Maybe the narrator changes tense.")
        p = self.bundle("free", [r])
        self.assertEqual(core.validate_bundle(p)["status"], "passed")

    def test_02_unknown_fields_survive_full_capsule(self):
        r = record(
            future={"opaque": [None, True, {"x": "λ"}]},
            extensions={"invented.profile/8": {"status": "unclassified"}},
        )
        p = self.bundle("unknown", [r])
        decoded = core.parse_capsule(core.capsule(p, full=True))
        self.assertEqual(decoded["records"], [r])

    def test_03_domain_states_are_open(self):
        r = record(state={"work": "awaiting-muse", "knowledge": "dream-sequence"})
        p = self.bundle("open-state", [r])
        self.assertEqual(core.parse_capsule(core.capsule(p, full=True))["records"][0], r)

    def test_04_completion_does_not_change_open_knowledge(self):
        r = record(kind="task", state={"work": "complete", "knowledge": "open"})
        p = self.bundle("state", [r])
        decoded = core.parse_capsule(core.capsule(p))["records"][0]
        self.assertEqual(decoded["state"], r["state"])

    def test_05_duplicate_json_members_rejected(self):
        self.bad_create('{"id":"N","id":"M","rev":"1","kind":"note","text":"x"}\n')

    def test_06_non_json_numeric_constants_rejected(self):
        self.bad_create('{"id":"N","rev":"1","kind":"note","text":"x","body":{"x":NaN}}\n')

    def test_07_conflicting_duplicate_record_revision_rejected(self):
        self.bad_create(json.dumps(record(text="first")) + "\n" + json.dumps(record(text="second")) + "\n")

    def test_08_dangling_relation_rejected(self):
        self.bad_create(json.dumps(record()) + "\n", json.dumps(relation("E", "N", "missing")) + "\n")

    def test_09_citation_cycles_remain_valid(self):
        p = self.bundle("citations", [record("A"), record("B")], [
            relation("E1", "A", "B", "cites"),
            relation("E2", "B", "A", "cites"),
        ])
        self.assertEqual(core.validate_bundle(p)["status"], "passed")
        self.bad_create(
            json.dumps(record("A")) + "\n" + json.dumps(record("B")) + "\n",
            json.dumps(relation("E", "A", "B", "supersedes")) + "\n",
        )

    def test_10_capsule_keeps_transitive_assumptions(self):
        hypothesis = record("H", kind="claim", text="Hypothesis H remains assumed.", state={"knowledge": "assumed"})
        first = record("C1", kind="claim", text="Conditional intermediate result.",
                       conditions=[{"text": "Assume H.", "ref": ref("H")}])
        second = record("C2", kind="claim", text="Consequence using C1.")
        p = self.bundle("closure", [hypothesis, first, second], [relation("E1", "C2", "C1")])
        decoded = core.parse_capsule(core.capsule(p, select=["C2"]))
        rows = {r["id"]: r for r in decoded["records"]}
        self.assertEqual(set(rows), {"H", "C1", "C2"})
        self.assertEqual(rows["H"]["state"]["knowledge"], "assumed")
        self.assertEqual(rows["C1"]["conditions"], first["conditions"])

    def test_11_full_capsule_preserves_all_relations(self):
        rows = [record("A"), record("B")]
        edge = relation("E", "A", "B", "future:influences")
        edge["extra"] = {"confidence": "unscored"}
        p = self.bundle("full", rows, [edge])
        decoded = core.parse_capsule(core.capsule(p, full=True))
        self.assertEqual(decoded["relations"], [edge])
        lines = core.capsule(p, full=True).decode("utf-8").splitlines()
        for field, value in [
            ("namespace", None), ("source_records_sha256", "bad-digest"),
            ("source_relations_sha256", None), ("selection", None),
            ("omitted_records", -1), ("omitted_relations", True),
        ]:
            with self.subTest(field=field):
                header = json.loads(lines[0])
                if value is None:
                    del header[field]
                else:
                    header[field] = value
                broken = "\n".join([json.dumps(header), *lines[1:]]) + "\n"
                with self.assertRaises(ValueError):
                    core.parse_capsule(broken)

    def test_12_asset_tampering_is_detected(self):
        p = self.bundle("assets", assets={"attachments/result.txt": b"pass\n"})
        (p / "attachments/result.txt").write_bytes(b"fail\n")
        self.assertEqual(core.validate_bundle(p)["status"], "failed")

    def test_13_parent_traversal_asset_is_rejected(self):
        p = self.bundle("paths")
        (self.root / "outside.bin").write_bytes(b"x")
        m = json.loads((p / "aocx.json").read_text())
        m["assets"].append({"path": "../outside.bin", "sha256": hashlib.sha256(b"x").hexdigest(), "bytes": 1, "role": "evidence"})
        (p / "aocx.json").write_text(json.dumps(m))
        self.assertEqual(core.validate_bundle(p)["status"], "failed")

    def test_14_required_unknown_profile_is_explicit(self):
        p = self.bundle("profile")
        m = json.loads((p / "aocx.json").read_text())
        m["profiles"].append("future:unimplemented/99")
        m["required_profiles"].append("future:unimplemented/99")
        (p / "aocx.json").write_text(json.dumps(m))
        self.assertEqual(core.validate_bundle(p)["status"], "unsupported")
        self.assertEqual(core.validate_bundle(p, preserve_only=True)["status"], "passed")

    def legacy_zip(self, unsafe=False):
        p = self.root / "original.zip"
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("legacy/PROTOCOL.json", '{"protocol":"GBCX/1"}\n')
            z.writestr("legacy/claims.jsonl", json.dumps({
                "id": "C", "status": "conditional", "statement": "C given H.",
                "assumptions": ["H is assumed."], "arbitrary_future": {"u": [1, 2]},
            }) + "\n")
            z.writestr("legacy/opaque.bin", b"\x00\xff\r\n")
            if unsafe:
                z.writestr("../outside.txt", b"unsafe")
        return p

    def test_15_legacy_restore_is_byte_identical(self):
        source = self.legacy_zip()
        p = self.root / "imported"
        self.cli("import-gbcx", source, p, "--namespace", "test.example")
        target = self.root / "restored.zip"
        self.cli("restore", p, target, "--origin", "legacy")
        self.assertEqual(target.read_bytes(), source.read_bytes())

    def test_16_unsafe_archive_member_rejected(self):
        source = self.legacy_zip(unsafe=True)
        report = self.cli("import-gbcx", source, self.root / "unsafe", "--namespace", "test.example", expect=2)
        self.assertEqual(report["status"], "failed")
        self.assertFalse((self.root / "outside.txt").exists())

    def branches(self, mode):
        base_rows = [record("A"), record("B")]
        base = self.bundle("base", base_rows, heads={"A": "1", "B": "1"})
        left_rows = deepcopy(base_rows) + [record("A", "2", text="Left revision")]
        left = self.bundle("left", left_rows, heads={"A": "2", "B": "1"})
        if mode == "disjoint":
            right_rows = deepcopy(base_rows) + [record("B", "2", text="Right revision")]
            right_heads = {"A": "1", "B": "2"}
        else:
            right_rows = deepcopy(base_rows) + [record("A", "3", text="Competing revision")]
            right_heads = {"A": "3", "B": "1"}
        right = self.bundle("right", right_rows, heads=right_heads)
        return base, left, right

    def test_17_disjoint_branch_edits_are_clean(self):
        self.assertEqual(core.merge_check(*self.branches("disjoint"))["status"], "clean")

    def test_18_divergent_heads_require_explicit_resolution(self):
        report = core.merge_check(*self.branches("divergent"))
        self.assertEqual(report["status"], "conflict")
        self.assertTrue(report["conflicts"])

    def test_19_reused_revision_with_changed_content_conflicts(self):
        base = self.bundle("base", [record()])
        left = self.bundle("left", [record(text="Same revision id, altered content")])
        right = self.bundle("right", [record()])
        self.assertEqual(core.merge_check(base, left, right)["status"], "conflict")
        rows = [record("A", "1"), record("A", "2")]
        base = self.bundle("cycle-base", rows, heads={"A": "1"})
        left = self.bundle("cycle-left", rows, [{
            "id": "E1", "from": ref("A", "2"), "to": ref("A", "1"), "kind": "supersedes"
        }], heads={"A": "1"})
        right = self.bundle("cycle-right", rows, [{
            "id": "E2", "from": ref("A", "1"), "to": ref("A", "2"), "kind": "supersedes"
        }], heads={"A": "1"})
        self.assertEqual(core.merge_check(base, left, right)["status"], "conflict")

    def view(self, path, rows):
        manifest = json.loads((path / "aocx.json").read_text())
        return {
            "format": "AOCX-VIEW", "version": "1.0", "codec": "babeltele-view/1",
            "namespace": manifest["namespace"],
            "source_records_sha256": hashlib.sha256((path / manifest["records"]).read_bytes()).hexdigest(),
            "source_relations_sha256": hashlib.sha256((path / manifest["relations"]).read_bytes()).hexdigest(),
            "task": "Testing metadata preservation only.",
            "producer": {"model": "test-fixture", "prompt_sha256": "0" * 64},
            "consumer": {"model": "test-fixture", "tokenizer": "not-run"},
            "entries": [
                {"ref": ref(r["id"], r["rev"]), "text": "Fixture text; no language model execution.",
                 "protected": {k: deepcopy(v) for k, v in r.items() if k not in ("text", "body", "extensions")}}
                for r in rows
            ],
            "evaluation": {"status": "unassessed"},
        }

    def test_20_view_structure_does_not_certify_semantics(self):
        rows = [record(conditions=[{"text": "Assume H."}], state={"knowledge": "derived"})]
        p = self.bundle("view", rows)
        result = core.check_view(p, self.view(p, rows))
        self.assertEqual(result["status"], "passed", result)
        self.assertFalse(result["eligible"])
        self.assertFalse(result["semantic_evaluation_verified"])

    def test_21_view_cannot_drop_protected_condition(self):
        rows = [record(conditions=[{"text": "Assume H."}])]
        p = self.bundle("view", rows)
        view = self.view(p, rows)
        view["entries"][0]["protected"]["conditions"] = []
        self.assertEqual(core.check_view(p, view)["status"], "failed")

    def test_22_view_is_bound_to_relation_snapshot(self):
        rows = [record("A"), record("B")]
        old = self.bundle("old", rows, [relation("E", "A", "B", "depends_on")])
        new = self.bundle("new", rows, [relation("E", "A", "B", "relates_to")])
        view = self.view(old, rows)
        self.assertEqual(core.check_view(new, view)["status"], "failed")

    def test_23_view_cannot_omit_assumption_record(self):
        rows = [record("H", state={"knowledge": "assumed"}),
                record("C", conditions=[{"text": "Assume H.", "ref": ref("H")}])]
        p = self.bundle("view", rows)
        view = self.view(p, [rows[1]])
        self.assertEqual(core.check_view(p, view)["status"], "failed")

    def capabilities(self, codecs, lossy=False):
        return {"versions": ["1.0"], "profiles": ["core/1"],
                "required_profiles": ["core/1"], "codecs": codecs, "accepts_lossy": lossy}

    def test_24_lossy_view_requires_both_peers_to_accept(self):
        offer = self.capabilities(["babeltele-view/1", "table-jsonl/1"], True)
        reader = self.capabilities(["babeltele-view/1", "table-jsonl/1"], False)
        result = core.negotiate(offer, reader)
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["codec"], "table-jsonl/1")
        self.assertFalse(result["lossy"])

    def test_25_unknown_codec_is_not_assumed_lossless(self):
        offer = self.capabilities(["future-semantic/1"])
        reader = self.capabilities(["future-semantic/1"])
        result = core.negotiate(offer, reader)
        self.assertNotEqual(result["status"], "passed", result)
        with self.subTest(mode="declared-lossless"):
            offer["codec_modes"] = {"future-semantic/1": "lossless"}
            reader["codec_modes"] = {"future-semantic/1": "lossless"}
            result = core.negotiate(offer, reader)
            self.assertEqual(result["status"], "passed", result)
            self.assertTrue(result["implementation_required"])
            self.assertFalse(result["lossy"])
        with self.subTest(mode="semantic-requires-consent"):
            offer["codec_modes"] = {"future-semantic/1": "semantic"}
            reader["codec_modes"] = {"future-semantic/1": "semantic"}
            self.assertNotEqual(core.negotiate(offer, reader)["status"], "passed")
            offer["accepts_lossy"] = reader["accepts_lossy"] = True
            result = core.negotiate(offer, reader)
            self.assertEqual(result["status"], "passed", result)
            self.assertTrue(result["implementation_required"])
            self.assertTrue(result["lossy"])
            self.assertTrue(result["evaluation_required"])
        with self.subTest(mode="conflicting-mode"):
            reader["codec_modes"] = {"future-semantic/1": "lossless"}
            self.assertNotEqual(core.negotiate(offer, reader)["status"], "passed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
