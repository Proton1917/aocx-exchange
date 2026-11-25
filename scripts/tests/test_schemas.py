"""Public representation schemas agree with executable formal examples."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

try:
    import jsonschema
except ImportError:
    jsonschema = None

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from aocx_core import decode_representation, parse_logic, validate_logic


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@unittest.skipUnless(jsonschema is not None, "jsonschema is an optional schema-check dependency")
class RepresentationSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schemas = {name: load_json(ROOT / "assets" / "schemas" / (name + ".schema.json"))
                       for name in ("manifest", "record", "relation", "logic", "representation")}
        cls.validators = {name: jsonschema.Draft202012Validator(value)
                          for name, value in cls.schemas.items()}
        cls.example = ROOT / "assets" / "examples" / "formal"
        cls.envelopes = {name: decode_representation((cls.example / (name + ".aocxrep")).read_bytes())
                         for name in ("context", "projection")}

    def assert_valid(self, name, value):
        errors = list(self.validators[name].iter_errors(value))
        self.assertEqual(errors, [], "\n".join(error.message for error in errors))

    def test_new_schemas_are_valid_and_self_contained(self):
        def inspect(value, root):
            if isinstance(value, dict):
                if "$ref" in value:
                    pointer = value["$ref"]
                    self.assertTrue(pointer.startswith("#/"), pointer)
                    target = root
                    for segment in pointer[2:].split("/"):
                        target = target[segment.replace("~1", "/").replace("~0", "~")]
                    self.assertIsInstance(target, (dict, bool))
                for child in value.values():
                    inspect(child, root)
            elif isinstance(value, list):
                for child in value:
                    inspect(child, root)
        for name in ("logic", "representation"):
            with self.subTest(schema=name):
                value = self.schemas[name]
                jsonschema.Draft202012Validator.check_schema(value)
                inspect(value, value)

    def test_formal_source_archive_validates(self):
        source = self.example / "source"
        manifest = load_json(source / "aocx.json")
        self.assert_valid("manifest", manifest)
        for kind in ("record", "relation"):
            for line in (source / manifest[kind + "s"]).read_text(encoding="utf-8").splitlines():
                value = json.loads(line)
                self.assert_valid(kind, value)
                if "logic" in value:
                    self.assert_valid("logic", value["logic"])

    def test_decoded_exact_and_projection_envelopes_validate(self):
        for name, envelope in self.envelopes.items():
            with self.subTest(representation=name):
                self.assert_valid("representation", envelope)
                self.assertEqual(envelope["context"], load_json(self.example / (name + ".json")))
        self.assert_valid("logic", load_json(self.example / "logic.json"))

    def test_known_logic_operators_require_their_declared_fields(self):
        examples = [
            ("变量", "name"), ('"原神"', "value"), ('Literal("开放文本")', "text"),
            ("SelfDev(x,y)", "args"), ('S[x="GenshinImpact"]', "bindings"),
            ("{y|P(y)}", "binder"), ("∀x.P(x)", "body"), ("∃x.P(x)", "binder"),
            ("¬P(x)", "body"), ("S⊢P(x)", "left"), ("P∧Q", "right"),
            ("P∨Q", "left"), ("P→Q", "right"), ("P↔Q", "left"),
            ("x∈D", "right"), ("x=y", "left"),
        ]
        for text, required in examples:
            with self.subTest(expression=text):
                node = parse_logic(text)
                wrapper = {"format": "aocx-logic/1", "expression": node}
                self.assert_valid("logic", wrapper)
                self.assertEqual(validate_logic(node)["status"], "passed")
                del node[required]
                self.assertFalse(self.validators["logic"].is_valid(wrapper))
                self.assertEqual(validate_logic(node)["status"], "failed")

    def test_known_logic_operand_types_are_checked(self):
        invalid = [
            {"op": "var", "name": ""}, {"op": "const", "value": {}},
            {"op": "call", "name": "P", "args": "x"},
            {"op": "bind", "name": "S", "bindings": [{"name": "x"}]},
            {"op": "set", "binder": 1, "body": {"op": "var", "name": "x"}},
            {"op": "and", "left": "P", "right": {"op": "var", "name": "Q"}},
        ]
        for node in invalid:
            with self.subTest(node=node):
                wrapper = {"format": "aocx-logic/1", "expression": node}
                self.assertFalse(self.validators["logic"].is_valid(wrapper))
                self.assertEqual(validate_logic(node)["status"], "failed")

    def test_unknown_ast_and_unicode_extensions_remain_open(self):
        for node in (
            {"op": "domain.future", "payload": {"自由": ["العربية", "∀", None, True, 1.0]}},
            {"op": "var", "name": "变量", "domain.units": "米 / m"},
        ):
            wrapper = {"format": "aocx-logic/1", "expression": node, "author.note": "保留未知信息"}
            self.assert_valid("logic", wrapper)
            self.assertEqual(validate_logic(node)["status"], "passed")
            envelope = deepcopy(self.envelopes["context"])
            envelope["context"]["records"][0]["logic"] = wrapper
            self.assert_valid("representation", envelope)

    def test_marked_malformed_ast_fails_representation_schema(self):
        envelope = deepcopy(self.envelopes["context"])
        envelope["context"]["records"][0]["logic"] = {
            "format": "aocx-logic/1", "expression": {"op": "and", "left": {"op": "var", "name": "P"}}}
        self.assertFalse(self.validators["representation"].is_valid(envelope))
        # Unmarked host-owned values retain the existing open-field contract.
        envelope["context"]["records"][0]["logic"] = {"host.language": "preserve opaquely"}
        self.assert_valid("representation", envelope)

    def test_malformed_contracts_and_source_bindings_are_rejected(self):
        mutations = [
            lambda p: p["contract"].pop("selection"),
            lambda p: p["contract"].update(fidelity="task"),
            lambda p: p["contract"].update(selection={"mode": "heads", "ids": ["formal/claim"]}),
            lambda p: p["contract"].update(omit_fields=["body"]),
            lambda p: p["source"].pop("snapshot_sha256"),
            lambda p: p["source"].update(snapshot_sha256="A" * 64),
            lambda p: p["source"].update(records_sha256="0123456789"),
            lambda p: p["source"].update(namespace=42),
            lambda p: p["recovery"].update(scope="archive-bytes"),
        ]
        for number, mutate in enumerate(mutations):
            with self.subTest(case=number):
                envelope = deepcopy(self.envelopes["context"])
                mutate(envelope)
                self.assertFalse(self.validators["representation"].is_valid(envelope))


if __name__ == "__main__":
    unittest.main()
