"""Deterministic capsules and structurally checked language views."""
from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path

from .common import (FORMAT, VERSION, _ref, _dump, _json, _str,
                     _string_list, _content, _path, _file, _digest,
                     _error_report, fail)
from .contracts import (snapshot, make_contract, project_context, context_digest,
                        assert_same_value, protected_record)
from .model import _closure, _validate_records
from .storage import _load_bundle


def capsule(path, select=None, full=False):
    """Encode the shared contract's rows in the legacy table-jsonl/1 wire form.

    This compatibility representation retains its original header. The exact
    record and relation values are checked after encoding; the richer context
    envelope, including heads and profiles, is carried by the formal codecs.
    """
    data = _load_bundle(path)
    # Legacy callers use [] for all records and may repeat a selected id.
    select_ids = list(dict.fromkeys(select)) if select else None
    contract = make_contract("exact" if full and not select else "projection",
                             select=select_ids, omit_fields=[] if full else None)
    source = snapshot(data)
    target = project_context(source, contract, graph=data["graph"])
    records, relations = target["records"], target["relations"]
    selected = {(rid, source["heads"][rid]) for rid in select_ids or []}
    retained_relations = {r["id"] for r in relations}
    retained_rows = [data["index"][(r["id"], r["rev"])] for r in records]
    retained_rows.extend(r for r in source["relations"] if r["id"] in retained_relations)
    omitted = {key for row in retained_rows for key in contract["omit_fields"] if key in row}
    rows = []
    for r in records:
        extra = {k: deepcopy(v) for k, v in r.items() if k not in ("id", "rev", "kind", "text")}
        rows.append(["record", r["id"], r["rev"], r["kind"], r["text"], extra])
    for r in relations:
        extra = {k: deepcopy(v) for k, v in r.items() if k not in ("id", "from", "kind", "to")}
        rows.append(["relation", r["id"], r["from"], r["kind"], r["to"], extra])
    header = {"format": FORMAT, "version": VERSION, "encoding": "table-jsonl/1",
              "projection": "full" if full else "handoff", "source_records_sha256": data["records_sha256"],
              "source_relations_sha256": data["relations_sha256"], "namespace": data["manifest"]["namespace"],
              "columns": {"record": ["id", "rev", "kind", "text", "extra"], "relation": ["id", "from", "kind", "to", "extra"]},
              "counts": {"records": len(records), "relations": len(relations)}, "omitted_fields": sorted(omitted),
              "selection": {"mode": "heads", "refs": [{"id": key[0], "rev": key[1]} for key in sorted(selected)]} if select else {"mode": "all"},
              "omitted_records": len(data["records"]) - len(records),
              "omitted_relations": len(data["relations"]) - len(relations)}
    raw = _dump(header) + b"".join(_dump(row) for row in rows)
    decoded = parse_capsule(raw)
    for field in ("records", "relations"):
        assert_same_value(decoded[field], target[field], field=field)
    return raw



def parse_capsule(raw):
    lines = raw.decode("utf-8").splitlines() if isinstance(raw, bytes) else raw.splitlines()
    if not lines:
        fail("invalid_capsule", "Capsule is empty")
    header = _json(lines[0])
    expected_columns = {"record": ["id", "rev", "kind", "text", "extra"], "relation": ["id", "from", "kind", "to", "extra"]}
    if not isinstance(header, dict) or header.get("format") != FORMAT or header.get("version") != VERSION or header.get("encoding") != "table-jsonl/1" or header.get("columns") != expected_columns:
        fail("invalid_capsule", "Unsupported capsule header")
    if header.get("projection") not in ("full", "handoff"):
        fail("invalid_capsule", "Unsupported capsule projection")
    _str(header.get("namespace"), "capsule.namespace")
    for key in ("source_records_sha256", "source_relations_sha256"):
        if not isinstance(header.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", header[key]):
            fail("invalid_capsule", "Capsule source digests must be lowercase SHA-256", field=key)
    for key in ("omitted_records", "omitted_relations"):
        if not isinstance(header.get(key), int) or isinstance(header[key], bool) or header[key] < 0:
            fail("invalid_capsule", "Omission counts must be nonnegative integers", field=key)
    _string_list(header.get("omitted_fields"), "capsule.omitted_fields")
    selection = header.get("selection")
    if not isinstance(selection, dict) or selection.get("mode") not in ("all", "heads"):
        fail("invalid_capsule", "Capsule selection requires mode all or heads")
    selected_refs = []
    if selection["mode"] == "heads":
        if not isinstance(selection.get("refs"), list) or not selection["refs"]:
            fail("invalid_capsule", "Head selection requires explicit pinned references")
        selected_refs = [_ref(ref, "selection.ref") for ref in selection["refs"]]
        if len(set(selected_refs)) != len(selected_refs):
            fail("invalid_capsule", "Selection contains duplicate references")
    elif header["omitted_records"] != 0 or header["omitted_relations"] != 0:
        fail("invalid_capsule", "All selection cannot omit records or relations")
    records, relations = [], []
    for line in lines[1:]:
        if not line.strip():
            continue
        row = _json(line)
        if not isinstance(row, list) or len(row) != 6 or row[0] not in expected_columns or not isinstance(row[5], dict):
            fail("invalid_capsule", "Invalid table row")
        keys = expected_columns[row[0]][:4]
        if set(row[5]).intersection(keys):
            fail("invalid_capsule", "Extra fields overlap positional columns")
        value = {**dict(zip(keys, row[1:5])), **row[5]}
        (records if row[0] == "record" else relations).append(value)
    index = _validate_records(records, relations)
    if any(ref not in index for ref in selected_refs):
        fail("invalid_capsule", "Selected revision is absent from the capsule")
    if header.get("counts") != {"records": len(records), "relations": len(relations)}:
        fail("invalid_capsule", "Table counts disagree with header")
    if header["projection"] == "full" and header.get("omitted_fields") != []:
        fail("invalid_capsule", "Full projection cannot declare omitted fields")
    return {"header": header, "records": records, "relations": relations}



def view_digest(view):
    """SHA-256 of canonical UTF-8 view content, excluding only evaluation.

    Canonical content uses the shared sorted-key JSON comparison form, with
    compact separators, Unicode retained and no final newline. Entries, task,
    producer, consumer, source identifiers and unknown view fields all bind.
    """
    if not isinstance(view, dict):
        fail("invalid_view", "A view digest requires a JSON object")
    value = {key: item for key, item in view.items() if key != "evaluation"}
    return _digest(_content(value).encode("utf-8"))


def _view_evidence(data, view, evaluation, source, warnings):
    """Load a hashed report and verify its explicit view and source bindings."""
    report_path = evaluation.get("report")
    if report_path is None:
        if evaluation["status"] == "passed":
            fail("missing_evaluation_report", "Declared passed evaluation requires a report asset")
        return None
    _path(report_path)
    asset = next((item for item in data["manifest"]["assets"] if item["path"] == report_path), None)
    if asset is None:
        fail("missing_evaluation_report", "Evaluation report must be a hashed bundle asset", path=report_path)
    raw = _file(data["base"], report_path).read_bytes()
    # Bind the bytes passed to the host even if a writer changes the file after
    # the initial archive validation.
    if len(raw) != asset["bytes"] or _digest(raw) != asset["sha256"]:
        fail("hash_mismatch", "Evaluation report bytes differ from manifest", path=report_path)
    try:
        report = _json(raw)
    except (ValueError, UnicodeError, RecursionError):
        report = None
    if not isinstance(report, dict) or report.get("format") != "AOCX-EVALUATION":
        warnings.append({"code": "unbound_evaluation_report", "path": report_path,
                         "message": "Report has no explicit AOCX-EVALUATION view and source bindings"})
        return None
    if report.get("version") != VERSION:
        fail("invalid_evaluation_report", "Expected AOCX-EVALUATION 1.0", path=report_path)
    for field in ("view_sha256", "source_snapshot_sha256"):
        if not isinstance(report.get(field), str) or not re.fullmatch(r"[0-9a-f]{64}", report[field]):
            fail("invalid_evaluation_report", "Evaluation bindings must be lowercase SHA-256", field=field, path=report_path)
    if report["view_sha256"] != view_digest(view):
        fail("evaluation_view_digest_mismatch", "Report is bound to different view content", path=report_path)
    if report["source_snapshot_sha256"] != context_digest(source):
        fail("evaluation_source_digest_mismatch", "Report is bound to a different source context", path=report_path)
    return report


def check_view(path, view, evaluator=None):
    """Check a BabelTele view and optionally verify its evidence in the host.

    Evidence is a hashed bundle asset containing a JSON object with required
    fields ``format: AOCX-EVALUATION``, ``version: 1.0``, ``view_sha256`` and
    ``source_snapshot_sha256``. Additional evidence fields remain open. The
    first digest is ``view_digest(view)``; the second is
    ``context_digest(snapshot(bundle))`` and binds heads, profiles and metadata
    as well as record and relation values.

    A caller-supplied ``evaluator`` is invoked only for matching evidence with
    declared status ``passed``. Its exact keyword API is
    ``evaluator(report=report, view=view, source=context) -> bool``. All three
    arguments are independent deep copies. Only the singleton ``True`` marks
    semantic evaluation verified and makes the view eligible. A missing,
    rejecting or raising evaluator leaves structural success intact and adds
    a warning. No executable behavior is loaded from the report or the view.
    """
    try:
        if evaluator is not None and not callable(evaluator):
            fail("invalid_evaluator", "Host evaluator must be callable")
        data = _load_bundle(path)
        if isinstance(view, (str, Path)):
            view = _json(Path(view).read_bytes())
        if not isinstance(view, dict) or view.get("format") != "AOCX-VIEW" or view.get("version") != VERSION or view.get("codec") != "babeltele-view/1":
            fail("invalid_view", "Expected AOCX-VIEW 1.0 / babeltele-view/1")
        if view.get("source_records_sha256") != data["records_sha256"]:
            fail("view_digest_mismatch", "View is bound to different source record bytes")
        if view.get("source_relations_sha256") != data["relations_sha256"]:
            fail("view_relations_digest_mismatch", "View is bound to different source relation bytes")
        if view.get("namespace") != data["manifest"]["namespace"]:
            fail("view_namespace_mismatch", "View belongs to a different record namespace")
        _str(view.get("task"), "view.task", empty=True)
        for group, keys in (("producer", ("model", "prompt_sha256")), ("consumer", ("model", "tokenizer"))):
            if not isinstance(view.get(group), dict):
                fail("invalid_view", "View producer/consumer must be objects", field=group)
            for key in keys:
                _str(view[group].get(key), group + "." + key)
        if not re.fullmatch(r"[0-9a-f]{64}", view["producer"]["prompt_sha256"]):
            fail("invalid_view", "Prompt SHA-256 must be lowercase hex")
        entries = view.get("entries")
        if not isinstance(entries, list):
            fail("invalid_view", "View entries must be an array")
        selected = set()
        for entry in entries:
            if not isinstance(entry, dict):
                fail("invalid_view", "View entry must be an object")
            key = _ref(entry.get("ref"), "view.ref")
            if key in selected or key not in data["index"]:
                fail("invalid_view_ref", "View reference is duplicate or absent", ref=entry.get("ref"))
            selected.add(key)
            _str(entry.get("text"), "view.text", empty=True)
            protected = protected_record(data["index"][key])
            if _content(entry.get("protected")) != _content(protected):
                fail("changed_protected_fields", "View changed pinned or protected source metadata", ref=entry["ref"])
        missing = _closure(data, selected) - selected
        if missing:
            fail("view_incomplete_closure", "View omits condition or prerequisite records", missing=[{"id": k[0], "rev": k[1]} for k in sorted(missing)])
        evaluation = view.get("evaluation")
        if not isinstance(evaluation, dict) or evaluation.get("status") not in ("unassessed", "passed"):
            fail("invalid_view_evaluation", "Expected declared evaluation status unassessed or passed")
        source = snapshot(data)
        warnings = []
        report = _view_evidence(data, view, evaluation, source, warnings)
        evidence_bound = report is not None
        verified = False
        if evidence_bound and evaluation["status"] == "passed":
            if evaluator is None:
                warnings.append({"code": "semantic_evaluator_required",
                                 "message": "A host evaluator must verify the bound evidence before eligibility"})
            else:
                try:
                    verified = evaluator(report=deepcopy(report), view=deepcopy(view), source=deepcopy(source)) is True
                except Exception as error:
                    warnings.append({"code": "semantic_evaluator_error", "error_type": type(error).__name__,
                                     "message": "Host evaluator raised an exception; semantic evaluation remains unverified"})
                else:
                    if not verified:
                        warnings.append({"code": "semantic_evaluation_not_verified",
                                         "message": "Host evaluator did not return True"})
        return {"status": "passed", "structural": "passed", "eligible": verified,
                "evidence_bound": evidence_bound, "semantic_evaluation_verified": verified,
                "eligibility_basis": "Matching view and source bindings, declared passed status and explicit host verification",
                "errors": [], "warnings": warnings, "entries": len(entries)}
    except (ValueError, TypeError, OSError, UnicodeError, RecursionError) as error:
        result = _error_report(error)
        result.update(structural="failed", eligible=False, evidence_bound=False, semantic_evaluation_verified=False)
        return result
