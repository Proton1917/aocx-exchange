"""AOCX archive loading, creation, validation and exact resource bytes."""
from __future__ import annotations

import io
import os
import re
import shutil
import stat
import zipfile
from copy import deepcopy
from pathlib import Path, PurePosixPath

from .common import (FORMAT, VERSION, MANIFEST, PROFILES, MAX_FILES, MAX_BYTES,
                     _json, _file, _str, _string_list, _path, _digest, _jsonl,
                     _dump, _error_report, fail)
from .model import GraphIndex, _validate_records


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
    core_bytes = {}
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
        if rel in (manifest.get("records"), manifest.get("relations")):
            core_bytes[rel] = raw
        folded.add(rel.casefold())
    for key in ("records", "relations"):
        rel = _path(manifest.get(key))
        if rel not in mapped:
            fail("unhashed_core_file", "Core file must be present in assets", field=key, path=rel)
    if manifest["records"] == manifest["relations"]:
        fail("invalid_bundle", "Records and relations require distinct files")
    raw_records = core_bytes[manifest["records"]]
    records = _jsonl(raw_records, manifest["records"])
    raw_relations = core_bytes[manifest["relations"]]
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
            "index": index, "graph": GraphIndex(records, relations, index),
            "records_sha256": mapped[manifest["records"]]["sha256"],
            "relations_sha256": mapped[manifest["relations"]]["sha256"], "warnings": warnings,
            "unsupported_profiles": unknown}



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
