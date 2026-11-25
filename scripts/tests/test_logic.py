"""Logic syntax preserves authored structure and opaque domain extensions."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aocx_core import logic
from aocx_core.common import AOCXError, _content


class LogicTests(unittest.TestCase):
    def roundtrip(self, node):
        self.assertEqual(logic.validate_logic(node)["status"], "passed")
        self.assertEqual(_content(logic.parse_logic(logic.render_logic(node))), _content(node))

    def test_user_scope_and_set_builder(self):
        text = 'S[x="GenshinImpact"]⊢x∈{y|SelfDev(Dev(x),y)∧OpenAdvGame(y)}'
        node = logic.parse_logic(text)
        self.assertEqual(node["op"], "sequent")
        self.assertEqual(node["left"]["op"], "bind")
        self.assertEqual(node["left"]["bindings"][0]["value"]["value"], "GenshinImpact")
        self.assertEqual(node["right"]["right"]["op"], "set")
        self.roundtrip(node)

    def test_connective_precedence_and_direction(self):
        node = logic.parse_logic("A∧B∨C→D")
        self.assertEqual(node["op"], "implies")
        self.assertEqual(node["left"]["op"], "or")
        self.assertEqual(node["left"]["left"]["op"], "and")
        self.assertEqual(node["right"], {"op": "var", "name": "D"})
        self.roundtrip(node)
        self.roundtrip(logic.parse_logic("A→B→C"))

    def test_quantifiers_negation_unicode(self):
        for text in ("∀x.(P(x)→Q(x))", "∃α.(P(α)∧¬Q(α))", "模型[变量=\"原神\"]⊢自研(变量)", "P()↔Q(x=1)"):
            self.roundtrip(logic.parse_logic(text))

    def test_quantifier_scope_survives_surrounding_operators(self):
        quantified = {"op": "forall", "binder": "x", "body": {
            "op": "call", "name": "P", "args": [{"op": "var", "name": "x"}]}}
        sibling = {"op": "call", "name": "Q", "args": []}
        for op in ("and", "or", "implies", "sequent", "eq"):
            self.roundtrip({"op": op, "left": quantified, "right": sibling})
            self.roundtrip({"op": op, "left": sibling, "right": quantified})
        self.roundtrip({"op": "call", "name": "Meta", "args": [quantified, sibling]})

    def test_opaque_literal_retains_original(self):
        self.roundtrip({"op": "literal", "text": "可以研究这个想法。∀ perhaps\n\"x\""})

    def test_unknown_nodes_and_extensions_survive(self):
        node = {"op": "domain/future", "payload": {"truth": None}, "extensions": {"state": "exploratory"}}
        self.assertEqual(logic.validate_logic(node)["opaque_nodes"], ["domain/future"])
        self.roundtrip(node)
        self.roundtrip({"op": "var", "name": "x", "extensions": {"unit": "m"}})
        self.roundtrip({"op": "call", "name": "arbitrary-domain/name", "args": [{"op": "var", "name": "x"}]})

    def test_reserved_names_are_escaped(self):
        for name in ("AST", "Literal", "true", "has space"):
            self.roundtrip({"op": "var", "name": name})
            self.roundtrip({"op": "call", "name": name, "args": []})

    def test_constants_preserve_json_types(self):
        for value in (None, True, False, 1, 1.0, -0.0, 10**30, "x", "中文"):
            self.roundtrip({"op": "const", "value": value})

    def test_malformed_logic_is_rejected(self):
        for text in ("P(x", "x∈{y|}", "S[x=1,x=2]⊢P(x)", "AST({\"op\":\"var\",\"op\":\"const\"})", "Literal(1)", "x y", "∀.P(x)"):
            with self.subTest(text=text), self.assertRaises(AOCXError):
                logic.parse_logic(text)
        for node in ({}, {"op": "var"}, {"op": "call", "name": "P", "args": "x"}, {"op": "const", "value": {}}, {"op": "var", "name": 1}):
            self.assertEqual(logic.validate_logic(node)["status"], "failed")

    def test_limits_are_explicit(self):
        with patch.object(logic, "MAX_DEPTH", 3):
            with self.assertRaises(AOCXError):
                logic.parse_logic("((((((x))))))")
        with patch.object(logic, "MAX_TEXT", 3):
            with self.assertRaises(AOCXError):
                logic.parse_logic("abcdef")


if __name__ == "__main__":
    unittest.main()
