"""An optional, open logic AST with deterministic rendering and parsing.

Only explicitly authored ASTs acquire logical structure. Predicate names and
free variables remain domain-owned. Unknown nodes and extension fields use an
AST(JSON) escape, retaining their data for a reader that understands them.
"""
from __future__ import annotations

import json
import math
import re

from .common import AOCXError, _dump, _json, _error_report, fail

FORMAT = "aocx-logic/1"
MAX_DEPTH = 128
MAX_NODES = 100_000
MAX_TEXT = 16 * 1024 * 1024
_NAME = re.compile(r"[^\W\d]\w*", re.UNICODE)
_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
_FIELDS = {
    "var": {"name"}, "const": {"value"}, "literal": {"text"},
    "call": {"name", "args"}, "set": {"binder", "body"},
    "bind": {"name", "bindings"}, "not": {"body"},
    "forall": {"binder", "body"}, "exists": {"binder", "body"},
    **{name: {"left", "right"} for name in ("sequent", "and", "or", "implies", "iff", "in", "eq")},
}
_SYMBOLS = {"sequent": "⊢", "and": "∧", "or": "∨", "implies": "→", "iff": "↔", "in": "∈", "eq": "="}
_PRECEDENCE = {"⊢": 10, "↔": 20, "→": 30, "∨": 40, "∧": 50, "∈": 60, "=": 60}
_OPS = {value: key for key, value in _SYMBOLS.items()}
_RESERVED = {"AST", "Literal", "true", "false", "null"}


def _json_safe(value, depth=0, budget=None):
    if budget is None:
        budget = [MAX_NODES]
    budget[0] -= 1
    if depth > MAX_DEPTH or budget[0] < 0:
        fail("logic_limit", "Logic AST exceeds nesting or node limit")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                fail("invalid_logic", "Logic object member names must be strings")
            _json_safe(item, depth + 1, budget)
    elif isinstance(value, list):
        for item in value:
            _json_safe(item, depth + 1, budget)
    elif value is None or isinstance(value, (str, bool, int)):
        return
    elif not isinstance(value, float) or not math.isfinite(value):
        fail("invalid_logic", "Logic AST must contain finite JSON values")


def _check(node, opaque, depth=0):
    if depth > MAX_DEPTH:
        fail("logic_limit", "Logic AST exceeds nesting limit")
    if not isinstance(node, dict) or not isinstance(node.get("op"), str) or not node["op"]:
        fail("invalid_logic", "Logic node requires an op string")
    op = node["op"]
    if op not in _FIELDS:
        opaque.append(op)
        return
    if not _FIELDS[op].issubset(node):
        fail("invalid_logic", "Logic node lacks required fields", op=op, fields=sorted(_FIELDS[op] - set(node)))
    for key in ("name", "binder", "text"):
        if key in _FIELDS[op] and (not isinstance(node[key], str) or (key != "text" and not node[key])):
            fail("invalid_logic", "Logic name, binder and literal text must be strings", op=op, field=key)
    if op == "const":
        if isinstance(node["value"], (dict, list)):
            fail("invalid_logic", "Constant value must be a JSON scalar")
    elif op == "call":
        if not isinstance(node["args"], list):
            fail("invalid_logic", "Call arguments must be an array")
        for arg in node["args"]:
            _check(arg, opaque, depth + 1)
    elif op == "bind":
        if not isinstance(node["bindings"], list):
            fail("invalid_logic", "Bindings must be an array")
        seen = set()
        for binding in node["bindings"]:
            if not isinstance(binding, dict) or not isinstance(binding.get("name"), str) or not binding["name"] or "value" not in binding:
                fail("invalid_logic", "Each binding requires name and value")
            if binding["name"] in seen:
                fail("invalid_logic", "Binding names must be unique", name=binding["name"])
            seen.add(binding["name"])
            _check(binding["value"], opaque, depth + 1)
    elif op in _SYMBOLS:
        _check(node["left"], opaque, depth + 1)
        _check(node["right"], opaque, depth + 1)
    elif "body" in _FIELDS[op]:
        _check(node["body"], opaque, depth + 1)


def validate_logic(ast):
    try:
        _json_safe(ast)
        opaque = []
        _check(ast, opaque)
        _dump(ast)  # UTF-8 contract, including escaped lone surrogates.
        return {"status": "passed", "errors": [], "opaque_nodes": sorted(set(opaque))}
    except (ValueError, UnicodeError, RecursionError) as error:
        report = _error_report(error)
        report["opaque_nodes"] = []
        return report


def _require(ast):
    report = validate_logic(ast)
    if report["status"] != "passed":
        fail("invalid_logic", "Logic AST validation failed", errors=report["errors"])


def _name(value):
    return _NAME.fullmatch(value) is not None and value not in _RESERVED


def _escape(node):
    return "AST(" + json.dumps(node, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + ")"


def _render(node):
    op = node["op"]
    if op not in _FIELDS or set(node) != {"op"} | _FIELDS[op]:
        return _escape(node)
    if any(key in node and not _name(node[key]) for key in ("name", "binder")):
        return _escape(node)
    if op == "var":
        return node["name"]
    if op == "const":
        return json.dumps(node["value"], ensure_ascii=False, allow_nan=False)
    if op == "literal":
        return "Literal(" + json.dumps(node["text"], ensure_ascii=False) + ")"
    if op == "call":
        return node["name"] + "(" + ",".join(_render(value) for value in node["args"]) + ")"
    if op == "set":
        return "{" + node["binder"] + "|" + _render(node["body"]) + "}"
    if op == "bind":
        if any(set(binding) != {"name", "value"} or not _name(binding["name"]) for binding in node["bindings"]):
            return _escape(node)
        return node["name"] + "[" + ",".join(binding["name"] + "=" + _render(binding["value"]) for binding in node["bindings"]) + "]"
    if op in _SYMBOLS:
        return "(" + _render(node["left"]) + _SYMBOLS[op] + _render(node["right"]) + ")"
    if op == "not":
        return "¬(" + _render(node["body"]) + ")"
    if op in ("forall", "exists"):
        # Quantifiers bind to the following expression. Enclose the whole
        # quantifier so a surrounding binary operator keeps its own scope.
        return "(" + ("∀" if op == "forall" else "∃") + node["binder"] + ".(" + _render(node["body"]) + "))"
    return _escape(node)


def render_logic(ast):
    _require(ast)
    text = _render(ast)
    if len(text.encode("utf-8")) > MAX_TEXT:
        fail("logic_limit", "Logic expression exceeds text byte limit")
    return text


class _LogicParser:
    def __init__(self, text):
        self.text = text
        self.at = 0
        self.remaining = MAX_NODES

    def error(self, message):
        fail("invalid_logic_expression", message, offset=self.at)

    def space(self):
        while self.at < len(self.text) and self.text[self.at].isspace():
            self.at += 1

    def take(self, token):
        self.space()
        if self.text.startswith(token, self.at):
            self.at += len(token)
            return True
        return False

    def need(self, token):
        if not self.take(token):
            self.error("Expected " + token)

    def name(self):
        self.space()
        match = _NAME.match(self.text, self.at)
        if match is None:
            self.error("Expected identifier")
        self.at = match.end()
        return match.group()

    def json_value(self):
        self.space()
        try:
            _, length = json.JSONDecoder().raw_decode(self.text[self.at:])
            value = _json(self.text[self.at:self.at + length])
        except (ValueError, UnicodeError, RecursionError):
            self.error("Malformed strict JSON value")
        self.at += length
        return value

    def atom(self, depth):
        if depth > MAX_DEPTH or self.remaining <= 0:
            fail("logic_limit", "Logic expression exceeds nesting or node limit")
        self.remaining -= 1
        if self.take("("):
            node = self.expr(0, depth + 1)
            self.need(")")
            return node
        if self.take("{"):
            binder = self.name()
            self.need("|")
            body = self.expr(0, depth + 1)
            self.need("}")
            return {"op": "set", "binder": binder, "body": body}
        if self.take("¬"):
            return {"op": "not", "body": self.atom(depth + 1)}
        for symbol, op in (("∀", "forall"), ("∃", "exists")):
            if self.take(symbol):
                binder = self.name()
                self.need(".")
                return {"op": op, "binder": binder, "body": self.expr(0, depth + 1)}
        self.space()
        if self.at >= len(self.text):
            self.error("Expected logical expression")
        if self.text[self.at] == '"' or _NUMBER.match(self.text, self.at):
            return {"op": "const", "value": self.json_value()}
        name = self.name()
        if name in ("true", "false", "null"):
            return {"op": "const", "value": {"true": True, "false": False, "null": None}[name]}
        if self.take("("):
            if name in ("AST", "Literal"):
                value = self.json_value()
                self.need(")")
                if name == "Literal":
                    if not isinstance(value, str):
                        self.error("Literal requires a string")
                    return {"op": "literal", "text": value}
                _require(value)
                return value
            args = []
            if not self.take(")"):
                while True:
                    args.append(self.expr(0, depth + 1))
                    if self.take(")"):
                        break
                    self.need(",")
            return {"op": "call", "name": name, "args": args}
        if self.take("["):
            bindings = []
            if not self.take("]"):
                while True:
                    variable = self.name()
                    self.need("=")
                    bindings.append({"name": variable, "value": self.expr(0, depth + 1)})
                    if self.take("]"):
                        break
                    self.need(",")
            return {"op": "bind", "name": name, "bindings": bindings}
        return {"op": "var", "name": name}

    def expr(self, minimum=0, depth=0):
        node = self.atom(depth)
        while True:
            self.space()
            operator = self.text[self.at:self.at + 1]
            precedence = _PRECEDENCE.get(operator, -1)
            if precedence < minimum:
                return node
            self.at += 1
            right = self.expr(precedence if operator == "→" else precedence + 1, depth + 1)
            node = {"op": _OPS[operator], "left": node, "right": right}


def parse_logic(text):
    if not isinstance(text, str):
        fail("invalid_logic_expression", "Logic expression must be a string")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeError:
        fail("invalid_logic_expression", "Logic expression must encode as UTF-8")
    if size > MAX_TEXT:
        fail("logic_limit", "Logic expression exceeds text byte limit")
    parser = _LogicParser(text)
    ast = parser.expr()
    parser.space()
    if parser.at != len(text):
        parser.error("Trailing content after logic expression")
    _require(ast)
    return ast
