"""Versioned records, relations and reusable prerequisite graph indexing."""
from __future__ import annotations

from collections import deque

from .common import FOLLOW, _content, _ref, _str, fail


def _validate_records(records, relations):
    if not isinstance(records, list) or not isinstance(relations, list):
        fail("invalid_type", "Records and relations must be arrays")
    index = {}
    for r in records:
        if not isinstance(r, dict):
            fail("invalid_record", "Record must be an object")
        for key in ("id", "rev", "kind", "text"):
            _str(r.get(key), "record." + key, empty=(key == "text"))
        key = r["id"], r["rev"]
        if key in index:
            code = "duplicate_record" if _content(index[key]) == _content(r) else "conflicting_record"
            fail(code, "Repeated record identity and revision", id=key[0], rev=key[1])
        index[key] = r
        if "state" in r:
            if not isinstance(r["state"], dict):
                fail("invalid_type", "Record state must be an object", id=r["id"])
            for field in ("work", "knowledge"):
                if field in r["state"]:
                    _str(r["state"][field], "state." + field)
        if "scope" in r:
            _str(r["scope"], "scope", empty=True)
        if "provenance" in r and (not isinstance(r["provenance"], list) or any(not isinstance(p, dict) for p in r["provenance"])):
            fail("invalid_type", "Provenance must be an array of objects", id=r["id"])
        logic = r.get("logic")
        if isinstance(logic, dict) and logic.get("format") == "aocx-logic/1":
            from .logic import validate_logic
            report = validate_logic(logic.get("expression"))
            if report["status"] != "passed":
                fail("invalid_logic", "Explicit logic declaration has an invalid AST", id=r["id"], errors=report["errors"])
        conditions = r.get("conditions", [])
        if not isinstance(conditions, list):
            fail("invalid_type", "Conditions must be an array", id=r["id"])
        for c in conditions:
            if not isinstance(c, dict):
                fail("invalid_type", "Condition must be an object", id=r["id"])
            _str(c.get("text"), "condition.text", empty=True)
            if "ref" in c:
                _ref(c["ref"], "condition.ref")
    for key, r in index.items():
        for c in r.get("conditions", []):
            if "ref" in c and _ref(c["ref"], "condition.ref") not in index:
                fail("dangling_ref", "Condition references an absent revision", id=key[0], ref=c["ref"])
    edge_ids, supersedes = {}, {}
    for edge in relations:
        if not isinstance(edge, dict):
            fail("invalid_relation", "Relation must be an object")
        _str(edge.get("id"), "relation.id")
        _str(edge.get("kind"), "relation.kind")
        if edge["id"] in edge_ids:
            code = "duplicate_relation" if _content(edge_ids[edge["id"]]) == _content(edge) else "conflicting_relation"
            fail(code, "Repeated relation identity", id=edge["id"])
        edge_ids[edge["id"]] = edge
        before = _ref(edge.get("from"), "relation.from")
        after = _ref(edge.get("to"), "relation.to")
        if before not in index or after not in index:
            fail("dangling_ref", "Relation references an absent revision", id=edge["id"])
        if edge["kind"] == "supersedes":
            if before[0] != after[0]:
                fail("supersedes_identity_mismatch", "supersedes links revisions of one logical record id", id=edge["id"])
            supersedes.setdefault(before, []).append(after)
    # Only revision replacement is required to be acyclic; research/code graphs may cycle.
    indegree = {k: 0 for k in index}
    for targets in supersedes.values():
        for target in targets:
            indegree[target] += 1
    ready = deque(k for k, degree in indegree.items() if degree == 0)
    visited = 0
    while ready:
        node = ready.popleft()
        visited += 1
        for target in supersedes.get(node, []):
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
    if visited != len(index):
        fail("supersedes_cycle", "Revision replacement relation contains a cycle")
    return index



class GraphIndex:
    """Index fixed-revision prerequisites once for repeated context selections.

    The caller owns the validated snapshot and keeps it unchanged for this
    index's lifetime. Relation direction remains user -> prerequisite.
    """

    def __init__(self, records, relations, index=None):
        self.records = _validate_records(records, relations) if index is None else index
        adjacency = {}
        for edge in relations:
            if edge["kind"] in FOLLOW:
                adjacency.setdefault(_ref(edge["from"], "from"), []).append(_ref(edge["to"], "to"))
        for key, record in self.records.items():
            for condition in record.get("conditions", []):
                if "ref" in condition:
                    adjacency.setdefault(key, []).append(_ref(condition["ref"], "condition.ref"))
        self.adjacency = {key: tuple(targets) for key, targets in adjacency.items()}

    def closure(self, selected):
        needed = set(selected)
        for key in needed:
            if key not in self.records:
                fail("unknown_selection", "Selected revision is absent", id=key[0], rev=key[1])
        queue = deque(needed)
        while queue:
            for target in self.adjacency.get(queue.popleft(), ()):
                if target not in needed:
                    needed.add(target)
                    queue.append(target)
        return needed


def _closure(data, selected):
    graph = data.get("graph")
    if graph is None:
        graph = GraphIndex(data["records"], data["relations"], data["index"])
    return graph.closure(selected)
