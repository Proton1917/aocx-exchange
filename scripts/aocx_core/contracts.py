"""Executable preservation contracts shared by every context representation.

The context value is the logical record graph, its revision heads, profiles and
manifest metadata. Archive attachment bytes have their own storage contract.
"""
from __future__ import annotations

from copy import deepcopy

from .common import _content, _digest, _ref, _str, _string_list, fail
from .model import GraphIndex, _validate_records

CONTEXT_FIELDS = {"namespace", "records", "relations", "heads", "profiles",
                  "required_profiles", "metadata"}
CONTAINER_FIELDS = {"format", "version", "namespace", "records", "relations",
                    "heads", "profiles", "required_profiles", "assets", "origins"}
OMITTABLE = {"body", "extensions"}


def make_contract(mode="exact", select=None, omit_fields=None):
    """Declare full recovery, or an explicit prerequisite-closed projection."""
    if mode not in ("exact", "projection"):
        fail("invalid_contract", "Fidelity must be exact or projection", fidelity=mode)
    if select is not None:
        if not isinstance(select, (list, tuple)) or not select:
            fail("invalid_contract", "Selection must contain explicit record ids")
        _string_list(list(select), "selection.ids")
        if len(set(select)) != len(select):
            fail("invalid_contract", "Selection ids must be unique")
    if omit_fields is None:
        omit_fields = [] if mode == "exact" else sorted(OMITTABLE)
    if not isinstance(omit_fields, (list, tuple)):
        fail("invalid_contract", "Omitted fields must be an array")
    _string_list(list(omit_fields), "omit_fields")
    if len(set(omit_fields)) != len(omit_fields) or not set(omit_fields).issubset(OMITTABLE):
        fail("invalid_contract", "Projection can omit body and extensions", fields=list(omit_fields))
    if mode == "exact" and (select is not None or omit_fields):
        fail("invalid_contract", "Exact fidelity covers the complete context value")
    return {"format": "AOCX-CONTRACT", "version": "1.0", "fidelity": mode,
            "selection": {"mode": "all"} if select is None else
                         {"mode": "heads", "ids": sorted(select)},
            "omit_fields": sorted(omit_fields)}


def validate_contract(contract):
    if not isinstance(contract, dict) or set(contract) != {"format", "version", "fidelity", "selection", "omit_fields"}:
        fail("invalid_contract", "Expected the complete AOCX preservation contract")
    if contract["format"] != "AOCX-CONTRACT" or contract["version"] != "1.0":
        fail("invalid_contract", "Supported preservation contract is AOCX-CONTRACT 1.0")
    selection = contract["selection"]
    if not isinstance(selection, dict):
        fail("invalid_contract", "Selection must be an object")
    if selection.get("mode") == "all" and set(selection) == {"mode"}:
        select = None
    elif selection.get("mode") == "heads" and set(selection) == {"mode", "ids"}:
        select = selection["ids"]
    else:
        fail("invalid_contract", "Expected all or explicit head selection")
    normalized = make_contract(contract["fidelity"], select, contract["omit_fields"])
    if _content(normalized) != _content(contract):
        fail("invalid_contract", "Contract selections and omissions must be in sorted order")
    return deepcopy(contract)


def snapshot(data):
    """Capture all context values from a validated archive, excluding assets."""
    manifest = data["manifest"]
    return deepcopy({"namespace": manifest["namespace"], "records": data["records"],
                     "relations": data["relations"], "heads": manifest["heads"],
                     "profiles": manifest["profiles"], "required_profiles": manifest["required_profiles"],
                     "metadata": {k: v for k, v in manifest.items() if k not in CONTAINER_FIELDS}})


def validate_context(context, *, complete=True):
    if not isinstance(context, dict) or set(context) != CONTEXT_FIELDS:
        fail("invalid_context", "Expected the complete logical context value")
    _str(context["namespace"], "context.namespace")
    index = _validate_records(context["records"], context["relations"])
    for name in ("profiles", "required_profiles"):
        _string_list(context[name], "context." + name)
    if "core/1" not in context["required_profiles"] or not set(context["required_profiles"]).issubset(context["profiles"]):
        fail("invalid_context", "Profiles must contain their required core and domain profiles")
    heads = context["heads"]
    if not isinstance(heads, dict) or not isinstance(context["metadata"], dict):
        fail("invalid_context", "Heads and metadata must be objects")
    for rid, rev in heads.items():
        _str(rid, "head.id")
        _str(rev, "head.rev")
        if (rid, rev) not in index:
            fail("invalid_context", "Head must identify a retained record revision", id=rid, rev=rev)
    if complete and set(heads) != {key[0] for key in index}:
        fail("invalid_context", "An exact context must select one head for every object")
    return index


def project_context(context, contract, *, graph=None):
    """Construct the only target value permitted by this preservation contract."""
    contract = validate_contract(contract)
    index = validate_context(context)
    if contract["fidelity"] == "exact":
        return deepcopy(context)
    selection = contract["selection"]
    if selection["mode"] == "all":
        needed = set(index)
    else:
        selected = set()
        for rid in selection["ids"]:
            if rid not in context["heads"]:
                fail("unknown_selection", "Selected record has no current revision", id=rid)
            selected.add((rid, context["heads"][rid]))
        graph = graph or GraphIndex(context["records"], context["relations"], index)
        needed = graph.closure(selected)
    omitted = set(contract["omit_fields"])
    result = deepcopy(context)
    result["records"] = [{k: deepcopy(v) for k, v in r.items() if k not in omitted}
                         for r in context["records"] if (r["id"], r["rev"]) in needed]
    result["relations"] = [{k: deepcopy(v) for k, v in edge.items() if k not in omitted}
                           for edge in context["relations"]
                           if _ref(edge["from"], "from") in needed and _ref(edge["to"], "to") in needed]
    # A retained historical premise stays historical; it never becomes a head.
    result["heads"] = {rid: rev for rid, rev in context["heads"].items() if (rid, rev) in needed}
    validate_context(result, complete=False)
    return result


def context_digest(context):
    """Digest the typed comparison form, including heads and manifest metadata."""
    return _digest(_content(context).encode("utf-8"))


def source_binding(data, context=None):
    context = snapshot(data) if context is None else context
    return {"namespace": context["namespace"], "snapshot_sha256": context_digest(context),
            "records_sha256": data["records_sha256"], "relations_sha256": data["relations_sha256"]}


def assert_same_value(actual, expected, *, code="preservation_failed", field="context"):
    """Compare JSON types and values, retaining missing/null and bool/int distinctions."""
    if _content(actual) != _content(expected):
        fail(code, "Decoded value differs from the declared target", field=field)


def protected_record(record):
    """The logical contract is protected across task-conditioned language views."""
    return {k: deepcopy(v) for k, v in record.items() if k not in ("text", "body", "extensions")}
