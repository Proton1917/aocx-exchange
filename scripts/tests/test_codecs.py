"""Executable contracts for reversible expression and dictionary codecs."""
from copy import deepcopy
from pathlib import Path
import random
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aocx_core import codecs
from aocx_core.common import AOCXError, _content
from aocx_core.logic import parse_logic


class CodecTests(unittest.TestCase):
    def setUp(self):
        self.registry = codecs.default_registry()
        self.envelope = {
            "format": "AOCX-REP", "version": "1.0",
            "contract": {"recovery": "exact"}, "source": {"namespace": "中文-namespace"},
            "context": {"namespace": "中文-namespace", "records": [
                {"id": "α", "rev": "1", "kind": "探索", "text": "∀x 中文 English\n\"quote\"\\slash",
                 "body": {"null": None, "bool": True, "int": 1, "float": 1.0, "minus": -0.0}},
                {"id": "β", "rev": "1", "kind": "claim", "text": "x > 0"}],
                "relations": [{"id": "r", "from": {"id": "α", "rev": "1"}, "kind": "depends_on",
                               "to": {"id": "β", "rev": "1"}, "future": [None, 0, False]}],
                "heads": {"α": "1", "β": "1"}, "profiles": ["core/1"], "required_profiles": ["core/1"]},
            "future": {"nested": [[], {}, {"missing": None}]},
        }

    def assert_roundtrip(self, value):
        for identifier in self.registry.ids:
            with self.subTest(codec=identifier):
                codec = self.registry.get(identifier)
                raw = codec.encode(value)
                self.assertEqual(_content(codec.decode(raw)), _content(value))
                self.assertEqual(_content(codecs.decode_representation(raw)), _content(value))

    def test_mixed_language_unknown_fields_and_typed_values(self):
        self.assert_roundtrip(self.envelope)

    def test_formal_constructors_and_logic_are_on_wire(self):
        value = deepcopy(self.envelope)
        ast = parse_logic('S[x="GenshinImpact"]⊢x∈{y|SelfDev(Dev(x),y)∧OpenAdvGame(y)}')
        value["context"]["records"][0]["logic"] = {"format": "aocx-logic/1", "expression": ast, "domain": "games"}
        self.assert_roundtrip(value)
        raw = self.registry.get("aocx-expr/1").encode(value).decode()
        for token in ("Rep(", "Context(", "Record(", "Relation(", "Ref(", "Logic(", "⊢", "∈", "∧"):
            self.assertIn(token, raw)

    def test_dictionary_compresses_repeated_values(self):
        value = {"data": [{"long-field-name": "a repeated phrase in mixed language 中文"} for _ in range(100)]}
        plain = self.registry.get("aocx-expr/1").encode(value)
        dictionary = self.registry.get("aocx-expr-dict/1").encode(value)
        self.assertLess(len(dictionary), len(plain))
        self.assertIn(b"@0", dictionary)
        self.assert_roundtrip(value)

    def test_expanded_string_budget_counts_dictionary_definitions_and_references(self):
        codec = self.registry.get("aocx-expr-dict/1")
        cases = [
            ('Dict(["中文"],{"v":[@0,@0]})', {"v": ["中文", "中文"]}, 19),
            ('Dict(["long"],{@0:@0})', {"long": "long"}, 12),
        ]
        for body, expected, size in cases:
            raw = b"AOCX/1 aocx-expr-dict/1\n" + body.encode("utf-8")
            with self.subTest(body=body), patch.object(codecs, "MAX_EXPANDED_STRING_BYTES", size):
                self.assertEqual(codec.decode(raw), expected)
            with self.subTest(over_limit=body), patch.object(codecs, "MAX_EXPANDED_STRING_BYTES", size - 1):
                with self.assertRaises(AOCXError) as caught:
                    codec.decode(raw)
                self.assertEqual(caught.exception.diagnostic["code"], "codec_limit")

    def test_expanded_string_budget_covers_json_keys_and_generated_ast_strings(self):
        cases = [
            ("json/1", '{"汉":"字"}', 6),
            ("aocx-expr/1", 'Ref("x","1")', 7),
            # Formula byte + wrapper strings + {"op":"var","name":"x"}.
            ("aocx-expr/1", 'Logic("x",{})', 39),
            # One dictionary definition, "items", and two full Logic values.
            ("aocx-expr-dict/1", 'Dict(["x"],{"items":[Logic(@0,{}),Logic(@0,{})]})', 84),
        ]
        for identifier, body, size in cases:
            raw = f"AOCX/1 {identifier}\n{body}".encode("utf-8")
            codec = self.registry.get(identifier)
            with self.subTest(codec=identifier, body=body), patch.object(codecs, "MAX_EXPANDED_STRING_BYTES", size):
                self.assertIsInstance(codec.decode(raw), dict)
            with self.subTest(over_limit=body), patch.object(codecs, "MAX_EXPANDED_STRING_BYTES", size - 1):
                with self.assertRaises(AOCXError) as caught:
                    codec.decode(raw)
                self.assertEqual(caught.exception.diagnostic["code"], "codec_limit")

    def test_quoted_malformed_or_oversized_logic_remains_json(self):
        sample = {"format": "aocx-logic/1", "expression": {}}
        value = {"body": {"invalid_sample": sample}}
        self.assert_roundtrip(value)
        with patch.object(codecs, "render_logic", side_effect=AssertionError("JSON encoding must not interpret logic")):
            codec = self.registry.get("json/1")
            self.assertEqual(codec.decode(codec.encode(value)), value)
        sample = {"format": "aocx-logic/1", "expression": {"op": "var", "name": "long_variable_name"}}
        with patch("aocx_core.logic.MAX_TEXT", 8):
            self.assert_roundtrip({"body": {"quoted_sample": sample}})

    def test_logic_fallback_retains_json_shape_and_resource_limits(self):
        for identifier in self.registry.ids:
            codec = self.registry.get(identifier)
            with self.subTest(codec=identifier):
                invalid = {"body": {"format": "aocx-logic/1", "expression": {"op": "future", "value": (1, 2)}}}
                with self.assertRaises(AOCXError) as caught:
                    codec.encode(invalid)
                self.assertEqual(caught.exception.diagnostic["code"], "invalid_json_value")
                with patch.object(codecs, "MAX_NODES", 3):
                    with self.assertRaises(AOCXError) as caught:
                        codec.encode({"sample": {"format": "aocx-logic/1", "expression": {}}})
                    self.assertEqual(caught.exception.diagnostic["code"], "codec_limit")

    def test_empty_and_small_envelopes(self):
        for value in ({}, {"x": ""}, {"x": None}, {"x": [True, 1, 1.0, False, 0, 0.0]}):
            self.assert_roundtrip(value)

    def test_generated_json_roundtrips(self):
        rng = random.Random(1917)
        values = [None, False, True, 0, 1, -1, 1.25, -0.0, 10**40, "中文", "⊢", "\n\t\\\"", "@0", "Record("]
        def generate(depth):
            if depth == 0 or rng.randrange(3) == 0:
                return rng.choice(values)
            if rng.randrange(2):
                return [generate(depth - 1) for _ in range(rng.randrange(5))]
            return {f"key-{i}": generate(depth - 1) for i in range(rng.randrange(5))}
        for _ in range(40):
            self.assert_roundtrip({"data": generate(4)})

    def test_malformed_expression_is_rejected(self):
        bodies = ['{"x":1,"x":2}', 'Record("a","1","claim","t",{"id":"b"})',
                  'Ref("a")', 'Exec("touch")', '{"x":01}', '{"x":NaN}',
                  '{"x":1e999}', '{"x":"\\ud800"}', '{} trailing', '{[]:1}',
                  '{"x":@0}', '[]', '{"x":"unterminated}', 'Logic("x",{"format":"bad"})']
        codec = self.registry.get("aocx-expr/1")
        for body in bodies:
            with self.subTest(body=body), self.assertRaises((AOCXError, ValueError)):
                codec.decode(b"AOCX/1 aocx-expr/1\n" + body.encode())

    def test_malformed_dictionary_is_rejected(self):
        codec = self.registry.get("aocx-expr-dict/1")
        for body in ('Dict(["x","x"],{})', 'Dict([true],{})', 'Dict(["x"],{@1:0})',
                     'Dict(["x"],{@99999999999999999:0})', 'Dict([@0],{})'):
            with self.subTest(body=body), self.assertRaises(AOCXError):
                codec.decode(b"AOCX/1 aocx-expr-dict/1\n" + body.encode())

    def test_json_codec_enforces_strict_grammar(self):
        codec = self.registry.get("json/1")
        for body in ('{"x":1,"x":2}', '{"x":NaN}', 'Ref("x","1")', '{"x":@0}'):
            with self.subTest(body=body), self.assertRaises(ValueError):
                codec.decode(b"AOCX/1 json/1\n" + body.encode())

    def test_wire_codec_binding(self):
        raw = self.registry.get("json/1").encode({})
        with self.assertRaises(AOCXError):
            self.registry.get("aocx-expr/1").decode(raw)
        with self.assertRaises(AOCXError):
            codecs.decode_representation(b"AOCX/1 unknown/1\n{}")
        with self.assertRaises(AOCXError):
            codecs.decode_representation(b"{}")

    def test_limits_and_non_json_values(self):
        codec = self.registry.get("aocx-expr/1")
        for value in ({"x": (1, 2)}, {1: "key"}, {"x": float("inf")}, {"x": "\ud800"}):
            with self.subTest(value=repr(value)), self.assertRaises((AOCXError, UnicodeError)):
                codec.encode(value)
        with patch.object(codecs, "MAX_DEPTH", 3):
            with self.assertRaises(AOCXError):
                codec.encode({"x": [[[[[0]]]]]})
            with self.assertRaises(AOCXError):
                codec.decode(b'AOCX/1 aocx-expr/1\n{"x":[[[[[0]]]]]}')
        with patch.object(codecs, "MAX_WIRE_BYTES", 8):
            with self.assertRaises(AOCXError):
                codec.encode({})

    def test_registry_duplicate_and_unknown(self):
        self.assertEqual(self.registry.ids, ("aocx-expr/1", "aocx-expr-dict/1", "json/1"))
        with self.assertRaises(AOCXError):
            self.registry.register(self.registry.get("json/1"))
        with self.assertRaises(AOCXError):
            self.registry.get("absent/1")


if __name__ == "__main__":
    unittest.main()
