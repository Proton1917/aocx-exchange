"""GBCX/1 primary-record projection into AOCX/1.

This adapter reads data only. The enclosing AOCX importer retains the exact
legacy archive separately. Projection does not certify mathematics or execute
any file. Every primary legacy record is retained, unchanged, in ``body``.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json
from typing import Any


TABLES = (
    ("claims.jsonl", "claim"),
    ("methods.jsonl", "method"),
    ("frontier.jsonl", "task"),
    ("sources.jsonl", "source"),
    ("symbols.jsonl", "term"),
    ("tools.jsonl", "entity"),
)

CLAIM_KNOWLEDGE = {
    "written_proof": "derived",
    "conditional": "derived",
    "source_inspected": "reported",
    "numerical": "observed",
    "refuted_attempt": "refuted",
    "open": "open",
    "definition_unresolved": "undefined",
}
METHOD_STATES = {"used", "audited_unused", "tried_failed", "untried"}


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate JSON member: {key}")
        obj[key] = value
    return obj


def _constant(value: str) -> None:
    raise ValueError(f"non-JSON numeric constant: {value}")


def _json(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_object, parse_constant=_constant)


def _string_list(value: Any, location: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ValueError(f"{location}: expected an array of strings")
    return value


def _ref(record_id: str) -> dict[str, str]:
    return {"id": record_id, "rev": "1"}


def _text(row: dict[str, Any], kind: str) -> str:
    candidates = {
        "claim": ("statement", "title"),
        "method": ("title", "result"),
        "task": ("target_statement", "title"),
        "source": ("title", "url"),
        "term": ("definition", "symbol"),
        "entity": ("symbol", "title"),
    }[kind]
    for field in candidates:
        if isinstance(row.get(field), str) and row[field]:
            return row[field]
    return row["id"]


def _anchor(scheme: str, row: dict[str, Any], fields: tuple[str, ...],
            original_fields: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    """Expose small native selectors that must survive a compact handoff."""
    selected = {field: deepcopy(row[field]) for field in fields if field in row}
    original = row.get("original")
    if isinstance(original, dict):
        selected_original = {field: deepcopy(original[field]) for field in original_fields
                             if field in original}
        if selected_original:
            selected["original"] = selected_original
    return [{"scheme": scheme, **selected}] if selected else []


def project(files: dict[str, bytes]) -> dict[str, Any]:
    """Project root-normalized GBCX/1 files without mutating their bytes.

    The original PROTOCOL.json must identify GBCX/1. At least claims.jsonl
    must exist. Secondary catalogues, proofs, checks and indexes stay in the
    retained origin; this projection does not pretend their bytes are absent.
    """
    if "PROTOCOL.json" not in files:
        raise ValueError("GBCX/1 requires PROTOCOL.json")
    protocol = _json(files["PROTOCOL.json"].decode("utf-8-sig"))
    if not isinstance(protocol, dict) or protocol.get("protocol") != "GBCX/1":
        raise ValueError("unsupported GBCX protocol; expected GBCX/1")
    if "claims.jsonl" not in files:
        raise ValueError("GBCX/1 requires claims.jsonl")

    warnings: list[str] = []
    native: list[tuple[str, int, str, dict[str, Any]]] = []
    local_ids: dict[str, set[str]] = {}
    for path, kind in TABLES:
        if path not in files:
            continue
        local_ids[path] = set()
        for line, raw in enumerate(files[path].decode("utf-8-sig").splitlines(), 1):
            if not raw.strip():
                continue
            row = _json(raw)
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line}: expected a JSON object")
            record_id = row.get("id")
            if not isinstance(record_id, str) or not record_id:
                raise ValueError(f"{path}:{line}: nonempty string id required")
            if record_id in local_ids[path]:
                raise ValueError(f"{path}:{line}: duplicate local id {record_id}")
            local_ids[path].add(record_id)
            native.append((path, line, kind, row))

    counts = Counter(row["id"] for _, _, _, row in native)
    assigned = {record_id for record_id, count in counts.items() if count == 1}
    mapping: dict[tuple[str, str], str] = {}
    for path, _, _, row in native:
        old_id = row["id"]
        if counts[old_id] == 1:
            mapping[(path, old_id)] = old_id
            continue
        stem = path.removesuffix(".jsonl")
        candidate = f"gbcx/{stem}/{old_id}"
        base, suffix = candidate, 2
        while candidate in assigned:
            candidate = f"{base}~{suffix}"
            suffix += 1
        assigned.add(candidate)
        mapping[(path, old_id)] = candidate
        warnings.append(f"ID collision: {path}:{old_id} projected as {candidate}")

    def resolve(old_id: str, preferred: str | None, location: str) -> str | None:
        if preferred is not None and (preferred, old_id) in mapping:
            return mapping[(preferred, old_id)]
        options = [new for (path, old), new in mapping.items() if old == old_id]
        if len(options) == 1:
            return options[0]
        reason = "ambiguous" if options else "unresolved"
        warnings.append(f"{location}: {reason} reference {old_id}; retained in body")
        return None

    records: list[dict[str, Any]] = []
    for path, line, kind, row in native:
        record: dict[str, Any] = {
            "id": mapping[(path, row["id"])],
            "rev": "1",
            "kind": kind,
            "text": _text(row, kind),
            "body": deepcopy(row),
            "provenance": [{"origin": "legacy", "path": path, "line": line}],
        }
        if kind == "claim":
            status = row.get("status")
            if status is not None and not isinstance(status, str):
                raise ValueError(f"{path}:{line}: claim status must be a string")
            record["state"] = {"knowledge": CLAIM_KNOWLEDGE.get(status, "unchecked")}
            if status not in CLAIM_KNOWLEDGE:
                warnings.append(f"{path}:{line}: unmapped claim status {status!r}")
            assumptions = _string_list(row.get("assumptions", []), f"{path}:{line}:assumptions")
            record["conditions"] = [{"text": x} for x in assumptions]
            inherited = _string_list(row.get("condition_bearing_dependencies", []),
                                     f"{path}:{line}:condition_bearing_dependencies")
            for legacy_id in inherited:
                target = resolve(legacy_id, "claims.jsonl", path)
                condition: dict[str, Any] = {
                    "text": f"Conditions inherited from {legacy_id}; retain its original scope and assumptions."
                }
                if target is not None:
                    condition["ref"] = _ref(target)
                record["conditions"].append(condition)
            # Preserve the original qualification even if a source omits an
            # assumption. An empty list never discharges a conditional claim.
            record["extensions"] = {"gbcx": {
                "claim_status": status,
                "inline_condition_count": len(assumptions),
            }}
            if status == "conditional" and not assumptions and not inherited:
                record["conditions"].append({
                    "text": "Legacy conditional claim; hypotheses unspecified in source"
                })
                warnings.append(f"{path}:{line}: conditional claim has no listed assumptions; qualification remains conditional")
            scope = row.get("scope_limit")
            if isinstance(scope, str):
                record["scope"] = scope
            record["anchors"] = _anchor("gbcx/claim", row,
                                        ("title", "status", "verification", "evidence"))
        elif kind == "method":
            method_state = row.get("state")
            if method_state is not None and not isinstance(method_state, str):
                raise ValueError(f"{path}:{line}: method state must be a string")
            record["extensions"] = {"gbcx": {"method_state": method_state}}
            if isinstance(method_state, str):
                record["state"] = {"method_use": method_state}
            if method_state not in METHOD_STATES:
                warnings.append(f"{path}:{line}: unmapped method state {method_state!r}")
            if isinstance(row.get("failure_scope"), str):
                record["scope"] = row["failure_scope"]
            record["anchors"] = _anchor("gbcx/method", row,
                                        ("objects", "result", "next_test", "failure_scope"))
        elif kind == "task":
            # An open research question is proposed work; importing it does
            # not assert readiness or successful completion.
            record["state"] = {"work": "proposed", "knowledge": "open"}
            record["anchors"] = _anchor("gbcx/frontier", row,
                                        ("missing", "next_discriminating_test", "priority", "inputs", "available"))
        elif kind == "term":
            record["anchors"] = _anchor("gbcx/symbol", row, ("symbol",))
        elif kind in {"source", "entity"}:
            record["state"] = {"knowledge": "reported"}
            if isinstance(row.get("scope"), str):
                record["scope"] = row["scope"]
            if kind == "source":
                record["anchors"] = _anchor("gbcx/source", row,
                    ("url", "commit", "sha256", "verification", "source_manifest"),
                    ("url", "doi", "commit", "sha256", "local_pdf_sha256", "locator", "path", "anchors"))
            else:
                record["anchors"] = _anchor("gbcx/declaration", row, ("symbol", "catalogue"),
                    ("repository", "commit", "source_path", "source_line", "source_url",
                     "path", "line", "url", "sha256", "source_sha256", "hypotheses_summary"))
        records.append(record)

    relations: list[dict[str, Any]] = []
    edge_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}

    def edge(kind: str, source: str | None, target: str | None,
             origin: dict[str, Any], condition_bearing: bool = False) -> None:
        if source is None or target is None:
            return
        key = (kind, source, target)
        if key not in edge_by_key:
            relation = {
                "id": f"gbcx.edge.{len(relations) + 1:06d}",
                "from": _ref(source), "to": _ref(target), "kind": kind,
                "body": {"legacy_origins": []},
            }
            if kind == "depends_on":
                relation["body"]["condition_bearing"] = False
            edge_by_key[key] = relation
            relations.append(relation)
        relation = edge_by_key[key]
        relation["body"]["legacy_origins"].append(deepcopy(origin))
        if origin.get("field") == "claim_ids":
            relation["body"]["native_field"] = "claim_ids"
        if condition_bearing:
            relation["body"]["condition_bearing"] = True

    for path, line, kind, row in native:
        source = mapping[(path, row["id"])]
        origin = {"path": path, "line": line, "legacy_id": row["id"]}
        if "dependencies" in row or "condition_bearing_dependencies" in row:
            deps = _string_list(row.get("dependencies", []), f"{path}:{line}:dependencies")
            bearing = _string_list(row.get("condition_bearing_dependencies", []), f"{path}:{line}:condition_bearing_dependencies")
            for old in deps:
                edge("depends_on", source, resolve(old, "claims.jsonl", path),
                     dict(origin, field="dependencies"), old in bearing)
            for old in bearing:
                if old not in deps:
                    edge("depends_on", source, resolve(old, "claims.jsonl", path),
                         dict(origin, field="condition_bearing_dependencies"), True)
        if "source_ids" in row:
            for old in _string_list(row["source_ids"], f"{path}:{line}:source_ids"):
                edge("cites", source, resolve(old, "sources.jsonl", path),
                     dict(origin, field="source_ids"))
        if kind == "method":
            for old in _string_list(row.get("claim_ids", []), f"{path}:{line}:claim_ids"):
                # Native claim_ids means associated claims; it does not
                # independently establish that this method produced them.
                edge("relates_to", source, resolve(old, "claims.jsonl", path),
                     dict(origin, field="claim_ids"))

    # GBCX's optional dependency table uses the opposite presentation:
    # prerequisite -> consumer. Normalize it explicitly to consumer -> input.
    if "dependencies.json" in files:
        rows = _json(files["dependencies.json"].decode("utf-8-sig"))
        if not isinstance(rows, list):
            raise ValueError("dependencies.json must be an array")
        for i, row in enumerate(rows):
            if not isinstance(row, dict) or row.get("relation") != "prerequisite":
                warnings.append(f"dependencies.json:{i}: unmapped row retained in origin")
                continue
            before, after = row.get("from_id"), row.get("to_id")
            if not isinstance(before, str) or not isinstance(after, str):
                raise ValueError(f"dependencies.json:{i}: string from_id/to_id required")
            edge("depends_on", resolve(after, None, "dependencies.json"),
                 resolve(before, None, "dependencies.json"),
                 {"path": "dependencies.json", "index": i, "original": row})

    if "relations.json" in files:
        rows = _json(files["relations.json"].decode("utf-8-sig"))
        if not isinstance(rows, list):
            raise ValueError("relations.json must be an array")
        for i, row in enumerate(rows):
            if not isinstance(row, dict) or not isinstance(row.get("older"), str) or not isinstance(row.get("newer"), str):
                warnings.append(f"relations.json:{i}: unmapped row retained in origin")
                continue
            # The old relation often means a refinement, not logical
            # entailment. Keep that precise label in the native body.
            edge("relates_to", resolve(row["newer"], None, "relations.json"),
                 resolve(row["older"], None, "relations.json"),
                 {"path": "relations.json", "index": i, "original": row})

    projected_paths = [path for path, _ in TABLES if path in files]
    return {
        "profile": "gbcx/1",
        "records": records,
        "relations": relations,
        "warnings": warnings,
        "coverage": {
            "projected_tables": projected_paths,
            "primary_records": len(records),
            "primary_records_by_table": dict(Counter(path for path, _, _, _ in native)),
            "other_files": "Retained in exact legacy origin, not expanded into records",
            "status_scope": "Reported legacy proof/observation state; no new validation of source claims",
            "evidence_scope": "Exact legacy evidence paths remain in record.body.evidence; files reside in origin",
            "condition_scope": "Inline assumptions preserved verbatim; condition-bearing prerequisites additionally exposed as pinned reference conditions",
        },
    }
