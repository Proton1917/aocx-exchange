"""Create, compile, verify and independently recover a formal AOCX example.

Run with --out PATH to produce a new example directory. Existing identical
generated files are accepted, making the checked-in example reproducible.
The executable workflow uses only the Python standard library.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "scripts"))

from aocx_core import (compile_context, create_bundle, make_contract,
                       parse_logic, recover_context, render_logic,
                       verify_representation)


EXPRESSION = 'zh(S[x="GenshinImpact"]⊢x∈{y|SelfDev(Dev(x),y)∧OpenAdvGame(y)})'
SOURCE_TEXT = (
    "原神（GenshinImpact）：本例声明它是开发商自研的开放世界冒险游戏。\n"
    "This is an authored classification example with explicit domain predicates.\n"
    "P' = " + EXPRESSION + "\n"
    "自由备注 / open note: 保留原文、条件、引用、未知字段与探索性想法。\n"
)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")


def ref(name, revision="1"):
    return {"id": "formal/" + name, "rev": revision}


def record(name, text, revision="1", **values):
    return {**ref(name, revision), "kind": "claim", "text": text, **values}


def relation(name, source, target, kind, source_rev="1", target_rev="1", **values):
    return {"id": "formal/" + name, "kind": kind,
            "from": ref(source, source_rev), "to": ref(target, target_rev), **values}


def example_data():
    logic = {
        "format": "aocx-logic/1", "expression": parse_logic(EXPRESSION),
        "interpretation": "Authored domain notation; the reader supplies predicate meanings.",
        "symbols": {
            "zh": "A presentation annotation retaining the expression as its argument.",
            "S": "The author-defined context binding x in this sequent.",
            "Dev": "Developer of the named game.",
            "SelfDev": "The developer named by the first argument developed the second argument.",
            "OpenAdvGame": "The argument belongs to the authored open-world adventure-game category.",
            "y": "The set-builder variable ranging over games.",
        },
    }
    records = [
        record("vocabulary", "符号含义由作者声明；predicate names remain domain-owned.",
               kind="domain.definition", state={"knowledge": "declared"},
               scope="Illustrative game taxonomy; external factual verification is separate.",
               vocabulary=deepcopy(logic["symbols"])),
        record("premise", "在本例词汇下，作者声明 SelfDev 与 OpenAdvGame 两个条件。",
               state={"knowledge": "assumed"},
               conditions=[{"text": "Use the declared domain vocabulary.", "ref": ref("vocabulary")}],
               logic={"format": "aocx-logic/1", "expression": parse_logic(
                   'SelfDev(Dev("GenshinImpact"),"GenshinImpact")∧OpenAdvGame("GenshinImpact")')},
               body={"explanation": "This fixed revision is the premise used by the claim."}),
        record("premise", "下一次分类修订仍在研究中；the earlier premise remains pinned.", "2",
               state={"work": "draft", "knowledge": "open"},
               body={"open_question": "How should the category boundary be refined?"}),
        record("claim", SOURCE_TEXT.splitlines()[0] + " The conclusion uses premise revision 1.",
               logic=logic, state={"knowledge": "declared"},
               scope="Under formal/premise@1 and the authored symbol interpretation.",
               conditions=[{"text": "Retain the premise at its cited revision.", "ref": ref("premise")}],
               anchors=[{"scheme": "asset", "path": "attachments/source.txt", "line": 1}],
               body={"original": SOURCE_TEXT}, extensions={"author.note": "可自由保留多种语言。"},
               **{"future.domain": {"labels": ["原神", "GenshinImpact", "∀", "自由"],
                                    "reviewed": False, "confidence": None, "revision_weight": 1.0}}),
        record("idea", "探索同一逻辑结构的其他领域解释；keep this as an open research idea.",
               kind="research.idea", state={"knowledge": "speculative"},
               body={"question": "Which reader tasks would establish useful semantic equivalence?"}),
    ]
    relations = [
        relation("claim-premise", "claim", "premise", "depends_on"),
        relation("premise-vocabulary", "premise", "vocabulary", "assumes"),
        relation("premise-revision", "premise", "premise", "supersedes", source_rev="2"),
        relation("exploration", "claim", "idea", "domain.inspires",
                 **{"future.relation": {"direction": "claim-to-idea", "note": "开放关系类型"}}),
    ]
    return records, relations, logic


def build_example(destination):
    records, relations, logic = example_data()
    exact = make_contract()
    projection = make_contract("projection", select=["formal/claim"])
    with tempfile.TemporaryDirectory(prefix="aocx-formal-source-") as temporary:
        source = Path(temporary) / "source"
        create_bundle(
            records, relations, source, "example:formal",
            heads={"formal/vocabulary": "1", "formal/premise": "2", "formal/claim": "1", "formal/idea": "1"},
            assets={"attachments/source.txt": SOURCE_TEXT.encode("utf-8")},
            origins=[{"id": "authored-source", "format": "text/plain", "asset": "attachments/source.txt", "root": ""}],
            extensions={"example": True, "domain_semantics": "author-declared", "display_language": "自由 / open"},
        )
        full = compile_context(source, exact)
        selected = compile_context(source, projection)
        verified_full = verify_representation(source, full["representation"], exact)
        verified_selected = verify_representation(source, selected["representation"], projection)
        if verified_full["status"] != "passed" or verified_selected["status"] != "passed":
            raise RuntimeError("Example representation failed verification")
        archive_files = {"source/" + path.relative_to(source).as_posix(): path.read_bytes()
                         for path in source.rglob("*") if path.is_file()}

    # The source path and attachment are now gone. Both inverse operations
    # receive only representation bytes and the installed decoder registry.
    recovered = recover_context(full["representation"])
    projected = recover_context(selected["representation"])
    if json_bytes(recovered["records"]) != json_bytes(records) or recovered["relations"] != relations:
        raise RuntimeError("Recovered logical values differ from the authored source")
    if {(r["id"], r["rev"]) for r in projected["records"]} != {
            ("formal/claim", "1"), ("formal/premise", "1"), ("formal/vocabulary", "1")}:
        raise RuntimeError("Projection lost the historical prerequisite closure")
    if "formal/premise" in projected["heads"]:
        raise RuntimeError("A historical premise was incorrectly promoted to a current head")
    if any("body" in r or "extensions" in r for r in projected["records"]):
        raise RuntimeError("Declared omissions were not applied")

    report = {
        "exact": {"compile": full["report"], "verify": verified_full},
        "projection": {"compile": selected["report"], "verify": verified_selected},
        "independent_recovery": {"status": "passed", "source_path_removed": True,
                                 "scope": "context-values"},
        "attachment": {"path": "source/attachments/source.txt", "bytes": len(SOURCE_TEXT.encode("utf-8")),
                       "sha256": hashlib.sha256(SOURCE_TEXT.encode("utf-8")).hexdigest(),
                       "storage": "separate-source-archive"},
    }
    files = {
        **archive_files,
        "context.aocxrep": full["representation"], "projection.aocxrep": selected["representation"],
        "context.json": json_bytes(recovered), "projection.json": json_bytes(projected),
        "logic.json": json_bytes(logic), "verification.json": json_bytes(report),
        "expression.txt": ("P' = " + EXPRESSION + "\n" + render_logic(logic["expression"]) + "\n").encode("utf-8"),
    }
    destination = Path(destination)
    for relative, raw in files.items():
        target = destination / relative
        if target.exists() and target.read_bytes() != raw:
            raise ValueError(f"Generated content differs at {target}; choose an empty --out directory")
    for relative, raw in files.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    return {"status": "passed", "directory": str(destination),
            "selected_codec": full["report"]["selected_codec"],
            "bytes": full["report"]["bytes"], "independent_recovery": "passed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=HERE / "formal")
    args = parser.parse_args()
    print(json.dumps(build_example(args.out), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
