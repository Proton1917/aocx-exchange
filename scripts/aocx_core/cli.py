"""Command-line dispatch for AOCX exchange and representation operations."""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

from .common import _jsonl, _json, _dump, _digest, _error_report, fail
from .storage import create_bundle, validate_bundle
from .legacy import import_bundle, restore
from .views import capsule, check_view
from .negotiation import negotiate, merge_check
from .contracts import make_contract
from .optimizer import compile_context, recover_context, verify_representation
from .logic import parse_logic, render_logic, validate_logic


def _write_outputs(outputs):
    """Publish new files only, rolling back this operation on a write failure."""
    paths = [Path(path).resolve() for path, _ in outputs]
    if len(set(paths)) != len(paths):
        fail("output_collision", "Output paths must be distinct")
    for path in paths:
        if path.exists():
            fail("output_exists", "Output already exists", path=str(path))
    created = []
    try:
        for path, (_, raw) in zip(paths, outputs):
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                created.append(path)
                stream.write(raw)
    except Exception:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise


def _tokenizer(args):
    if args.metric != "tokens":
        if args.tokenizer:
            fail("invalid_metric", "A tokenizer option requires the tokens metric")
        return None, None
    if not args.tokenizer:
        fail("missing_tokenizer", "Token measurement requires --tokenizer with a tiktoken encoding name")
    try:
        import tiktoken
    except ImportError:
        fail("missing_tokenizer", "Install the optional tiktoken package to measure tokens")
    encoding = tiktoken.get_encoding(args.tokenizer)
    return lambda text: encoding.encode(text, disallowed_special=()), "tiktoken:" + encoding.name


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    c = commands.add_parser("compile", aliases=["optimize"], help="Compile the smallest verified representation")
    c.add_argument("bundle")
    c.add_argument("--out", required=True)
    c.add_argument("--mode", choices=["exact", "projection"], default="exact")
    c.add_argument("--select", action="append")
    c.add_argument("--codec", action="append")
    c.add_argument("--metric", choices=["bytes", "characters", "tokens"], default="bytes")
    c.add_argument("--tokenizer", help="Optional tiktoken encoding, required for the tokens metric")
    c.add_argument("--reader", help="Reader capability JSON")
    c.add_argument("--full-fields", action="store_true", help="Retain body and extensions in a projection")
    c.add_argument("--report", help="Write the compile report to a new JSON file")
    c = commands.add_parser("decode", help="Recover context values from a self-contained representation")
    c.add_argument("representation")
    c.add_argument("--out", required=True)
    c = commands.add_parser("verify", help="Compare a representation with its source and expected contract")
    c.add_argument("bundle")
    c.add_argument("representation")
    c.add_argument("--contract", help="Expected contract JSON; pins exact/projection policy")
    c = commands.add_parser("logic", help="Parse or render open symbolic expressions")
    group = c.add_mutually_exclusive_group(required=True)
    group.add_argument("--expression")
    group.add_argument("--input", help="AST JSON or aocx-logic/1 declaration")
    c.add_argument("--out", help="Write the logic declaration to a new JSON file")
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
        if args.command in ("compile", "optimize"):
            contract = make_contract(args.mode, select=args.select,
                                     omit_fields=[] if args.full_fields else None)
            tokenizer, tokenizer_id = _tokenizer(args)
            result = compile_context(args.bundle, contract, codecs=args.codec,
                                     reader=_json(Path(args.reader).read_bytes()) if args.reader else None,
                                     metric=args.metric, tokenizer=tokenizer, tokenizer_id=tokenizer_id)
            report = dict(result["report"], path=str(Path(args.out).resolve()))
            outputs = [(args.out, result["representation"])]
            if args.report:
                outputs.append((args.report, _dump(report, pretty=True)))
            _write_outputs(outputs)
        elif args.command == "decode":
            context = recover_context(Path(args.representation).read_bytes())
            raw = _dump(context, pretty=True)
            _write_outputs([(args.out, raw)])
            report = {"status": "passed", "path": str(Path(args.out).resolve()),
                      "scope": "context-values", "source_verified": False,
                      "counts": {"records": len(context["records"]), "relations": len(context["relations"])}}
        elif args.command == "verify":
            report = verify_representation(args.bundle, Path(args.representation).read_bytes(),
                                           _json(Path(args.contract).read_bytes()) if args.contract else None)
        elif args.command == "logic":
            value = parse_logic(args.expression) if args.expression is not None else _json(Path(args.input).read_bytes())
            expression = value["expression"] if isinstance(value, dict) and value.get("format") == "aocx-logic/1" else value
            report = validate_logic(expression)
            if report["status"] == "passed":
                declaration = {"format": "aocx-logic/1", "expression": expression}
                if isinstance(value, dict) and value.get("format") == "aocx-logic/1":
                    declaration = value
                report.update(declaration=declaration, rendered=render_logic(expression))
                if args.out:
                    _write_outputs([(args.out, _dump(declaration, pretty=True))])
                    report["path"] = str(Path(args.out).resolve())
        elif args.command == "create":
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
    except (ValueError, TypeError, KeyError, OSError, UnicodeError, RecursionError, zipfile.BadZipFile, RuntimeError) as error:
        report = _error_report(error)
    sys.stdout.buffer.write(_dump(report, pretty=True))
    return 0 if report["status"] in ("passed", "clean") else 2
