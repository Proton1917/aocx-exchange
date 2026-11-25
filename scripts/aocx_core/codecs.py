"""Reversible codecs for AOCX representation envelopes.

The expression wire format is a bounded term language. Its named constructors
factor repeated structural keys; every other JSON field remains an ordinary
object member. Dictionary references denote strings and never executable code.

Decoding permits at most MAX_EXPANDED_STRING_BYTES cumulative UTF-8 bytes of
strings. This conservative total includes literal keys and values, dictionary
definitions and each resolved reference, constructor-generated keys and marker
values, and every string in an embedded logic AST. The original logic formula
also remains charged when its AST replaces it. Dictionary byte sizes are cached
once, so repeated references consume their full payload budget in constant time.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import math
import re
from typing import Callable

from .common import AOCXError, _json, fail
from .logic import parse_logic, render_logic

MAX_WIRE_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_STRING_BYTES = MAX_WIRE_BYTES
MAX_DEPTH = 128
MAX_NODES = 1_000_000
_HEADER = b"AOCX/1 "
_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
_INDEX = re.compile(r"0|[1-9][0-9]*")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")


@dataclass(frozen=True)
class Codec:
    id: str
    encode: Callable[[dict], bytes]
    decode: Callable[[bytes], dict]


class CodecRegistry:
    """Explicit host-owned codec registrations, with stable unique identifiers."""

    def __init__(self):
        self._codecs = {}

    def register(self, codec):
        if not isinstance(codec, Codec) or not re.fullmatch(r"[a-z0-9][a-z0-9._/-]*", codec.id):
            fail("invalid_codec", "A codec needs a portable identifier and encode/decode functions")
        if not callable(codec.encode) or not callable(codec.decode):
            fail("invalid_codec", "Codec encode and decode must be callable", codec=codec.id)
        if codec.id in self._codecs:
            fail("duplicate_codec", "Codec identifier is already registered", codec=codec.id)
        self._codecs[codec.id] = codec
        return codec

    def get(self, identifier):
        if identifier not in self._codecs:
            fail("unsupported_codec", "Codec implementation is unavailable", codec=identifier)
        return self._codecs[identifier]

    @property
    def ids(self):
        return tuple(self._codecs)


@dataclass(frozen=True)
class _Term:
    name: str
    args: tuple


_FIELDS = {
    "Rep": ("contract", "source", "context"),
    "Context": ("namespace", "records", "relations", "heads", "profiles", "required_profiles"),
    "Record": ("id", "rev", "kind", "text"),
    "Relation": ("id", "from", "kind", "to"),
    "Ref": ("id", "rev"),
}


def _scalar(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _validate_json(value, depth=0, budget=None):
    """Check plain JSON shape and resource bounds without interpreting markers."""
    if budget is None:
        budget = [MAX_NODES]
    budget[0] -= 1
    if budget[0] < 0 or depth > MAX_DEPTH:
        fail("codec_limit", "Representation exceeds node or nesting limits")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                fail("invalid_json_value", "Object member names must be strings")
            _validate_json(item, depth + 1, budget)
    elif isinstance(value, list):
        for item in value:
            _validate_json(item, depth + 1, budget)
    elif value is None or isinstance(value, (str, bool, int)):
        return
    elif not isinstance(value, float) or not math.isfinite(value):
        fail("invalid_json_value", "Codec accepts finite JSON values", value_type=type(value).__name__)


def _terms(value, depth=0, budget=None):
    if budget is None:
        budget = [MAX_NODES]
    budget[0] -= 1
    if budget[0] < 0 or depth > MAX_DEPTH:
        fail("codec_limit", "Representation exceeds node or nesting limits")
    if isinstance(value, dict):
        if any(not isinstance(k, str) for k in value):
            fail("invalid_json_value", "Object member names must be strings")
        if value.get("format") == "aocx-logic/1" and "expression" in value:
            try:
                formula = render_logic(value["expression"])
            except AOCXError as error:
                if error.diagnostic["code"] not in ("invalid_logic", "logic_limit"):
                    raise
                # Quoted or oversized samples remain ordinary JSON. Mandatory
                # record.logic validation belongs to the record model boundary.
            else:
                extra = {key: item for key, item in value.items() if key not in ("format", "expression")}
                return _Term("Logic", (formula, _terms(extra, depth + 1, budget)))
        name = None
        if value.get("format") == "AOCX-REP" and value.get("version") == "1.0" and all(k in value for k in _FIELDS["Rep"]):
            name = "Rep"
        elif all(k in value for k in _FIELDS["Context"]):
            name = "Context"
        elif all(k in value for k in _FIELDS["Record"]):
            name = "Record"
        elif all(k in value for k in _FIELDS["Relation"]):
            name = "Relation"
        elif set(value) == {"id", "rev"}:
            name = "Ref"
        if name is not None:
            fields = _FIELDS[name]
            excluded = set(fields) | ({"format", "version"} if name == "Rep" else set())
            extra = {k: v for k, v in value.items() if k not in excluded}
            args = tuple(_terms(value[k], depth + 1, budget) for k in fields)
            if name != "Ref":
                args += (_terms(extra, depth + 1, budget),)
            return _Term(name, args)
        return {k: _terms(v, depth + 1, budget) for k, v in value.items()}
    if isinstance(value, list):
        return [_terms(v, depth + 1, budget) for v in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    fail("invalid_json_value", "Codec accepts finite JSON values", value_type=type(value).__name__)


def _strings(term, counter):
    if isinstance(term, _Term):
        for value in term.args:
            _strings(value, counter)
    elif isinstance(term, dict):
        for key, value in term.items():
            counter[key] += 1
            _strings(value, counter)
    elif isinstance(term, list):
        for value in term:
            _strings(value, counter)
    elif isinstance(term, str):
        counter[term] += 1


def _emit(term, dictionary):
    if isinstance(term, _Term):
        return term.name + "(" + ",".join(_emit(v, dictionary) for v in term.args) + ")"
    if isinstance(term, dict):
        return "{" + ",".join(_emit(k, dictionary) + ":" + _emit(v, dictionary) for k, v in term.items()) + "}"
    if isinstance(term, list):
        return "[" + ",".join(_emit(v, dictionary) for v in term) + "]"
    if isinstance(term, str) and term in dictionary:
        return "@" + str(dictionary[term])
    return _scalar(term)


def _frame(identifier, body):
    try:
        raw = _HEADER + identifier.encode("ascii") + b"\n" + body.encode("utf-8") + b"\n"
    except UnicodeError:
        fail("invalid_utf8", "Representation strings must encode as UTF-8")
    if len(raw) > MAX_WIRE_BYTES:
        fail("codec_limit", "Representation exceeds wire byte limit", limit=MAX_WIRE_BYTES)
    return raw


def _unframe(raw, expected=None):
    if not isinstance(raw, bytes):
        fail("invalid_representation", "Representation input must be bytes")
    if len(raw) > MAX_WIRE_BYTES:
        fail("codec_limit", "Representation exceeds wire byte limit", limit=MAX_WIRE_BYTES)
    header, separator, body = raw.partition(b"\n")
    if not separator or not header.startswith(_HEADER):
        fail("invalid_representation", "Expected AOCX/1 codec header")
    try:
        identifier = header[len(_HEADER):].decode("ascii")
        text = body.decode("utf-8")
    except UnicodeError:
        fail("invalid_utf8", "Representation header must be ASCII and body UTF-8")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._/-]*", identifier):
        fail("invalid_codec", "Malformed wire codec identifier")
    if expected is not None and identifier != expected:
        fail("codec_mismatch", "Wire codec differs from selected decoder", expected=expected, actual=identifier)
    return identifier, text


class _Parser:
    def __init__(self, text):
        self.text = text
        self.at = 0
        self.remaining = MAX_NODES
        self.remaining_string_bytes = MAX_EXPANDED_STRING_BYTES
        self.dictionary = None
        self.dictionary_sizes = None

    def string_bytes(self, size):
        self.remaining_string_bytes -= size
        if self.remaining_string_bytes < 0:
            fail("codec_limit", "Representation exceeds expanded string byte limit",
                 limit=MAX_EXPANDED_STRING_BYTES)

    def embedded_strings(self, value):
        """Charge generated AST strings before exposing them to other codecs."""
        pending = [value]
        while pending:
            item = pending.pop()
            if isinstance(item, str):
                self.string_bytes(len(item.encode("utf-8")))
            elif isinstance(item, dict):
                for key, child in item.items():
                    self.string_bytes(len(key.encode("utf-8")))
                    pending.append(child)
            elif isinstance(item, list):
                pending.extend(item)

    def error(self, message):
        fail("invalid_expression", message, offset=self.at)

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

    def string(self):
        self.space()
        start = self.at
        if not self.take('"'):
            self.error("Expected JSON string")
        while self.at < len(self.text):
            char = self.text[self.at]
            self.at += 1
            if char == "\\":
                self.at += 1
            elif char == '"':
                try:
                    value = _json(self.text[start:self.at])
                except (ValueError, UnicodeError):
                    self.error("Malformed JSON string")
                self.string_bytes(len(value.encode("utf-8")))
                return value
        self.error("Unterminated JSON string")

    def sequence(self, end, depth):
        values = []
        if self.take(end):
            return values
        while True:
            values.append(self.value(depth + 1))
            if self.take(end):
                return values
            self.need(",")

    def value(self, depth=0):
        self.remaining -= 1
        if self.remaining < 0 or depth > MAX_DEPTH:
            fail("codec_limit", "Representation exceeds node or nesting limits")
        self.space()
        if self.at >= len(self.text):
            self.error("Expected expression")
        char = self.text[self.at]
        if char == '"':
            return self.string()
        if self.take("["):
            return self.sequence("]", depth)
        if self.take("{"):
            result = {}
            if self.take("}"):
                return result
            while True:
                key = self.value(depth + 1)
                if not isinstance(key, str):
                    self.error("Object member must be a string")
                if key in result:
                    self.error("Duplicate object member")
                self.need(":")
                result[key] = self.value(depth + 1)
                if self.take("}"):
                    return result
                self.need(",")
        if self.take("@"):
            match = _INDEX.match(self.text, self.at)
            if match is None or self.dictionary is None:
                self.error("Dictionary reference needs an initialized dictionary and integer index")
            self.at = match.end()
            if match.end() - match.start() > 8:
                self.error("Dictionary index is out of range")
            index = int(match.group())
            if index >= len(self.dictionary):
                self.error("Dictionary index is out of range")
            self.string_bytes(self.dictionary_sizes[index])
            return self.dictionary[index]
        number = _NUMBER.match(self.text, self.at)
        if number:
            self.at = number.end()
            try:
                return _json(number.group())
            except ValueError:
                self.error("Malformed or nonfinite JSON number")
        word = _WORD.match(self.text, self.at)
        if word is None:
            self.error("Unknown expression token")
        self.at = word.end()
        name = word.group()
        if name in ("true", "false", "null"):
            return {"true": True, "false": False, "null": None}[name]
        if name not in _FIELDS and name != "Logic":
            self.error("Unknown expression constructor")
        self.need("(")
        args = self.sequence(")", depth)
        if name == "Logic":
            if len(args) != 2 or not isinstance(args[0], str) or not isinstance(args[1], dict):
                self.error("Logic requires an expression string and extra members")
            if set(args[1]).intersection(("format", "expression")):
                self.error("Logic extra members overlap reserved fields")
            self.string_bytes(len("formatexpressionaocx-logic/1"))
            expression = parse_logic(args[0])
            self.embedded_strings(expression)
            return {"format": "aocx-logic/1", "expression": expression, **args[1]}
        fields = _FIELDS[name]
        if len(args) != len(fields) + (name != "Ref"):
            self.error("Constructor argument count differs from its contract")
        self.string_bytes(sum(len(field) for field in fields))
        result = dict(zip(fields, args))
        if name == "Rep":
            self.string_bytes(len("formatversionAOCX-REP1.0"))
            result = {"format": "AOCX-REP", "version": "1.0", **result}
        if name != "Ref":
            extra = args[-1]
            if not isinstance(extra, dict) or set(extra).intersection(result):
                self.error("Constructor extra members must be a disjoint object")
            result.update(extra)
        return result

    def finish(self):
        self.space()
        if self.at != len(self.text):
            self.error("Trailing content after expression")


def _encode_expr(envelope, dictionary=False):
    if not isinstance(envelope, dict):
        fail("invalid_representation", "Representation envelope must be an object")
    term = _terms(envelope)
    table = []
    if dictionary:
        counts = Counter()
        _strings(term, counts)
        # Count the dictionary definition and every reference, including commas.
        for value, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])):
            index = len(table)
            size = len(_scalar(value).encode("utf-8"))
            if count > 1 and (count - 1) * size > count * (len(str(index)) + 1) + 1:
                table.append(value)
    body = _emit(term, {value: index for index, value in enumerate(table)})
    identifier = "aocx-expr-dict/1" if dictionary else "aocx-expr/1"
    if dictionary:
        body = "Dict(" + _scalar(table) + "," + body + ")"
    return _frame(identifier, body)


def _decode_expr(raw, dictionary=False):
    identifier = "aocx-expr-dict/1" if dictionary else "aocx-expr/1"
    _, body = _unframe(raw, identifier)
    parser = _Parser(body)
    if dictionary:
        parser.need("Dict(")
        table = parser.value()
        if not isinstance(table, list) or any(not isinstance(value, str) for value in table):
            parser.error("Dictionary must be an array of strings")
        if len(set(table)) != len(table):
            parser.error("Dictionary contains duplicate strings")
        parser.dictionary = table
        parser.dictionary_sizes = [len(value.encode("utf-8")) for value in table]
        parser.need(",")
    value = parser.value()
    if dictionary:
        parser.need(")")
    parser.finish()
    if not isinstance(value, dict):
        parser.error("Representation envelope must be an object")
    return value


def _encode_json(envelope):
    if not isinstance(envelope, dict):
        fail("invalid_representation", "Representation envelope must be an object")
    _validate_json(envelope)
    return _frame("json/1", _scalar(envelope))


def _decode_json(raw):
    _, body = _unframe(raw, "json/1")
    # The expression parser's generic subset has the same bounded JSON values.
    # _json additionally enforces the strict JSON grammar and duplicate keys.
    parser = _Parser(body)
    value = parser.value()
    parser.finish()
    strict = _json(body)
    if not isinstance(strict, dict):
        fail("invalid_representation", "Representation envelope must be an object")
    return strict


def default_registry():
    registry = CodecRegistry()
    registry.register(Codec("aocx-expr/1", _encode_expr, _decode_expr))
    registry.register(Codec("aocx-expr-dict/1", lambda value: _encode_expr(value, True), lambda raw: _decode_expr(raw, True)))
    registry.register(Codec("json/1", _encode_json, _decode_json))
    return registry


def decode_representation(raw, registry=None):
    identifier, _ = _unframe(raw)
    codec = (registry or default_registry()).get(identifier)
    return codec.decode(raw)
