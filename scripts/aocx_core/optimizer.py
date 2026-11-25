"""Compile the smallest verified representation in a finite codec search.

Every candidate follows the same sequence: encode, decode, preserve, measure.
Cost can select among valid encodings; it cannot relax the context contract.
"""
from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path

from .common import AOCXError, _content, _digest, _error_report, _string_list, fail
from .contracts import (assert_same_value, context_digest, make_contract,
                        project_context, snapshot, source_binding,
                        validate_context, validate_contract)
from .storage import _load_bundle

DEFAULT_CODECS = ("aocx-expr/1", "aocx-expr-dict/1")


def _registry(value):
    from .codecs import default_registry
    return default_registry() if value is None else value


def _decoded(raw, registry):
    from .codecs import decode_representation
    return decode_representation(raw, registry=registry)


def _check_envelope(envelope, *, contract=None, source=None, target=None):
    keys = {"format", "version", "contract", "source", "context", "recovery"}
    if not isinstance(envelope, dict) or set(envelope) != keys:
        fail("invalid_representation", "Expected a complete AOCX-REP envelope")
    if envelope["format"] != "AOCX-REP" or envelope["version"] != "1.0":
        fail("unsupported_representation", "Supported representation is AOCX-REP 1.0")
    declared = validate_contract(envelope["contract"])
    if contract is not None:
        assert_same_value(declared, validate_contract(contract), code="contract_mismatch", field="contract")
    context = envelope["context"]
    validate_context(context, complete=declared["fidelity"] == "exact")
    binding = envelope["source"]
    if not isinstance(binding, dict) or set(binding) != {"namespace", "snapshot_sha256", "records_sha256", "relations_sha256"}:
        fail("invalid_source_binding", "Source binding requires the snapshot and both file digests")
    if binding["namespace"] != context["namespace"]:
        fail("source_mismatch", "Source and context namespaces differ")
    for key in ("snapshot_sha256", "records_sha256", "relations_sha256"):
        if not isinstance(binding[key], str) or not re.fullmatch(r"[0-9a-f]{64}", binding[key]):
            fail("invalid_source_binding", "Source digests must be lowercase SHA-256", field=key)
    if source is not None:
        assert_same_value(binding, source, code="source_mismatch", field="source")
    expected_recovery = {"kind": "self-contained", "scope": "context-values",
                         "target_sha256": context_digest(context)}
    assert_same_value(envelope["recovery"], expected_recovery, code="recovery_mismatch", field="recovery")
    if declared["fidelity"] == "exact" and context_digest(context) != binding["snapshot_sha256"]:
        fail("preservation_failed", "Exact context differs from the bound source snapshot")
    if declared["selection"]["mode"] == "heads":
        missing = sorted(set(declared["selection"]["ids"]) - set(context["heads"]))
        if missing:
            fail("invalid_representation", "Selected current revisions must be retained", missing=missing)
    omitted = set(declared["omit_fields"])
    if any(omitted.intersection(row) for row in context["records"] + context["relations"]):
        fail("invalid_representation", "Projection contains a declared omitted field")
    if target is not None:
        assert_same_value(context, target)
    return context


def recover_context(raw, registry=None):
    """Recover the declared context value without reading the original archive."""
    envelope = _decoded(raw, _registry(registry))
    return deepcopy(_check_envelope(envelope))


def verify_representation(source, raw, contract=None, *, registry=None):
    """Verify an actual inverse against the source and optional caller contract."""
    try:
        data = _load_bundle(source)
        full = snapshot(data)
        envelope = _decoded(raw, _registry(registry))
        # Validate the envelope before trusting its declared contract.
        _check_envelope(envelope, contract=contract)
        declared = envelope["contract"]
        target = project_context(full, declared, graph=data["graph"])
        context = _check_envelope(envelope, contract=contract, source=source_binding(data, full), target=target)
        return {"status": "passed", "fidelity": declared["fidelity"], "recovery": "self-contained",
                "scope": "context-values", "source_verified": True,
                "logic_preserved": True, "target_sha256": context_digest(context),
                "counts": {"records": len(context["records"]), "relations": len(context["relations"])},
                "errors": [], "warnings": []}
    except Exception as error:
        # Registered decoders share the same diagnostic boundary as encoders.
        return _error_report(error)


def _reader_check(reader, context):
    if reader is None:
        return None
    if not isinstance(reader, dict):
        fail("invalid_reader", "Reader capabilities must be an object")
    for name in ("codecs", "profiles", "required_profiles"):
        if name in reader:
            _string_list(reader[name], "reader." + name)
    if "profiles" in reader:
        needed = set(context["required_profiles"]) | set(reader.get("required_profiles", []))
        if not needed.issubset(set(reader["profiles"]) & set(context["profiles"])):
            fail("unsupported_required_profile", "Reader must support the required context profiles",
                 profiles=sorted(needed - (set(reader["profiles"]) & set(context["profiles"]))))
    elif reader.get("required_profiles"):
        fail("invalid_reader", "Reader required profiles need a supported profiles declaration")
    return set(reader["codecs"]) if "codecs" in reader else None


def _measure(raw, metric, tokenizer, tokenizer_id):
    if metric == "bytes":
        return len(raw)
    if metric == "characters":
        return len(raw.decode("utf-8"))
    tokens = tokenizer(raw.decode("utf-8"))
    # A concrete sequence makes a measurement distinguishable from an estimate.
    if isinstance(tokens, (str, bytes, dict, int, float)) or not hasattr(tokens, "__len__"):
        fail("invalid_tokenizer_result", "Tokenizer must return the measured token sequence", tokenizer=tokenizer_id)
    return len(tokens)


def compile_context(source, contract=None, *, codecs=None, registry=None, reader=None,
                    metric="bytes", tokenizer=None, tokenizer_id=None):
    """Compile a source archive using an enforced, language-independent contract.

    Source is read once. Each plugin receives its own copy and must prove its
    inverse on this input. Ties use (cost, wire bytes, codec id), independent of
    registration order. Plugins are explicitly registered trusted Python code.
    """
    if metric not in ("bytes", "characters", "tokens"):
        fail("invalid_metric", "Cost metric must be bytes, characters or tokens")
    if metric == "tokens" and (not callable(tokenizer) or not isinstance(tokenizer_id, str) or not tokenizer_id):
        fail("missing_tokenizer", "Token cost requires a concrete tokenizer and its identifier")
    contract = make_contract() if contract is None else validate_contract(contract)
    data = _load_bundle(source)
    full = snapshot(data)
    target = project_context(full, contract, graph=data["graph"])
    allowed = _reader_check(reader, target)
    registry = _registry(registry)
    ids = list(DEFAULT_CODECS if codecs is None else codecs)
    _string_list(ids, "codecs")
    if not ids or len(set(ids)) != len(ids):
        fail("invalid_candidates", "Provide unique candidate codec ids")
    envelope = {"format": "AOCX-REP", "version": "1.0", "contract": contract,
                "source": source_binding(data, full), "context": target,
                "recovery": {"kind": "self-contained", "scope": "context-values",
                             "target_sha256": context_digest(target)}}
    candidates, accepted = [], []
    for codec_id in ids:
        item = {"codec": codec_id, "status": "rejected", "cost": None, "errors": []}
        try:
            if allowed is not None and codec_id not in allowed:
                fail("reader_codec_unsupported", "Reader does not declare this decoder", codec=codec_id)
            codec = registry.get(codec_id)
            raw = codec.encode(deepcopy(envelope))
            if not isinstance(raw, bytes):
                fail("invalid_codec_output", "Encoder must return wire bytes", codec=codec_id)
            # Dispatch through the declared wire prefix, just as a recipient does.
            decoded = _decoded(raw, registry)
            expected_prefix = ("AOCX/1 " + codec_id + "\n").encode("utf-8")
            if not raw.startswith(expected_prefix):
                fail("codec_identity_mismatch", "Wire codec differs from the chosen encoder", codec=codec_id)
            assert_same_value(decoded, envelope, field="envelope")
            _check_envelope(decoded, contract=contract, source=envelope["source"], target=target)
            cost = _measure(raw, metric, tokenizer, tokenizer_id)
            item.update(status="passed", cost=cost, bytes=len(raw), characters=len(raw.decode("utf-8")),
                        roundtrip="passed", sha256=_digest(raw))
            accepted.append((cost, len(raw), codec_id, raw))
        except Exception as error:
            # One third-party encoder failure cannot discard other valid encodings.
            item["errors"] = _error_report(error)["errors"]
        candidates.append(item)
    if not accepted:
        fail("no_eligible_representation", "Every candidate failed the preservation or reader contract", candidates=candidates)
    cost, byte_count, chosen, raw = min(accepted, key=lambda row: row[:3])
    report = {"status": "passed", "selected_codec": chosen, "metric": metric, "cost": cost,
              "bytes": byte_count, "sha256": _digest(raw), "fidelity": contract["fidelity"],
              "scope": "context-values", "recovery": "self-contained", "logic_preserved": True,
              "finite_search": True, "candidates": candidates,
              "selection_rule": "Minimum (measured cost, wire bytes, codec id) among verified candidates",
              "source": envelope["source"], "target_sha256": context_digest(target),
              "omitted_records": len(full["records"]) - len(target["records"]),
              "omitted_relations": len(full["relations"]) - len(target["relations"]),
              "contract": contract, "errors": [], "warnings": data["warnings"]}
    if metric == "tokens":
        report["tokenizer"] = tokenizer_id
    return {"representation": raw, "report": report}
