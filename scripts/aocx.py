#!/usr/bin/env python3
"""AOCX/1 reference exchange tools. Python standard library; no network or execution.

Canonical records keep arbitrary text and unknown JSON fields. Domain profiles
remain optional. Hashes bind stored bytes, not a claimed JSON canonicalization.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import shutil
import stat
import sys
import zipfile
from collections import deque
from copy import deepcopy
from pathlib import Path, PurePosixPath

FORMAT = "AOCX"
VERSION = "1.0"
MANIFEST = "aocx.json"
PROFILES = {"core/1", "gbcx/1", "aoci-code/volumes-v1+fras-v2", "aoci-code/legacy"}
CODECS = {"jsonl/1", "canonical-jsonl/1", "table-jsonl/1", "babeltele-view/1"}
MAX_FILES = 100000
MAX_BYTES = 500 * 1024 * 1024
FOLLOW = {"depends_on", "assumes", "cites"}
OMIT = {"body", "extensions"}


class AOCXError(ValueError):
    def __init__(self, code, message, **details):
        super().__init__(message)
        self.diagnostic = {"code": code, "message": message, **details}


def fail(code, message, **details):
    raise AOCXError(code, message, **details)


def _pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            fail("duplicate_json_key", "Duplicate JSON member", key=key)
        obj[key] = value
    return obj


def _number(text):
    value = float(text)
    if not math.isfinite(value):
        fail("nonfinite_number", "JSON number exceeds finite representation", value=text)
    return value


def _constant(text):
    fail("nonfinite_number", "Non-JSON numeric constant", value=text)


def _json(data):
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    value = json.loads(data, object_pairs_hook=_pairs, parse_constant=_constant, parse_float=_number)
    # Ensure escaped lone surrogates also fail the UTF-8 interchange contract.
    json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    return value


def _dump(value, *, pretty=False):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2 if pretty else None,
                       separators=None if pretty else (",", ":")) + "\n").encode("utf-8")


def _content(value):
    # Internal typed comparison only. This is not RFC 8785 or a wire hash.
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _path(value, *, empty=False):
    if empty and value == "":
        return value
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or "\x00" in value:
        fail("unsafe_path", "Expected a portable relative path", path=value)
    p = PurePosixPath(value)
    if p.is_absolute() or p.as_posix() != value or any(x in ("", ".", "..") for x in value.split("/")):
        fail("unsafe_path", "Path must be canonical, relative and traversal-free", path=value)
    return value


def _file(base, rel):
    _path(rel)
    p = base
    for part in PurePosixPath(rel).parts:
        p = p / part
        if p.is_symlink():
            fail("symlink", "Symbolic links are outside the bundle file contract", path=rel)
    if not p.is_file():
        fail("missing_file", "Bundle file is missing or not regular", path=rel)
    if p.stat().st_size > MAX_BYTES:
        fail("size_limit", "Bundle file exceeds the byte limit", path=rel)
    return p


def _str(value, name, *, empty=False):
    if not isinstance(value, str) or (not empty and not value):
        fail("invalid_type", "Expected " + ("a string" if empty else "a nonempty string"), field=name)


def _string_list(value, name):
    if not isinstance(value, list) or any(not isinstance(x, str) or not x for x in value):
        fail("invalid_type", "Expected an array of nonempty strings", field=name)


def _ref(value, name):
    if not isinstance(value, dict):
        fail("invalid_ref", "Pinned reference must be an object", field=name)
    _str(value.get("id"), name + ".id")
    _str(value.get("rev"), name + ".rev")
    return value["id"], value["rev"]


def _jsonl(data, name):
    text = data.decode("utf-8")
    result = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        value = _json(line)
        if not isinstance(value, dict):
            fail("invalid_record", "Each JSONL line must be an object", path=name, line=number)
        result.append(value)
    return result


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


def _load_bundle(path, preserve_only=False):
    base = Path(path).resolve(strict=True)
    if not base.is_dir():
        fail("invalid_bundle", "Expected a bundle directory")
    manifest = _json(_file(base, MANIFEST).read_bytes())
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT or manifest.get("version") != VERSION:
        fail("unsupported_version", "Supported envelope is AOCX 1.0")
    _str(manifest.get("namespace"), "namespace")
    for name in ("profiles", "required_profiles"):
        _string_list(manifest.get(name), name)
    if "core/1" not in manifest["profiles"] or "core/1" not in manifest["required_profiles"]:
        fail("missing_core_profile", "core/1 must be declared and required")
    if not set(manifest["required_profiles"]).issubset(manifest["profiles"]):
        fail("invalid_profile", "Required profiles must also be declared")
    unknown = sorted(set(manifest["required_profiles"]) - PROFILES)
    warnings = []
    if unknown:
        if not preserve_only:
            fail("unsupported_required_profile", "Reader does not implement required profiles", profiles=unknown)
        warnings.append({"code": "opaque_required_profiles", "profiles": unknown})
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        fail("invalid_type", "assets must be an array")
    mapped, folded = {}, set()
    total = 0
    for item in assets:
        if not isinstance(item, dict):
            fail("invalid_type", "Asset entry must be an object")
        rel = _path(item.get("path"))
        if rel == MANIFEST or rel in mapped or rel.casefold() in folded:
            fail("duplicate_asset", "Reserved, duplicate or case-folded asset path", path=rel)
        if not isinstance(item.get("bytes"), int) or isinstance(item["bytes"], bool) or item["bytes"] < 0:
            fail("invalid_type", "Asset byte count must be a nonnegative integer", path=rel)
        if not isinstance(item.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            fail("invalid_hash", "Asset SHA-256 must be lowercase hex", path=rel)
        _str(item.get("role"), "asset.role")
        p = _file(base, rel)
        total += p.stat().st_size
        if total > MAX_BYTES or len(mapped) >= MAX_FILES:
            fail("size_limit", "Bundle exceeds file count or byte limit")
        raw = p.read_bytes()
        if len(raw) != item["bytes"] or _digest(raw) != item["sha256"]:
            fail("hash_mismatch", "Asset bytes differ from manifest", path=rel)
        mapped[rel] = item
        folded.add(rel.casefold())
    for key in ("records", "relations"):
        rel = _path(manifest.get(key))
        if rel not in mapped:
            fail("unhashed_core_file", "Core file must be present in assets", field=key, path=rel)
    if manifest["records"] == manifest["relations"]:
        fail("invalid_bundle", "Records and relations require distinct files")
    raw_records = _file(base, manifest["records"]).read_bytes()
    records = _jsonl(raw_records, manifest["records"])
    raw_relations = _file(base, manifest["relations"]).read_bytes()
    relations = _jsonl(raw_relations, manifest["relations"])
    index = _validate_records(records, relations)
    heads = manifest.get("heads")
    if not isinstance(heads, dict) or set(heads) != {key[0] for key in index}:
        fail("invalid_heads", "heads must select one revision for every record id")
    for rid, rev in heads.items():
        _str(rev, "heads revision")
        if (rid, rev) not in index:
            fail("invalid_heads", "Head references an absent revision", id=rid, rev=rev)
    origins = manifest.get("origins", [])
    if not isinstance(origins, list):
        fail("invalid_type", "origins must be an array")
    seen_origins = set()
    for origin in origins:
        if not isinstance(origin, dict):
            fail("invalid_type", "Origin must be an object")
        for field in ("id", "format", "asset"):
            _str(origin.get(field), "origin." + field)
        if origin["id"] in seen_origins:
            fail("duplicate_origin", "Origin id is repeated", id=origin["id"])
        seen_origins.add(origin["id"])
        if _path(origin["asset"]) not in mapped:
            fail("missing_origin_asset", "Origin asset must be hashed in the manifest", id=origin["id"])
        _path(origin.get("root", ""), empty=True)
    count = 0
    for folder, dirs, files in os.walk(base, followlinks=False):
        for name in dirs + files:
            p = Path(folder) / name
            if p.is_symlink():
                fail("symlink", "Bundle contains a symbolic link", path=p.relative_to(base).as_posix())
        for name in files:
            count += 1
            if count > MAX_FILES:
                fail("size_limit", "Bundle file count limit exceeded")
            rel = (Path(folder) / name).relative_to(base).as_posix()
            if rel != MANIFEST and rel not in mapped:
                warnings.append({"code": "unlisted_file", "path": rel})
    return {"base": base, "manifest": manifest, "records": records, "relations": relations,
            "index": index, "records_sha256": _digest(raw_records), "relations_sha256": _digest(raw_relations), "warnings": warnings,
            "unsupported_profiles": unknown}


def _error_report(error):
    diagnostic = error.diagnostic if isinstance(error, AOCXError) else {"code": type(error).__name__, "message": str(error)}
    status = "unsupported" if diagnostic["code"] in ("unsupported_version", "unsupported_required_profile") else "failed"
    return {"status": status, "errors": [diagnostic], "warnings": []}


def validate_bundle(path, preserve_only=False):
    try:
        data = _load_bundle(path, preserve_only)
        return {"status": "passed", "errors": [], "warnings": data["warnings"],
                "namespace": data["manifest"]["namespace"], "records_sha256": data["records_sha256"], "relations_sha256": data["relations_sha256"],
                "counts": {"records": len(data["records"]), "relations": len(data["relations"]), "assets": len(data["manifest"]["assets"])},
                "preserve_only": preserve_only, "required_profiles_supported": not data["unsupported_profiles"],
                "scope": "Structure, pinned references and exact stored bytes; content truth and actions are external"}
    except (ValueError, OSError, UnicodeError, RecursionError) as error:
        return _error_report(error)


def create_bundle(records, relations, out, namespace, *, profiles=None, required_profiles=None,
                  heads=None, assets=None, origins=None, extensions=None):
    _str(namespace, "namespace")
    records, relations = deepcopy(records), deepcopy(relations)
    index = _validate_records(records, relations)
    if heads is None:
        heads = {}
        for rid, rev in index:
            if rid in heads:
                fail("ambiguous_heads", "Specify heads when an id has multiple revisions", id=rid)
            heads[rid] = rev
    payload = dict(assets or {})
    if any(name in payload for name in (MANIFEST, "records.jsonl", "relations.jsonl")):
        fail("reserved_asset", "Attachments cannot replace core bundle files")
    payload["records.jsonl"] = b"".join(_dump(r) for r in records)
    payload["relations.jsonl"] = b"".join(_dump(r) for r in relations)
    folded = set()
    total = 0
    for rel, raw in payload.items():
        _path(rel)
        if rel.casefold() in folded:
            fail("duplicate_asset", "Case-folded attachment path collision", path=rel)
        folded.add(rel.casefold())
        if not isinstance(raw, bytes):
            fail("invalid_type", "Asset content must be bytes", path=rel)
        total += len(raw)
    if total > MAX_BYTES or len(payload) > MAX_FILES:
        fail("size_limit", "Bundle exceeds size or count limits")
    manifest = {"format": FORMAT, "version": VERSION, "namespace": namespace,
                "records": "records.jsonl", "relations": "relations.jsonl", "heads": deepcopy(heads),
                "profiles": list(profiles or ["core/1"]), "required_profiles": list(required_profiles or ["core/1"]),
                "assets": [{"path": rel, "sha256": _digest(raw), "bytes": len(raw),
                            "role": "records" if rel == "records.jsonl" else "relations" if rel == "relations.jsonl" else "attachment"}
                           for rel, raw in sorted(payload.items())], "origins": deepcopy(origins or [])}
    if extensions is not None:
        manifest["extensions"] = deepcopy(extensions)
    destination = Path(out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir(exist_ok=False)
    try:
        for rel, raw in payload.items():
            target = destination / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as f:
                f.write(raw)
        with (destination / MANIFEST).open("xb") as f:
            f.write(_dump(manifest, pretty=True))
        report = validate_bundle(destination, preserve_only=True)
        if report["status"] != "passed":
            fail("invalid_created_bundle", "Created data failed validation", errors=report["errors"])
    except BaseException:
        shutil.rmtree(destination)
        raise
    report["path"] = str(destination.resolve())
    return report


def _zip_read(raw):
    if len(raw) > MAX_BYTES:
        fail("size_limit", "ZIP input exceeds the byte limit")
    files, folded, total = {}, set(), 0
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_FILES:
            fail("size_limit", "ZIP member count limit exceeded")
        for item in entries:
            name = item.filename.rstrip("/") if item.is_dir() else item.filename
            _path(name)
            if name.casefold() in folded:
                fail("duplicate_zip_member", "ZIP member names collide", path=name)
            folded.add(name.casefold())
            mode = item.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if kind not in (0, stat.S_IFREG, stat.S_IFDIR) or stat.S_ISLNK(mode):
                fail("unsafe_zip_member", "ZIP contains a nonregular member", path=name)
            if item.flag_bits & 1:
                fail("encrypted_zip", "Encrypted ZIP members are unsupported", path=name)
            if item.is_dir():
                continue
            total += item.file_size
            if total > MAX_BYTES or item.file_size < 0:
                fail("size_limit", "ZIP uncompressed byte limit exceeded")
            with archive.open(item) as f:
                data = f.read(item.file_size + 1)
            if len(data) != item.file_size:
                fail("zip_size_mismatch", "ZIP member size is inconsistent", path=name)
            files[name] = data
    # Reject a file that is also an ancestor of another file.
    for name in files:
        for parent in PurePosixPath(name).parents:
            if parent.as_posix() != "." and parent.as_posix() in files:
                fail("zip_path_collision", "ZIP file is an ancestor of another member", path=name)
    return files


def _zip_write(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(files.items()):
            _path(name)
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, raw)
    return stream.getvalue()


def _adapter(kind):
    if kind not in ("aoci", "gbcx"):
        fail("unsupported_adapter", "Supported importers are aoci and gbcx", adapter=kind)
    path = Path(__file__).resolve().parent / "adapters" / (kind + ".py")
    spec = importlib.util.spec_from_file_location("aocx_adapter_" + kind, path)
    if spec is None or spec.loader is None:
        fail("missing_adapter", "Adapter module is unavailable", adapter=kind)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rooted(files, marker):
    candidates = [p for p in files if p == marker or p.endswith("/" + marker)]
    if len(candidates) != 1:
        fail("ambiguous_origin_root", "Archive must contain exactly one import entry", marker=marker, found=candidates)
    root = str(PurePosixPath(candidates[0]).parent)
    root = "" if root == "." else root
    prefix = root + "/" if root else ""
    return root, {p[len(prefix):]: raw for p, raw in files.items() if p.startswith(prefix)}


def import_bundle(input_path, out, namespace, kind):
    adapter = _adapter(kind)
    source = Path(input_path)
    if source.is_symlink():
        fail("symlink", "Import input must be an explicit regular file or directory")
    capture = "zip"
    if source.is_dir():
        capture = "directory"
        files = {}
        if kind == "aoci":
            paths = adapter.collect_paths(source)
        else:
            paths = []
            for folder, dirs, names in os.walk(source, followlinks=False):
                for name in dirs + names:
                    if (Path(folder) / name).is_symlink():
                        fail("symlink", "Import directory contains a symbolic link")
                for name in names:
                    paths.append((Path(folder) / name).relative_to(source).as_posix())
                    if len(paths) > MAX_FILES:
                        fail("size_limit", "Import file count exceeds the limit")
        total = 0
        for path in paths:
            p = _file(source.resolve(), path)
            total += p.stat().st_size
            if total > MAX_BYTES:
                fail("size_limit", "Import directory exceeds the byte limit")
            files[path] = p.read_bytes()
        original = _zip_write(files)
        root = ""
    else:
        if not source.is_file() or source.stat().st_size > MAX_BYTES:
            fail("invalid_input", "Expected a bounded regular ZIP input")
        original = source.read_bytes()
        root, files = _rooted(_zip_read(original), "aoci.txt" if kind == "aoci" else "PROTOCOL.json")
        if kind == "aoci":
            native_text = adapter._text(files["aoci.txt"])
            paths = ["aoci.txt"]
            if adapter._layout(native_text) == "volumes-v1":
                paths += [d["path"] for d in adapter._declarations(native_text)]
            if any(p not in files for p in paths):
                fail("missing_native_asset", "AOCI archive lacks a declared asset")
            files = {p: files[p] for p in paths}
    projection = adapter.project(files)
    profile = projection["profile"]
    origin = {"id": "legacy", "format": "GBCX/1" if kind == "gbcx" else profile,
              "asset": "assets/original.zip", "root": root, "capture": capture}
    report = create_bundle(projection["records"], projection["relations"], out, namespace,
                           profiles=["core/1", profile], assets={"assets/original.zip": original,
                           "assets/import_report.json": _dump({k: v for k, v in projection.items() if k not in ("records", "relations")}, pretty=True)},
                           origins=[origin], extensions={"importer": {"profile": profile, "scope": "Native bytes preserved; semantic projection bounded by adapter"}})
    report["import_warnings"] = projection.get("warnings", [])
    report["origin_sha256"] = _digest(original)
    return report


def restore(path, out, origin="legacy"):
    data = _load_bundle(path, preserve_only=True)
    found = [x for x in data["manifest"].get("origins", []) if x["id"] == origin]
    if len(found) != 1:
        fail("missing_origin", "Requested origin was not found", origin=origin)
    raw = _file(data["base"], found[0]["asset"]).read_bytes()
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as f:
        f.write(raw)
    return {"status": "passed", "path": str(target.resolve()), "bytes": len(raw), "sha256": _digest(raw),
            "scope": "Restored unchanged origin archive; edited projections are not applied to native data"}


def _closure(data, selected):
    adjacency = {}
    for edge in data["relations"]:
        if edge["kind"] in FOLLOW:
            adjacency.setdefault(_ref(edge["from"], "from"), []).append(_ref(edge["to"], "to"))
    needed, queue = set(selected), deque(selected)
    while queue:
        key = queue.popleft()
        targets = list(adjacency.get(key, []))
        targets.extend(_ref(c["ref"], "condition.ref") for c in data["index"][key].get("conditions", []) if "ref" in c)
        for target in targets:
            if target not in needed:
                needed.add(target)
                queue.append(target)
    return needed


def capsule(path, select=None, full=False):
    data = _load_bundle(path)
    if select:
        selected = set()
        for rid in select:
            if rid not in data["manifest"]["heads"]:
                fail("unknown_selection", "Selected record id has no head", id=rid)
            selected.add((rid, data["manifest"]["heads"][rid]))
        needed = _closure(data, selected)
    else:
        needed = set(data["index"])
        selected = set(needed)
    records = [r for r in data["records"] if (r["id"], r["rev"]) in needed]
    relations = [r for r in data["relations"] if _ref(r["from"], "from") in needed and _ref(r["to"], "to") in needed]
    omitted = set()
    rows = []
    for r in records:
        extra = {k: deepcopy(v) for k, v in r.items() if k not in ("id", "rev", "kind", "text")}
        if not full:
            for key in OMIT:
                if key in extra:
                    omitted.add(key)
                    del extra[key]
        rows.append(["record", r["id"], r["rev"], r["kind"], r["text"], extra])
    for r in relations:
        extra = {k: deepcopy(v) for k, v in r.items() if k not in ("id", "from", "kind", "to")}
        if not full:
            for key in OMIT:
                if key in extra:
                    omitted.add(key)
                    del extra[key]
        rows.append(["relation", r["id"], r["from"], r["kind"], r["to"], extra])
    header = {"format": FORMAT, "version": VERSION, "encoding": "table-jsonl/1",
              "projection": "full" if full else "handoff", "source_records_sha256": data["records_sha256"],
              "source_relations_sha256": data["relations_sha256"], "namespace": data["manifest"]["namespace"],
              "columns": {"record": ["id", "rev", "kind", "text", "extra"], "relation": ["id", "from", "kind", "to", "extra"]},
              "counts": {"records": len(records), "relations": len(relations)}, "omitted_fields": sorted(omitted),
              "selection": {"mode": "heads", "refs": [{"id": key[0], "rev": key[1]} for key in sorted(selected)]} if select else {"mode": "all"},
              "omitted_records": len(data["records"]) - len(records),
              "omitted_relations": len(data["relations"]) - len(relations)}
    return _dump(header) + b"".join(_dump(row) for row in rows)


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


def check_view(path, view):
    try:
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
            protected = {k: v for k, v in data["index"][key].items() if k not in ("text", "body", "extensions")}
            if _content(entry.get("protected")) != _content(protected):
                fail("changed_protected_fields", "View changed pinned or protected source metadata", ref=entry["ref"])
        missing = _closure(data, selected) - selected
        if missing:
            fail("view_incomplete_closure", "View omits condition or prerequisite records", missing=[{"id": k[0], "rev": k[1]} for k in sorted(missing)])
        evaluation = view.get("evaluation")
        if not isinstance(evaluation, dict) or evaluation.get("status") not in ("unassessed", "passed"):
            fail("invalid_view_evaluation", "Expected declared evaluation status unassessed or passed")
        report = evaluation.get("report")
        if report is not None:
            _path(report)
            if report not in {a["path"] for a in data["manifest"]["assets"]}:
                fail("missing_evaluation_report", "Evaluation report must be a hashed bundle asset", path=report)
        if evaluation["status"] == "passed" and report is None:
            fail("missing_evaluation_report", "Declared passed evaluation requires a report asset")
        return {"status": "passed", "structural": "passed", "eligible": evaluation["status"] == "passed" and report is not None,
                "semantic_evaluation_verified": False, "eligibility_basis": "Declared evaluation status and bound report; host evaluates the actual evidence",
                "errors": [], "warnings": [], "entries": len(entries)}
    except (ValueError, OSError, UnicodeError, RecursionError) as error:
        result = _error_report(error)
        result.update(structural="failed", eligible=False, semantic_evaluation_verified=False)
        return result


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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    c = commands.add_parser("create")
    for name in ("records", "relations", "out", "namespace"):
        c.add_argument("--" + name, required=True)
    c.add_argument("--heads")
    for name in ("import-aoci", "import-gbcx"):
        c = commands.add_parser(name)
        c.add_argument("input")
        c.add_argument("out")
        c.add_argument("--namespace", required=True)
    c = commands.add_parser("validate")
    c.add_argument("bundle")
    c.add_argument("--preserve-only", action="store_true")
    c = commands.add_parser("restore")
    c.add_argument("bundle")
    c.add_argument("out")
    c.add_argument("--origin", default="legacy")
    c = commands.add_parser("capsule")
    c.add_argument("bundle")
    c.add_argument("--out", required=True)
    c.add_argument("--select", action="append")
    c.add_argument("--full", action="store_true")
    c = commands.add_parser("check-view")
    c.add_argument("bundle")
    c.add_argument("view")
    c = commands.add_parser("negotiate")
    c.add_argument("offer")
    c.add_argument("reader")
    c = commands.add_parser("merge-check")
    for name in ("base", "left", "right"):
        c.add_argument(name)
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            report = create_bundle(_jsonl(Path(args.records).read_bytes(), args.records), _jsonl(Path(args.relations).read_bytes(), args.relations), args.out, args.namespace,
                                   heads=_json(Path(args.heads).read_bytes()) if args.heads else None)
        elif args.command.startswith("import-"):
            report = import_bundle(args.input, args.out, args.namespace, args.command.split("-", 1)[1])
        elif args.command == "validate":
            report = validate_bundle(args.bundle, args.preserve_only)
        elif args.command == "restore":
            report = restore(args.bundle, args.out, args.origin)
        elif args.command == "capsule":
            raw = capsule(args.bundle, args.select, args.full)
            target = Path(args.out)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as f:
                f.write(raw)
            report = {"status": "passed", "path": str(target.resolve()), "bytes": len(raw), "sha256": _digest(raw)}
        elif args.command == "check-view":
            report = check_view(args.bundle, args.view)
        elif args.command == "negotiate":
            report = negotiate(_json(Path(args.offer).read_bytes()), _json(Path(args.reader).read_bytes()))
        else:
            report = merge_check(args.base, args.left, args.right)
    except (ValueError, OSError, UnicodeError, RecursionError, zipfile.BadZipFile, RuntimeError) as error:
        report = _error_report(error)
    sys.stdout.buffer.write(_dump(report, pretty=True))
    return 0 if report["status"] in ("passed", "clean") else 2


if __name__ == "__main__":
    raise SystemExit(main())
