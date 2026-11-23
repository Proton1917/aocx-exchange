"""Read-only, bounded AOCI-CODE projection into AOCX records.

The container owns original asset bytes. This module does not render native
writes, alter AOCI receipts, contact an MCP server, or execute source content.
Reviewed source: aoci-spec/aoci-code at 3d8e4b0048b7ae93d671ffae39db73a44db434d3.
"""
from __future__ import annotations

import hashlib
import posixpath
import re
from pathlib import Path, PurePosixPath

ROOT_MARKER = "#AOCI-ROOT-MANIFEST: 1"
PINNED_COMMIT = "3d8e4b0048b7ae93d671ffae39db73a44db434d3"
_ENTRY = re.compile(r"^([^\[\s][^\[]*?)\[([^\]]*)\]:\s?(.*)$", re.ASCII)
_ENTRY_EXTENDED = re.compile(r"^(\S.*?)\[([^\[\]]*)\]:\s?(F:.*)$", re.ASCII)
_DIRECTORY = re.compile(r"^===(.*?)((?:[A-Za-z]:)?/[^\s=(（]+)(.*)===\s*$", re.ASCII)
_SEPARATOR = re.compile(r"^={3,}.*={3,}\s*$", re.ASCII)
_DATABASE = re.compile(r"^===.*?(database://[^/\s]+/[^/\s]+/)===\s*$", re.ASCII)


def _text(raw: bytes) -> str:
    if not isinstance(raw, bytes):
        raise ValueError("AOCI input values must be bytes")
    return raw.decode("utf-8-sig")


def _safe_path(path: str) -> str:
    if not path or "\\" in path or "\x00" in path or ":" in path:
        raise ValueError("Unsafe native asset path: " + repr(path))
    p = PurePosixPath(path)
    if p.is_absolute() or path != p.as_posix() or any(x in ("", ".", "..") for x in path.split("/")):
        raise ValueError("Native asset path must be canonical and relative: " + repr(path))
    return path


def _layout(text: str) -> str:
    first = text.splitlines()[0] if text.splitlines() else ""
    if first == ROOT_MARKER:
        return "volumes-v1"
    if first.startswith("#AOCI-ROOT-MANIFEST"):
        raise ValueError("Malformed AOCI Root marker")
    return "legacy"


def _declarations(text: str) -> list[dict]:
    result: list[dict] = []
    ids: set[str] = set()
    paths: set[str] = set()
    for line_no, line in enumerate(text.splitlines(), 1):
        if not line.startswith("#Volume:"):
            continue
        tokens = line[len("#Volume:"):].strip().split()
        pairs = []
        for token in tokens:
            if "=" not in token:
                raise ValueError(f"Invalid Volume declaration on line {line_no}")
            key, value = token.split("=", 1)
            pairs.append((key, value))
        expected = ["id", "kind", "path", "format", "depends"]
        if len(pairs) not in (5, 6) or [k for k, _ in pairs[:5]] != expected:
            raise ValueError(f"Unsupported Volume declaration on line {line_no}")
        if len(pairs) == 6 and pairs[5][0] != "state":
            raise ValueError(f"Unsupported sixth Volume field on line {line_no}")
        d = dict(pairs)
        if any(not v for v in d.values()):
            raise ValueError(f"Empty Volume declaration value on line {line_no}")
        d.setdefault("state", "enabled")
        if d["state"] not in ("enabled", "disabled"):
            raise ValueError("Unsupported native Volume state: " + d["state"])
        _safe_path(d["path"])
        if d["id"] in ids or d["path"].casefold() in paths:
            raise ValueError("Duplicate native Volume id or case-folded path")
        if d["path"].casefold() == "aoci.txt":
            raise ValueError("Root asset cannot also be a Volume")
        ids.add(d["id"])
        paths.add(d["path"].casefold())
        d["line"] = line_no
        result.append(d)
    metas = [d for d in result if d["kind"] == "meta"]
    if len(metas) != 1 or metas[0]["state"] != "enabled":
        raise ValueError("Exactly one enabled Meta Volume is required")
    for d in result:
        for target in d["depends"].split(","):
            if target != "-" and target not in ids:
                raise ValueError("Volume dependency is undeclared: " + target)
    return result


def collect_paths(root: Path) -> list[str]:
    """Discover only aoci.txt and its declared assets under a directory root.

    A directory fixture uses aoci.txt as the explicit entry. Callers with a
    different configured index path can assemble the byte dictionary directly.
    All declared assets, including disabled assets, must exist in this profile.
    """
    base = Path(root).resolve(strict=True)
    if not base.is_dir():
        raise ValueError("AOCI root must be a directory")

    def regular(rel: str) -> Path:
        _safe_path(rel)
        p = base
        for part in PurePosixPath(rel).parts:
            p = p / part
            if p.is_symlink():
                raise ValueError("Symlink native asset or ancestor: " + rel)
        if not p.is_file() or not p.resolve(strict=True).is_relative_to(base):
            raise ValueError("Missing or unsafe native asset: " + rel)
        return p

    entry = regular("aoci.txt")
    text = _text(entry.read_bytes())
    paths = ["aoci.txt"]
    if _layout(text) == "volumes-v1":
        for d in _declarations(text):
            regular(d["path"])
            paths.append(d["path"])
    return paths


def _tag(raw: str) -> dict[str, str]:
    value = raw.strip()
    if not value or "," in value or "，" in value:
        return {}
    if "." in value:
        parts = value.split(".")
        keys = ["A", "B", "C", "E"] if len(parts) == 4 else ["A", "B", "C", "D", "E"]
        return dict(zip(keys, parts)) if len(parts) in (4, 5) and all(p.strip() for p in parts) else {}
    digit = next((i for i, ch in enumerate(value) if "0" <= ch <= "9"), -1)
    if digit < 2 or digit >= len(value) - 1:
        return {}
    answer = {"A": value[0], "B": value[1:digit], "C": value[digit], "E": value[-1]}
    if value[digit + 1:-1]:
        answer["D"] = value[digit + 1:-1]
    return answer


def _fras(rest: str) -> tuple[dict[str, str], list[str]]:
    fields = {"F": "", "R": "", "A": "", "S": ""}
    s_parts, unknown = [], []
    for part in rest.split(" | "):
        p = part.strip()
        if p[:2] in ("F:", "R:", "A:"):
            fields[p[0]] = p[2:].strip()
        elif p.startswith("S:") or re.match(r"^S[0-9]+:", p):
            s_parts.append(p.split(":", 1)[1].strip())
        else:
            unknown.append(part)
    fields["S"] = " | ".join(s_parts)
    return fields, unknown


def _code_header(line: str) -> str | None:
    m = _DIRECTORY.match(line)
    if not m:
        return None
    path, remainder = m[2], m[3]
    note_like = path.endswith("/") and remainder.startswith((" ", "\t"))
    if remainder.endswith("/") and not note_like and not re.search(r"\s(?:[A-Za-z]:)?/", remainder, re.ASCII):
        path += remainder
    return path.strip().rstrip("/") or "/"


def _warning(warnings: list, code: str, path: str, line: int | None = None, **extra) -> None:
    w = {"code": code, "path": path, **extra}
    if line is not None:
        w["line"] = line
    warnings.append(w)


def _asset_record(path: str, raw: bytes, kind: str, declaration: dict | None) -> dict:
    anchor = {"type": "aoci/asset", "path": path, "kind": kind,
              "sha256": hashlib.sha256(raw).hexdigest(), "declaration": declaration}
    if kind in ("root", "meta"):
        anchor["native_context"] = raw.decode("utf-8")
    elif kind == "legacy":
        anchor["native_context"] = _legacy_header(raw)
    return {
        "id": "aoci:asset:" + path, "rev": "1", "kind": "source",
        "text": "AOCI " + kind + " asset: " + path,
        "body": {"native_path": path, "native_kind": kind, "declaration": declaration,
                 "raw_text": raw.decode("utf-8"), "sha256": hashlib.sha256(raw).hexdigest()},
        "anchors": [anchor],
        "provenance": [{"origin": "legacy", "path": path}],
    }


def _legacy_header(raw: bytes) -> str:
    lines = raw.decode("utf-8").splitlines(keepends=True)
    stop = next((i for i, line in enumerate(lines) if _SEPARATOR.match((line.lstrip("\ufeff") if i == 0 else line).rstrip("\r\n"))), len(lines))
    return "".join(lines[:stop])


def _dictionary_text(raw: bytes, scope: str) -> str:
    """Keep the exact declared dictionary text; unsupported headings stay opaque."""
    lines = raw.decode("utf-8").splitlines(keepends=True)
    marker = "#[Tag dictionary: " + scope + "]"
    starts = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == marker]
    if len(starts) != 1:
        return raw.decode("utf-8")
    start = starts[0]
    stop = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("#[Tag dictionary:")), len(lines))
    return "".join(lines[start:stop])


def project(files: dict[str, bytes]) -> dict:
    """Project recognized native objects; preserve unsupported text in source records.

    Returns records, relations, warnings and profile. No imported field becomes
    a verification status or workflow precondition. Mapping is deterministic.
    """
    if "aoci.txt" not in files:
        raise ValueError("AOCI input must include aoci.txt")
    for path, raw in files.items():
        _safe_path(path)
        _text(raw)
    text = _text(files["aoci.txt"])
    layout = _layout(text)
    declarations = _declarations(text) if layout == "volumes-v1" else []
    profile = "aoci-code/volumes-v1+fras-v2" if declarations else "aoci-code/legacy"
    records, warnings, relations = [], [], []
    records.append(_asset_record("aoci.txt", files["aoci.txt"], "root" if declarations else "legacy", None))
    meta = next((d for d in declarations if d["kind"] == "meta"), None)
    for d in declarations:
        if d["path"] not in files:
            raise ValueError("Declared native asset missing: " + d["path"])
        records.append(_asset_record(d["path"], files[d["path"]], d["kind"], d))
    declared = {"aoci.txt", *(d["path"] for d in declarations)}
    for path in sorted(set(files) - declared):
        records.append(_asset_record(path, files[path], "undeclared", None))
        _warning(warnings, "undeclared_asset_preserved", path)
    objects = declarations if declarations else [{"id": "legacy", "kind": "code", "path": "aoci.txt", "format": "legacy", "state": "enabled"}]
    entries: dict[str, dict] = {}
    for d in objects:
        path, kind = d["path"], d["kind"]
        if d["state"] == "disabled" or kind == "meta":
            continue
        if kind not in ("code", "database"):
            _warning(warnings, "unsupported_volume_kind_preserved", path, native_kind=kind)
            continue
        expected = {"code": ("object-fras-v2", "#AOCI-CODE-VOLUME: 1"), "database": ("table-fras-v2", "#AOCI-DATABASE-VOLUME: 1")}[kind]
        lines = _text(files[path]).splitlines()
        if declarations and (d["format"] != expected[0] or not lines or lines[0] != expected[1]):
            _warning(warnings, "unsupported_volume_format_preserved", path, native_format=d["format"])
            continue
        headers = [_code_header(line) for line in lines] if kind == "code" else []
        directories = [h for h in headers if h is not None]
        base = None
        if directories:
            if "/<repository>" in directories and all(h == "/<repository>" or h.startswith("/<repository>/") for h in directories):
                base = "/<repository>"
            elif all(not any(c in h for c in " =(（") for h in directories):
                try:
                    common = posixpath.commonpath(directories)
                except ValueError:
                    common = ""
                if common and common == directories[0]:
                    base = common
                    _warning(warnings, "historical_root_projection", path, root=base)
            if base is None:
                _warning(warnings, "ambiguous_historical_roots_preserved", path)
        section = None
        for line_no, line in enumerate(lines, 1):
            header = _code_header(line) if kind == "code" else _DATABASE.match(line)
            if header is not None:
                section = header if kind == "code" else header[1]
                continue
            if _SEPARATOR.match(line):
                section = None
                continue
            match = _ENTRY.match(line) or _ENTRY_EXTENDED.match(line)
            if match is None or not match[1].strip():
                if not line.strip().startswith("#") and "[" in line:
                    _warning(warnings, "unparsed_entry_like_line", path, line_no)
                continue
            name, tag = match[1].strip(), match[2]
            fields, unknown = _fras(match[3])
            native_identity = None
            if section is None:
                _warning(warnings, "entry_outside_section_preserved", path, line_no)
                continue
            if kind == "code" and base is not None:
                rel = posixpath.relpath(section, base)
                rel = name if rel == "." else rel + "/" + name
                try:
                    native_identity = "code:" + _safe_path(rel)
                except ValueError:
                    _warning(warnings, "unsafe_object_identity_preserved", path, line_no)
            elif kind == "database" and re.fullmatch(r"[A-Za-z0-9_.-]+", name):
                native_identity = section + name
            if native_identity is None:
                _warning(warnings, "opaque_object_identity", path, line_no, name=name)
                continue
            body = {
                "native_identity": native_identity, "native_object_type": "file" if kind == "code" else "table",
                "raw_entry": line, "name": name, "tag_raw": tag, "tag_axes": _tag(tag),
                "fras": fields, "constraints": fields["S"], "volume": d,
                "section": section, "unknown_segments": unknown,
                "meta_dictionary": {"asset": meta["path"], "scope": kind,
                                    "record_ref": {"id": "aoci:asset:" + meta["path"], "rev": "1"}} if meta else {"scope": "legacy-header", "asset": "aoci.txt"},
            }
            dictionary_binding = dict(body["meta_dictionary"])
            dictionary_raw = files[meta["path"]] if meta else files["aoci.txt"]
            dictionary_binding["asset_sha256"] = hashlib.sha256(dictionary_raw).hexdigest()
            dictionary_binding["dictionary_text"] = _dictionary_text(dictionary_raw, kind) if meta else _legacy_header(dictionary_raw)
            anchors = [
                {"type": "aoci/fras", "R": fields["R"], "A": fields["A"], "S": fields["S"], "unknown_segments": unknown},
                {"type": "aoci/identity-and-tag", "native_identity": native_identity,
                 "tag_raw": tag, "tag_axes": _tag(tag), "meta_dictionary": dictionary_binding},
            ]
            rec = {"id": "aoci:" + native_identity, "rev": "1", "kind": "entity",
                   "text": fields["F"] or line, "body": body,
                   "anchors": anchors,
                   "provenance": [{"origin": "legacy", "path": path, "line": line_no}]}
            if native_identity in entries:
                old = entries[native_identity]
                if name.startswith("#") and old["body"]["section"] == section:
                    body["historical_duplicates"] = old["body"].get("historical_duplicates", []) + [{"raw_entry": old["body"]["raw_entry"], "provenance": old["provenance"]}]
                    _warning(warnings, "historical_hash_filename_duplicate", path, line_no, native_identity=native_identity)
                else:
                    raise ValueError("Duplicate native object identity: " + native_identity)
            entries[native_identity] = rec
            if unknown:
                _warning(warnings, "unknown_entry_segments_preserved", path, line_no, segments=unknown)
            if not body["tag_axes"]:
                _warning(warnings, "unparsed_tag_preserved", path, line_no, tag=tag)
    records.extend(entries.values())
    for native, rec in entries.items():
        relation_text = rec["body"]["fras"]["R"]
        if not relation_text or relation_text == "-":
            continue
        seen = set()
        for target in relation_text.split(","):
            target = target.strip()
            if target in seen:
                continue
            seen.add(target)
            other = entries.get(target)
            if other is None:
                p = rec["provenance"][0]
                _warning(warnings, "unresolved_native_relation", p["path"], p["line"], source=native, target=target)
                continue
            rid = hashlib.sha256((native + "\x00" + target).encode()).hexdigest()
            relations.append({"id": "aoci:relation:" + rid, "from": {"id": rec["id"], "rev": "1"},
                              "to": {"id": other["id"], "rev": "1"}, "kind": "relates_to",
                              "body": {"native_field": "R", "native_target": target}})
    return {"records": records, "relations": relations, "warnings": warnings, "profile": profile}
