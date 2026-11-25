"""Peer capability matching and fixed-revision three-way merge checks."""
from __future__ import annotations

from .common import (CODECS, AOCXError, _string_list, _content, _error_report, fail)
from .model import _validate_records
from .storage import _load_bundle


def negotiate(offer, reader):
    try:
        for value, name in ((offer, "offer"), (reader, "reader")):
            if not isinstance(value, dict):
                fail("invalid_negotiation", "Capability document must be an object", endpoint=name)
            for field in ("versions", "profiles", "codecs"):
                _string_list(value.get(field), name + "." + field)
            _string_list(value.get("required_profiles", []), name + ".required_profiles")
            if "accepts_lossy" in value and not isinstance(value["accepts_lossy"], bool):
                fail("invalid_negotiation", "accepts_lossy must be boolean")
            modes = value.get("codec_modes", {})
            if not isinstance(modes, dict) or any(not isinstance(k, str) or v not in ("lossless", "semantic") for k, v in modes.items()):
                fail("invalid_negotiation", "codec_modes must map codec ids to lossless or semantic")
        versions = [v for v in offer["versions"] if v in reader["versions"]]
        if not versions:
            fail("no_common_version", "No mutually supported version")
        shared_profiles = set(offer["profiles"]) & set(reader["profiles"])
        required = set(offer.get("required_profiles", [])) | set(reader.get("required_profiles", []))
        if not required.issubset(shared_profiles):
            fail("unsupported_required_profile", "Required profiles lack mutual support", profiles=sorted(required - shared_profiles))
        lossy = offer.get("accepts_lossy", False) and reader.get("accepts_lossy", False)
        codecs, unsupported = [], []
        for codec in offer["codecs"]:
            if codec not in reader["codecs"]:
                continue
            om, rm = offer.get("codec_modes", {}).get(codec), reader.get("codec_modes", {}).get(codec)
            if codec in CODECS:
                mode = "semantic" if codec == "babeltele-view/1" else "lossless"
                if any(m is not None and m != mode for m in (om, rm)):
                    unsupported.append(codec)
                    continue
            elif om is not None and om == rm:
                mode = om
            else:
                unsupported.append(codec)
                continue
            if mode == "semantic" and not lossy:
                continue
            codecs.append((codec, mode))
        if not codecs:
            fail("no_common_codec", "No mutually permitted codec")
        selected_codec, selected_mode = codecs[0]
        return {"status": "passed", "version": versions[0], "profiles": sorted(shared_profiles), "codec": selected_codec,
                "lossy": selected_mode == "semantic", "evaluation_required": selected_mode == "semantic",
                "declared_mode": selected_mode, "implementation_required": selected_codec not in CODECS,
                "unsupported_codecs": sorted(set(unsupported))}
    except (ValueError, TypeError) as error:
        return _error_report(error)



def merge_check(base, left, right):
    try:
        datasets = [_load_bundle(p) for p in (base, left, right)]
        namespaces = [d["manifest"]["namespace"] for d in datasets]
        if len(set(namespaces)) != 1:
            fail("namespace_mismatch", "Three-way merge requires one namespace", namespaces=namespaces)
        conflicts, values, edge_values = [], {}, {}
        for label, data in zip(("base", "left", "right"), datasets):
            for key, record in data["index"].items():
                if key in values and _content(values[key][1]) != _content(record):
                    conflicts.append({"code": "revision_content_conflict", "id": key[0], "rev": key[1], "sides": [values[key][0], label]})
                else:
                    values[key] = (label, record)
            for relation in data["relations"]:
                rid = relation["id"]
                if rid in edge_values and _content(edge_values[rid][1]) != _content(relation):
                    conflicts.append({"code": "relation_content_conflict", "id": rid, "sides": [edge_values[rid][0], label]})
                else:
                    edge_values[rid] = (label, relation)
        bh, lh, rh = [d["manifest"]["heads"] for d in datasets]
        if not conflicts:
            try:
                _validate_records([r for _, r in values.values()], [r for _, r in edge_values.values()])
            except AOCXError as error:
                conflicts.append({"code": "merged_graph_invalid", "cause": error.diagnostic})
        merged_heads = {}
        for rid in sorted(set(bh) | set(lh) | set(rh)):
            b, l, r = bh.get(rid), lh.get(rid), rh.get(rid)
            if l == r:
                chosen = l
            elif l == b:
                chosen = r
            elif r == b:
                chosen = l
            else:
                conflicts.append({"code": "head_conflict", "id": rid, "base": b, "left": l, "right": r})
                continue
            if chosen is not None:
                merged_heads[rid] = chosen
        # A deletion removes a selection, not its immutable historical records.
        return {"status": "conflict" if conflicts else "clean", "namespace": namespaces[0], "conflicts": conflicts,
                "proposed_heads": merged_heads, "retained_record_revisions": len(values), "retained_relations": len(edge_values),
                "writes": False, "scope": "Conflict report only; a separate explicit commit must preserve history and revalidate the union"}
    except (ValueError, OSError, UnicodeError, RecursionError) as error:
        return _error_report(error)
