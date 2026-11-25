"""Shared JSON, diagnostics and bounded path contracts for AOCX."""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import PurePosixPath

FORMAT = "AOCX"
VERSION = "1.0"
MANIFEST = "aocx.json"
PROFILES = {"core/1", "logic/1", "gbcx/1", "aoci-code/volumes-v1+fras-v2", "aoci-code/legacy"}
CODECS = {"jsonl/1", "canonical-jsonl/1", "table-jsonl/1", "babeltele-view/1",
          "aocx-expr/1", "aocx-expr-dict/1", "json/1"}
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



def _error_report(error):
    diagnostic = error.diagnostic if isinstance(error, AOCXError) else {"code": type(error).__name__, "message": str(error)}
    status = "unsupported" if diagnostic["code"] in ("unsupported_version", "unsupported_required_profile") else "failed"
    return {"status": status, "errors": [diagnostic], "warnings": []}
