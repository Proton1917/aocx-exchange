"""Acceptance tests for reversible, contract-constrained context compilation.

These tests compare restored values and final wire costs with independent
expectations. External codecs are deliberately simple fixtures so that the
optimizer must establish their fidelity instead of trusting their names.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from aocx_core.codecs import Codec, default_registry
from aocx_core.contracts import make_contract
from aocx_core.optimizer import compile_context, recover_context, verify_representation
from aocx_core.storage import create_bundle


def row(name="N", revision="1", **extra):
    return {"id": name, "rev": revision, "kind": "claim",
            "text": "条件 H 下，∀x∈D: P(x) ⇒ Q(x).", **extra}


def ref(name, revision="1"):
    return {"id": name, "rev": revision}


def edge(name, source, target, kind="depends_on", source_rev="1", target_rev="1", **extra):
    return {"id": name, "from": ref(source, source_rev), "to": ref(target, target_rev),
            "kind": kind, **extra}


def json_codec(identifier, *, padding=0, mutate=None):
    """A decoder-backed fixture with explicit, measurable transport overhead."""
    def encode(value):
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        return ("AOCX/1 " + identifier + "\n" + encoded).encode("utf-8") + b" " * padding

    def decode(raw):
        value = json.loads(raw.split(b"\n", 1)[1])
        if mutate:
            mutate(value)
        return value

    return Codec(identifier, encode, decode)


def first_record(value):
    """Locate a record without relying on the representation envelope layout."""
    if isinstance(value, dict):
        if {"id", "rev", "kind", "text"}.issubset(value):
            return value
        children = value.values()
    elif isinstance(value, list):
        children = value
    else:
        return None
    for child in children:
        found = first_record(child)
        if found is not None:
            return found
    return None


class OptimizerContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aocx-optimizer-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def bundle(self, name="source", rows=None, edges=None, **options):
        destination = self.root / name
        result = create_bundle(rows if rows is not None else [row()], edges or [],
                               destination, "test.optimizer", **options)
        self.assertEqual(result["status"], "passed", result)
        return destination

    def compiled(self, source, contract=None, **options):
        result = compile_context(source, contract, **options)
        self.assertIsInstance(result["representation"], bytes)
        self.assertEqual(result["report"]["status"], "passed", result["report"])
        self.assertTrue(result["report"]["finite_search"])
        return result

    def rejected(self, operation):
        """The API may raise a contract error or return an explicit failure."""
        try:
            result = operation()
        except ValueError:
            return
        report = result.get("report", result) if isinstance(result, dict) else {}
        self.assertIn(report.get("status"), {"failed", "unsupported"}, result)

    def rewrite_manifest(self, source, mutate):
        path = source / "aocx.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        mutate(value)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def test_exact_roundtrip_preserves_unicode_types_and_unknown_fields(self):
        records = [row(
            text="中文 English Ελληνικά العربية: ∀x, ∃y; 引号\" 与换行\n",
            body={"nullable": None, "boolean": True, "integer": 1, "decimal": 1.0,
                  "negative_zero": -0.0, "nested": [{"λ": "µm"}, [], {}]},
            future={"uninterpreted": [False, "x", 12345678901234567890]},
            extensions={"domain/9": {"status": "hypothetical"}},
        )]
        source = self.bundle(rows=records)
        result = self.compiled(source)
        restored = recover_context(result["representation"])
        # Serialized value comparison distinguishes Python's 1 == 1.0 == True.
        self.assertEqual(json.dumps(restored["records"], sort_keys=True, ensure_ascii=False),
                         json.dumps(records, sort_keys=True, ensure_ascii=False))
        self.assertEqual(restored["namespace"], "test.optimizer")
        self.assertEqual(verify_representation(source, result["representation"])["status"], "passed")

    def test_opaque_body_can_quote_a_malformed_logic_sample(self):
        original = row(kind="parser.fixture", text="Quoted JSON is source data.", body={
            "invalid_sample": {"format": "aocx-logic/1", "expression": {}},
            "expected_diagnostic": "缺少 op / missing op",
        })
        source = self.bundle(rows=[original])
        for codec in ("aocx-expr/1", "aocx-expr-dict/1", "json/1"):
            with self.subTest(codec=codec):
                raw = self.compiled(source, codecs=[codec])["representation"]
                self.assertEqual(recover_context(raw)["records"], [original])
                self.assertEqual(verify_representation(source, raw)["status"], "passed")

    def test_exact_preserves_heads_profiles_metadata_and_unknown_relations(self):
        records = [row("A", "1"), row("A", "2"), row("B")]
        relations = [edge("future", "A", "B", "domain:related", source_rev="2",
                          extra={"meaning": "方向按源定义", "confidence": None})]
        source = self.bundle(rows=records, edges=relations, heads={"A": "2", "B": "1"},
                             profiles=["core/1", "future:optional/9"],
                             extensions={"domain": {"owner": "实验室"}})
        self.rewrite_manifest(source, lambda m: m.update(domain_note={"scope": "research"}))
        restored = recover_context(self.compiled(source)["representation"])
        self.assertEqual(restored["heads"], {"A": "2", "B": "1"})
        self.assertEqual(restored["profiles"], ["core/1", "future:optional/9"])
        self.assertEqual(restored["required_profiles"], ["core/1"])
        self.assertEqual(restored["relations"], relations)
        self.assertEqual(restored["metadata"]["domain_note"], {"scope": "research"})
        self.assertEqual(restored["metadata"]["extensions"], {"domain": {"owner": "实验室"}})

    def test_projection_keeps_transitive_historical_prerequisites(self):
        records = [row("H", state={"knowledge": "assumed"}),
                   row("A", "1", conditions=[{"text": "Assume H", "ref": ref("H")}]),
                   row("A", "2", text="Later revision"), row("C"), row("Unused")]
        source = self.bundle(rows=records,
                             edges=[edge("C-A", "C", "A", target_rev="1")],
                             heads={"H": "1", "A": "2", "C": "1", "Unused": "1"})
        contract = make_contract(mode="projection", select=["C"], omit_fields=[])
        result = self.compiled(source, contract)
        restored = recover_context(result["representation"])
        self.assertEqual({(r["id"], r["rev"]) for r in restored["records"]},
                         {("C", "1"), ("A", "1"), ("H", "1")})
        self.assertEqual(restored["heads"], {"H": "1", "C": "1"})
        self.assertEqual(restored["relations"][0]["to"], ref("A", "1"))
        self.assertEqual(verify_representation(source, result["representation"], contract)["status"], "passed")

    def test_projection_preserves_cycles_and_knowledge_states(self):
        records = [row("A", state={"work": "complete", "knowledge": "open"}),
                   row("B", conditions=[{"text": "Assume A", "ref": ref("A")}])]
        source = self.bundle(rows=records, edges=[edge("AB", "A", "B", "cites")])
        contract = make_contract(mode="projection", select=["A"])
        restored = recover_context(self.compiled(source, contract)["representation"])
        self.assertEqual({r["id"] for r in restored["records"]}, {"A", "B"})
        actual = next(r for r in restored["records"] if r["id"] == "A")
        self.assertEqual(actual["state"], {"work": "complete", "knowledge": "open"})

    def test_projection_omissions_are_explicit_and_protected_fields_survive(self):
        record = row(body={"details": "long source"}, extensions={"optional": True},
                     conditions=[{"text": "x > 0"}], scope="∀x∈R", anchors=["≤", "10 ms"],
                     state={"knowledge": "derived"}, future={"tag": "preserve"})
        source = self.bundle(rows=[record])
        contract = make_contract(mode="projection")
        restored = recover_context(self.compiled(source, contract)["representation"])
        expected = {k: v for k, v in record.items() if k not in {"body", "extensions"}}
        self.assertEqual(restored["records"], [expected])
        full_fields = make_contract(mode="projection", omit_fields=[])
        self.assertEqual(recover_context(self.compiled(source, full_fields)["representation"])["records"], [record])

    def test_expected_exact_contract_rejects_projection_downgrade(self):
        source = self.bundle(rows=[row(body={"critical": "original"})])
        projection = self.compiled(source, make_contract(mode="projection"))["representation"]
        self.assertEqual(verify_representation(source, projection, make_contract(mode="exact"))["status"], "failed")

    def test_source_binding_covers_head_and_metadata_changes(self):
        source = self.bundle(rows=[row("A", "1"), row("A", "2")], heads={"A": "2"})
        representation = self.compiled(source)["representation"]
        self.rewrite_manifest(source, lambda m: m.update(heads={"A": "1"}))
        self.assertEqual(verify_representation(source, representation)["status"], "failed")
        self.rewrite_manifest(source, lambda m: m.update(heads={"A": "2"}, scope_note="new scope"))
        self.assertEqual(verify_representation(source, representation)["status"], "failed")

    def test_actual_roundtrip_rejects_logic_changed_by_decoder(self):
        source = self.bundle()
        registry = default_registry()
        registry.register(json_codec("test-good/1"))
        registry.register(json_codec("test-evil/1", mutate=lambda p: first_record(p).update(text="∃x: Q(x)")))
        result = self.compiled(source, registry=registry, codecs=["test-evil/1", "test-good/1"])
        self.assertEqual(result["report"]["selected_codec"], "test-good/1")
        rejected = next(c for c in result["report"]["candidates"] if c["codec"] == "test-evil/1")
        self.assertNotEqual(rejected["status"], "passed")
        self.assertTrue(rejected["errors"])

    def test_actual_roundtrip_rejects_bool_integer_substitution(self):
        source = self.bundle(rows=[row(future={"flag": True})])
        registry = default_registry()
        registry.register(json_codec("test-bool/1", mutate=lambda p: first_record(p)["future"].update(flag=1)))
        self.rejected(lambda: compile_context(source, registry=registry, codecs=["test-bool/1"]))

    def test_candidate_decoder_failure_allows_valid_fallback(self):
        source = self.bundle()
        registry = default_registry()
        def broken_decode(raw):
            raise ValueError("fixture decoder fails")
        registry.register(Codec("test-broken/1", lambda p: b"AOCX/1 test-broken/1\nx", broken_decode))
        result = self.compiled(source, registry=registry, codecs=["test-broken/1", "aocx-expr/1"])
        self.assertEqual(result["report"]["selected_codec"], "aocx-expr/1")
        self.assertTrue(any(c["codec"] == "test-broken/1" and c["errors"]
                            for c in result["report"]["candidates"]))

    def test_mutating_encoder_cannot_poison_other_candidates_or_source(self):
        original = row(text="Original conditional conclusion: ∀x, H(x) ⇒ P(x).")
        source = self.bundle(rows=[original])
        registry = default_registry()
        good = json_codec("test-good/1")
        def mutate_then_fail(payload):
            first_record(payload)["text"] = "Poisoned shared state"
            raise ValueError("fixture encoder mutated its argument")
        registry.register(Codec("test-mutate/1", mutate_then_fail, good.decode))
        registry.register(good)
        result = self.compiled(source, registry=registry, codecs=["test-mutate/1", "test-good/1"])
        self.assertEqual(recover_context(result["representation"], registry)["records"], [original])
        self.assertEqual(verify_representation(source, result["representation"], registry=registry)["status"], "passed")

    def test_verifier_reports_plugin_decoder_failure(self):
        source = self.bundle()
        registry = default_registry()
        def broken_decode(raw):
            raise KeyError("fixture decoder cannot find its payload")
        registry.register(Codec("test-keyerror/1", lambda value: b"", broken_decode))
        report = verify_representation(source, b"AOCX/1 test-keyerror/1\nx", registry=registry)
        self.assertEqual(report["status"], "failed")
        self.assertTrue(report["errors"])

    def test_wire_cost_includes_envelope_and_dictionary_overhead(self):
        source = self.bundle()
        registry = default_registry()
        registry.register(json_codec("test-short/1"))
        registry.register(json_codec("test-long_/1", padding=4096))
        result = self.compiled(source, registry=registry, codecs=["test-long_/1", "test-short/1"])
        report = result["report"]
        self.assertEqual(report["selected_codec"], "test-short/1")
        self.assertEqual(report["metric"], "bytes")
        self.assertEqual(report["cost"], len(result["representation"]))
        costs = {c["codec"]: c["cost"] for c in report["candidates"] if c["status"] == "passed"}
        self.assertGreaterEqual(costs["test-long_/1"] - costs["test-short/1"], 4096)
        self.assertEqual(report["cost"], min(costs.values()))

    def test_equal_cost_uses_codec_id_tiebreak_independent_of_offer_order(self):
        source = self.bundle()
        registry = default_registry()
        registry.register(json_codec("test-a/1"))
        registry.register(json_codec("test-z/1"))
        first = self.compiled(source, registry=registry, codecs=["test-z/1", "test-a/1"])
        second = self.compiled(source, registry=registry, codecs=["test-a/1", "test-z/1"])
        self.assertEqual(first["report"]["selected_codec"], "test-a/1")
        self.assertEqual(first["representation"], second["representation"])

    def test_reader_codec_intersection_controls_candidates(self):
        source = self.bundle()
        result = self.compiled(source, reader={"codecs": ["aocx-expr/1"], "profiles": ["core/1"]})
        self.assertEqual(result["report"]["selected_codec"], "aocx-expr/1")
        self.rejected(lambda: compile_context(source, reader={"codecs": ["unknown/1"], "profiles": ["core/1"]}))

    def test_reader_must_support_required_profile(self):
        source = self.bundle()
        self.rejected(lambda: compile_context(source, reader={"codecs": ["aocx-expr/1"], "profiles": []}))
        self.rejected(lambda: compile_context(source, reader={"codecs": ["aocx-expr/1"],
                                                              "profiles": ["core/1", "extra/1"],
                                                              "required_profiles": ["extra/1"]}))

    def test_token_cost_is_measured_on_entire_selected_wire(self):
        source = self.bundle()
        seen = []
        def tokenizer(text):
            seen.append(text)
            # A deterministic test tokenizer, explicitly identified as such.
            return list(text)
        result = self.compiled(source, metric="tokens", tokenizer=tokenizer, tokenizer_id="fixture:unicode-codepoints/1")
        wire = result["representation"].decode("utf-8")
        self.assertIn(wire, seen)
        self.assertEqual(result["report"]["cost"], len(wire))
        self.assertEqual(result["report"]["metric"], "tokens")

    def test_token_cost_requires_actual_tokenizer_and_identity(self):
        source = self.bundle()
        self.rejected(lambda: compile_context(source, metric="tokens", tokenizer_id="fixture/1"))
        self.rejected(lambda: compile_context(source, metric="tokens", tokenizer=lambda text: list(text)))

    def test_illegal_contracts_and_protected_omissions_are_rejected(self):
        source = self.bundle()
        cases = [dict(mode="unknown"), dict(mode="exact", select=["N"]),
                 dict(mode="exact", omit_fields=["body"]),
                 dict(mode="projection", select=[123])]
        for field in ("id", "rev", "text", "conditions", "scope", "state", "anchors", "logic"):
            cases.append(dict(mode="projection", omit_fields=[field]))
        for options in cases:
            with self.subTest(options=options):
                self.rejected(lambda options=options: compile_context(source, make_contract(**options)))

    def test_unknown_selection_and_unknown_codec_have_explicit_failure(self):
        source = self.bundle()
        self.rejected(lambda: compile_context(source, make_contract(mode="projection", select=["absent"])))
        self.rejected(lambda: compile_context(source, codecs=["unregistered/1"]))

    def test_each_builtin_codec_recovers_the_same_context(self):
        records = [row(str(i), anchors=[{"shared": "共同条件" * 30}],
                       body={"source": "重复资料" * 30}) for i in range(12)]
        source = self.bundle(rows=records)
        restored = []
        for codec in ("aocx-expr/1", "aocx-expr-dict/1"):
            result = self.compiled(source, codecs=[codec])
            restored.append(recover_context(result["representation"]))
            self.assertEqual(verify_representation(source, result["representation"])["status"], "passed")
        self.assertEqual(restored[0], restored[1])
        self.assertEqual(restored[0]["records"], records)

    def test_modified_or_truncated_representation_is_rejected(self):
        source = self.bundle()
        registry = default_registry()
        codec = registry.get("aocx-expr/1")
        raw = self.compiled(source, codecs=[codec.id])["representation"]
        payload = codec.decode(raw)
        first_record(payload)["text"] = "Changed conclusion"
        modified = codec.encode(payload)
        self.assertEqual(verify_representation(source, modified)["status"], "failed")
        with self.assertRaises(ValueError):
            recover_context(modified)
        self.assertEqual(verify_representation(source, raw[:-8])["status"], "failed")

    def test_verifier_rejects_forged_content_even_with_consistent_local_digest(self):
        source = self.bundle()
        other = self.bundle("other", rows=[row(text="Different conditional conclusion")])
        valid_for_other = self.compiled(other)["representation"]
        self.assertEqual(verify_representation(source, valid_for_other)["status"], "failed")


if __name__ == "__main__":
    unittest.main()
