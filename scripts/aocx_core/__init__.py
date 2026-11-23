"""AOCX representation core with modular archive and compatibility services.

Use explicit submodules for extension APIs. The public exchange operations keep
same signatures as the historical scripts/aocx.py entry point.
"""
from .common import AOCXError
from .model import GraphIndex
from .storage import create_bundle, validate_bundle
from .legacy import import_bundle, restore
from .views import capsule, parse_capsule, check_view, view_digest
from .negotiation import negotiate, merge_check
from .contracts import make_contract
from .optimizer import compile_context, recover_context, verify_representation
from .codecs import Codec, CodecRegistry, default_registry, decode_representation
from .logic import parse_logic, render_logic, validate_logic

__all__ = [
    "AOCXError", "GraphIndex", "create_bundle", "validate_bundle", "import_bundle",
    "restore", "capsule", "parse_capsule", "check_view", "view_digest", "negotiate", "merge_check",
    "make_contract", "compile_context", "recover_context", "verify_representation",
    "Codec", "CodecRegistry", "default_registry", "decode_representation",
    "parse_logic", "render_logic", "validate_logic",
]
