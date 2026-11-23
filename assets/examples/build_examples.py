"""Build three illustrative bundles using the installed AOCX core."""

from copy import deepcopy
from pathlib import Path
import hashlib
import importlib.util
import json
import sys

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent.parent
module_path = SKILL / "scripts" / "aocx.py"
spec = importlib.util.spec_from_file_location("aocx_example_core", module_path)
core = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = core
spec.loader.exec_module(core)


def ref(name):
    return {"id": name, "rev": "draft.1"}


def record(name, kind, text, **kwargs):
    return {"id": name, "rev": "draft.1", "kind": kind, "text": text, **kwargs}


def edge(name, source, target, kind, **kwargs):
    return {"id": name, "from": ref(source), "to": ref(target), "kind": kind, **kwargs}


software = [
    record("software/module", "code.unit", "样例模块负责解析十进制非负整数。",
           body={"purpose": "Parse an unsigned decimal integer",
                 "interface": {"name": "parse_count", "input": "string", "output": "integer or error"},
                 "constraints": ["Empty input returns an error", "Leading sign characters are rejected"]},
           state={"work": "draft", "knowledge": "declared"},
           scope="Illustrative contract; implementation and tests are not supplied."),
    record("software/requirement", "requirement", "有效输入仅包含一个或多个 ASCII 数字。",
           body={"pattern": "[0-9]+", "rationale": "Keep the example input contract explicit"},
           state={"knowledge": "declared"}),
    record("software/task", "task", "依照声明的接口实现解析函数，并执行列出的边界测试。",
           conditions=[{"text": "Use the stated input contract", "ref": ref("software/requirement")}],
           state={"work": "proposed"}, body={"owner": None, "deliverable": "parser implementation"}),
    record("software/check", "evidence", "拟执行空输入、符号输入和正常数字输入检查。",
           body={"executed": False, "result": None,
                 "cases": [{"input": "", "expected": "error"},
                           {"input": "+1", "expected": "error"},
                           {"input": "12", "expected": 12}]},
           state={"work": "proposed", "knowledge": "planned"}),
]
software_edges = [
    edge("software/edge1", "software/task", "software/module", "depends_on"),
    edge("software/edge2", "software/task", "software/check", "plans_check"),
]

math = [
    record("math/premise", "claim", "实数 a、b、c 满足 a>b 且 b>c。",
           state={"knowledge": "assumed"}, scope="a,b,c are real numbers.",
           body={"formula": "a>b \\land b>c"}),
    record("math/conclusion", "claim", "a>c。",
           conditions=[{"text": "Retain both inequalities in the premise", "ref": ref("math/premise")}],
           state={"knowledge": "derived"}, scope="Under the pinned premise over the real numbers.",
           body={"proof": "Apply transitivity of the strict order on the real numbers."}),
    record("math/idea", "research.idea", "探索这个例子在其他有序结构中的推广条件。",
           state={"knowledge": "speculative"},
           body={"possible_direction": "Inspect which order axioms the argument uses", "confidence": None},
           extensions={"author.free_note": "先保留这个想法，具体命题可在后续形成。"}),
]
math_edges = [edge("math/edge1", "math/conclusion", "math/premise", "assumes")]

document = [
    record("document/section", "document.section", "样例文档第二节说明浓度记录的单位和缺失值。",
           body={"title": "浓度记录方法", "purpose": "Explain the data fields"},
           anchors=[{"scheme": "section", "value": "2"}]),
    record("document/measurement", "lab.measurement", "样例工作表第 12 行等待录入浓度读数。",
           body={"value": None, "unit": "mg/L",
                 "interval": {"lower": 0, "upper": 5, "lower_closed": True,
                              "upper_closed": False, "unit": "mg/L", "role": "designed_range"}},
           anchors=[{"scheme": "sheet_cell", "sheet": "Measurements", "cell": "C12"}],
           state={"knowledge": "awaiting_measurement"}),
    record("document/source", "artifact", "样例外部数据表定位信息。",
           body={"uri": "https://example.invalid/data.csv", "availability": "external",
                 "embedded": False, "sha256": None},
           scope="Illustrative locator only; no dataset has been fetched."),
]
document_edges = [
    edge("document/edge1", "document/section", "document/measurement", "describes"),
    edge("document/edge2", "document/measurement", "document/source", "cites"),
]

for name, records, relations, profiles in (
    ("software", software, software_edges, ["core/1"]),
    ("math", math, math_edges, ["core/1"]),
    ("document", document, document_edges, ["core/1", "document/1"]),
):
    destination = HERE / name
    if destination.exists():
        existing_manifest = json.loads((destination / "aocx.json").read_text())
        existing_records = [json.loads(line) for line in
                            (destination / existing_manifest["records"]).read_text().splitlines() if line]
        existing_relations = [json.loads(line) for line in
                              (destination / existing_manifest["relations"]).read_text().splitlines() if line]
        if existing_records != records or existing_relations != relations:
            raise RuntimeError(f"Existing example differs from its definition: {name}")
    else:
        core.create_bundle(records, relations, destination, f"example:{name}",
                           profiles=profiles, required_profiles=["core/1"],
                           extensions={"example": True, "asserted_execution": False})

# The example's short phrase is human-authored. The unassessed state makes its
# lack of a paired-model comprehension benchmark explicit.
manifest = json.loads((HERE / "math" / "aocx.json").read_text())
source_hash = hashlib.sha256((HERE / "math" / manifest["records"]).read_bytes()).hexdigest()
relation_hash = hashlib.sha256((HERE / "math" / manifest["relations"]).read_bytes()).hexdigest()
idea = math[2]
view = {
    "format": "AOCX-VIEW", "version": "1.0", "codec": "babeltele-view/1",
    "namespace": manifest["namespace"],
    "source_records_sha256": source_hash, "source_relations_sha256": relation_hash,
    "task": "Keep the speculative direction available without promoting it to a result.",
    "producer": {"model": "none:manual-example", "prompt_sha256": hashlib.sha256(
        b"Illustrative unassessed task-conditioned view").hexdigest()},
    "consumer": {"model": "example:unbound", "tokenizer": "example:unbound"},
    "entries": [{"ref": ref("math/idea"), "text": "Explore order-axiom transfer; speculative.",
                 "protected": deepcopy({k: v for k, v in idea.items()
                                        if k not in {"text", "body", "extensions"}})}],
    "evaluation": {"status": "unassessed"},
    "example_bundle": "math",
}
(HERE / "math_view.babeltele.json").write_text(json.dumps(view, ensure_ascii=False, indent=2) + "\n")
print("Built software, math and document examples plus one unassessed view.")
