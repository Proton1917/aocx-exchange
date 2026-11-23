"""Source-format imports and exact origin recovery through AOCX archives."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path, PurePosixPath

from .common import MAX_FILES, MAX_BYTES, _file, _dump, _digest, fail
from .storage import _load_bundle, create_bundle, _zip_read, _zip_write


def _adapter(kind):
    if kind not in ("aoci", "gbcx"):
        fail("unsupported_adapter", "Supported importers are aoci and gbcx", adapter=kind)
    path = Path(__file__).resolve().parents[1] / "adapters" / (kind + ".py")
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
