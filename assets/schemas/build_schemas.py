"""Regenerate archive schemas, embedding the authored open logic schema.

logic.schema.json and representation.schema.json are maintained as schema
sources. The generated record and document schemas reuse the logic definition.
"""

from copy import deepcopy
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
DIALECT = "https://json-schema.org/draft/2020-12/schema"
STRING = {"type": "string"}
NAME = {"type": "string", "minLength": 1}
REF = {"type": "object", "required": ["id", "rev"],
       "properties": {"id": NAME, "rev": NAME}, "additionalProperties": True}
RELATIVE_PATH = {
    "type": "string", "minLength": 1,
    "pattern": r"^[^/\\:\u0000-\u001f]+(?:/[^/\\:\u0000-\u001f]+)*$",
    "not": {"pattern": r"(?:^|/)\.{1,2}(?:/|$)"},
}
HASH = {"type": "string", "pattern": "^[0-9a-f]{64}$"}


def schema(name, title, properties, required, defs=None):
    result = {
        "$schema": DIALECT, "$id": f"urn:aocx:schema:{name}:1.0",
        "title": title, "type": "object", "properties": properties,
        "required": required, "additionalProperties": True,
    }
    if defs:
        result["$defs"] = defs
    return result


record = schema("record", "AOCX/1 open-vocabulary record", {
    "id": NAME, "rev": NAME, "kind": NAME, "text": STRING,
    "body": {},
    "state": {"type": "object", "properties": {"work": STRING, "knowledge": STRING},
              "additionalProperties": True},
    "conditions": {"type": "array", "items": {
        "type": "object", "required": ["text"],
        "properties": {"text": STRING, "ref": {"$ref": "#/$defs/ref"}},
        "additionalProperties": True,
    }},
    "scope": STRING,
    "provenance": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
    "anchors": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
    "extensions": {},
}, ["id", "rev", "kind", "text"], {"ref": REF})

# Only an explicit format marker opts a field into the logic contract.
# Other existing values of an open `logic` field retain their own vocabulary.
logic = json.loads((ROOT / "logic.schema.json").read_text(encoding="utf-8"))
record["$defs"].update(deepcopy(logic["$defs"]))
record["properties"]["logic"] = {
    "if": {"type": "object", "required": ["format"],
           "properties": {"format": {"const": "aocx-logic/1"}}},
    "then": {key: deepcopy(value) for key, value in logic.items()
             if key not in ("$schema", "$id", "$defs")},
}

relation = schema("relation", "AOCX/1 typed directed relation", {
    "id": NAME, "kind": NAME,
    "from": {"$ref": "#/$defs/ref"}, "to": {"$ref": "#/$defs/ref"},
    "body": {}, "extensions": {},
}, ["id", "from", "to", "kind"], {"ref": REF})

manifest = schema("manifest", "AOCX/1 bundle manifest", {
    "format": {"const": "AOCX"}, "version": {"const": "1.0"},
    "namespace": NAME,
    "records": {"$ref": "#/$defs/path"},
    "relations": {"$ref": "#/$defs/path"},
    "heads": {"type": "object", "additionalProperties": NAME},
    "profiles": {"type": "array", "items": NAME, "uniqueItems": True},
    "required_profiles": {"type": "array", "items": NAME, "uniqueItems": True},
    "assets": {"type": "array", "items": {"$ref": "#/$defs/asset"}},
    "origins": {"type": "array", "items": {"$ref": "#/$defs/origin"}},
    "external_resources": {"type": "array", "items": {
        "type": "object", "additionalProperties": True,
        "properties": {"uri": STRING, "availability": STRING, "role": STRING},
    }},
    "extensions": {},
}, ["format", "version", "namespace", "records", "relations", "heads",
    "profiles", "required_profiles", "assets", "origins"], {
    "path": RELATIVE_PATH,
    "asset": {
        "type": "object", "required": ["path", "sha256", "bytes", "role"],
        "properties": {"path": {"$ref": "#/$defs/path"}, "sha256": HASH,
                       "bytes": {"type": "integer", "minimum": 0}, "role": NAME},
        "additionalProperties": True,
    },
    "origin": {
        "type": "object", "required": ["id", "format", "asset", "root"],
        "properties": {"id": NAME, "format": NAME,
                       "asset": {"$ref": "#/$defs/path"}, "root": STRING},
        "additionalProperties": True,
    },
})

view = schema("babeltele-view", "AOCX/1 task-conditioned experimental view", {
    "format": {"const": "AOCX-VIEW"}, "version": {"const": "1.0"},
    "codec": {"const": "babeltele-view/1"}, "source_records_sha256": HASH,
    "namespace": NAME, "source_relations_sha256": HASH,
    "task": STRING,
    "producer": {"type": "object", "required": ["model", "prompt_sha256"],
                 "properties": {"model": NAME, "prompt_sha256": HASH},
                 "additionalProperties": True},
    "consumer": {"type": "object", "required": ["model", "tokenizer"],
                 "properties": {"model": NAME, "tokenizer": NAME},
                 "additionalProperties": True},
    "entries": {"type": "array", "items": {
        "type": "object", "required": ["ref", "text", "protected"],
        "properties": {"ref": {"$ref": "#/$defs/ref"}, "text": STRING,
                       "protected": {}}, "additionalProperties": True,
    }},
    "evaluation": {"type": "object", "required": ["status"],
                   "properties": {"status": {"enum": ["unassessed", "passed"]},
                                  "report": {"anyOf": [RELATIVE_PATH, {"type": "null"}]}},
                   "allOf": [{"if": {"properties": {"status": {"const": "passed"}}, "required": ["status"]},
                              "then": {"required": ["report"], "properties": {"report": RELATIVE_PATH}}}],
                   "additionalProperties": True},
}, ["format", "version", "codec", "namespace", "source_records_sha256", "source_relations_sha256", "task", "producer",
    "consumer", "entries", "evaluation"], {"ref": REF})

evaluation = schema("view-evaluation", "AOCX view and source bound evaluation evidence", {
    "format": {"const": "AOCX-EVALUATION"}, "version": {"const": "1.0"},
    "view_sha256": HASH, "source_snapshot_sha256": HASH,
}, ["format", "version", "view_sha256", "source_snapshot_sha256"])
evaluation["description"] = (
    "A hashed bundle asset binding the complete view except its evaluation member "
    "and the full source context snapshot. Evidence fields are supplied by the host. "
    "A bound report requires host evaluation before semantic eligibility is granted.")

# This optional domain schema introduces local shape checks without closing
# the core's record kinds, states or extension vocabulary.
document = deepcopy(record)
document["$id"] = "urn:aocx:schema:document-profile:1.0"
document["title"] = "Optional document/1 profile"
document["allOf"] = [{
    "if": {"properties": {"kind": {"const": "lab.measurement"}}, "required": ["kind"]},
    "then": {"required": ["body"], "properties": {"body": {
        "type": "object", "required": ["unit"],
        "properties": {"unit": NAME, "value": {"type": ["number", "null"]}},
        "additionalProperties": True,
    }}},
}]

for filename, value in {
    "record.schema.json": record,
    "relation.schema.json": relation,
    "manifest.schema.json": manifest,
    "babeltele-view.schema.json": view,
    "document-profile.schema.json": document,
    "view-evaluation.schema.json": evaluation,
}.items():
    (ROOT / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print("Generated six self-contained JSON Schema 2020-12 files; retained two authored schemas.")
