#!/usr/bin/env python3
"""AOCX exchange CLI and backward-compatible Python entry point.

The executable core lives in aocx_core. This entry point also supports loading
by absolute file path from a host application or an existing handoff script.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = str(Path(__file__).resolve().parent)
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from aocx_core.common import (
    FORMAT, VERSION, MANIFEST, PROFILES, CODECS, MAX_FILES, MAX_BYTES, FOLLOW, OMIT,
    AOCXError, fail, _pairs, _number, _constant, _json, _dump, _content, _digest,
    _path, _file, _str, _string_list, _ref, _jsonl, _error_report,
)
from aocx_core.model import GraphIndex, _validate_records, _closure
from aocx_core.storage import _load_bundle, validate_bundle, create_bundle, _zip_read, _zip_write
from aocx_core.legacy import _adapter, _rooted, import_bundle, restore
from aocx_core.views import capsule, parse_capsule, check_view, view_digest
from aocx_core.negotiation import negotiate, merge_check
from aocx_core.contracts import make_contract
from aocx_core.optimizer import compile_context, recover_context, verify_representation
from aocx_core.codecs import Codec, CodecRegistry, default_registry, decode_representation
from aocx_core.logic import parse_logic, render_logic, validate_logic
from aocx_core.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
