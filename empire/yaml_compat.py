"""
Minimal YAML support.

PyYAML is used when it is installed. When it is not, this module implements
the YAML subset the project actually uses:

  * block mappings            key: value
  * block sequences            - item / - key: value
  * nested structures by indentation
  * block scalars              | (literal) and > (folded)
  * flow collections           [] {} ["a", "b"] {k: v}
  * quoted strings             "..." and '...'
  * scalars                   str, int, float, bool (true/false), null

It is a real parser, not a stub: anything it cannot parse raises, rather
than silently returning an empty document.

Usage:
    from empire import yaml_compat as yaml
    data = yaml.safe_load(text)
    text = yaml.safe_dump(data)
"""
from __future__ import annotations

import re
from typing import Any

try:                                     # pragma: no cover
    import yaml as _pyyaml
    HAS_PYYAML = True
except ImportError:                      # pragma: no cover
    _pyyaml = None
    HAS_PYYAML = False


class YAMLError(Exception):
    """Raised when the document cannot be parsed."""


# ── scalars ───────────────────────────────────────────────────────────────

_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")


def _parse_scalar(tok: str) -> Any:
    """Convert a YAML scalar token to a Python value."""
    tok = tok.strip()
    if not tok:
        return None
    if tok[0] == '"' and tok.endswith('"') and len(tok) >= 2:
        return _unescape_double(tok[1:-1])
    if tok[0] == "'" and tok.endswith("'") and len(tok) >= 2:
        return tok[1:-1].replace("''", "'")
    low = tok.lower()
    if low in ("null", "~"):
        return None
    if low == "true":
        return True
    if low == "false":
        return False
    if _INT_RE.match(tok):
        return int(tok)
    if _FLOAT_RE.match(tok) and any(c in tok for c in ".eE"):
        return float(tok)
    return tok


def _unescape_double(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            nxt = s[i + 1]
            out.append({"n": "\n", "t": "\t", "r": "\r", '"': '"',
                        "\\": "\\", "0": "\0"}.get(nxt, nxt))
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _strip_comment(line: str) -> str:
    """Remove a trailing comment that is not inside quotes."""
    out, quote = [], None
    for i, c in enumerate(line):
        if quote:
            out.append(c)
            if c == quote and (i == 0 or line[i - 1] != "\\"):
                quote = None
            continue
        if c in "\"'":
            quote = c
            out.append(c)
            continue
        if c == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        out.append(c)
    return "".join(out).rstrip()


# ── flow collections ──────────────────────────────────────────────────────

def _parse_flow(text: str) -> Any:
    """Parse a flow collection: [], {}, [a, b], {k: v}."""
    value, idx = _parse_flow_at(text, 0)
    rest = text[idx:].strip()
    if rest:
        raise YAMLError(f"trailing content in flow collection: {rest!r}")
    return value


def _parse_flow_at(text: str, i: int):
    while i < len(text) and text[i] in " \t\n":
        i += 1
    if i >= len(text):
        raise YAMLError("unexpected end of flow collection")
    if text[i] == "[":
        return _parse_flow_seq(text, i + 1)
    if text[i] == "{":
        return _parse_flow_map(text, i + 1)
    # scalar
    start = i
    depth = 0
    quote = None
    while i < len(text):
        c = text[i]
        if quote:
            if c == quote and text[i - 1] != "\\":
                quote = None
            i += 1
            continue
        if c in "\"'":
            quote = c
            i += 1
            continue
        if c in "[{":
            depth += 1
        elif c in "]}":
            if depth == 0:
                break
            depth -= 1
        elif c == "," and depth == 0:
            break
        i += 1
    return _parse_scalar(text[start:i]), i


def _parse_flow_seq(text: str, i: int):
    items = []
    while True:
        while i < len(text) and text[i] in " \t\n,":
            i += 1
        if i >= len(text):
            raise YAMLError("unterminated flow sequence")
        if text[i] == "]":
            return items, i + 1
        val, i = _parse_flow_at(text, i)
        items.append(val)
        while i < len(text) and text[i] in " \t\n":
            i += 1
        if i < len(text) and text[i] == ",":
            i += 1
        elif i < len(text) and text[i] == "]":
            return items, i + 1


def _parse_flow_map(text: str, i: int):
    out = {}
    while True:
        while i < len(text) and text[i] in " \t\n,":
            i += 1
        if i >= len(text):
            raise YAMLError("unterminated flow mapping")
        if text[i] == "}":
            return out, i + 1
        key, i = _parse_flow_at(text, i)
        while i < len(text) and text[i] in " \t\n":
            i += 1
        if i < len(text) and text[i] == ":":
            i += 1
            val, i = _parse_flow_at(text, i)
        else:
            val = None
        out[str(key)] = val
        while i < len(text) and text[i] in " \t\n":
            i += 1
        if i < len(text) and text[i] == ",":
            i += 1
        elif i < len(text) and text[i] == "}":
            return out, i + 1


# ── block parser ──────────────────────────────────────────────────────────

class _Line:
    __slots__ = ("indent", "text", "no", "raw")

    def __init__(self, indent: int, text: str, no: int, raw: str):
        self.indent, self.text, self.no, self.raw = indent, text, no, raw


def _tokenize(text: str) -> list[_Line]:
    out = []
    for no, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        stripped = raw.lstrip(" ")
        indent = len(raw) - len(stripped)
        if stripped.startswith("#"):
            continue
        out.append(_Line(indent, stripped, no, raw))
    return out


def _block_scalar(lines: list[_Line], idx: int, parent_indent: int,
                  style: str) -> tuple[str, int]:
    """Read a literal (|) or folded (>) block scalar."""
    body, i = [], idx
    base = None
    while i < len(lines):
        ln = lines[i]
        if ln.indent <= parent_indent:
            break
        if base is None:
            base = ln.indent
        body.append(" " * max(0, ln.indent - base) + ln.text
                    if ln.raw.strip() else "")
        i += 1
    if style == "|":
        text = "\n".join(body)
    else:
        parts, buf = [], []
        for b in body:
            if not b.strip():
                if buf:
                    parts.append(" ".join(buf))
                    buf = []
            else:
                buf.append(b.strip())
        if buf:
            parts.append(" ".join(buf))
        text = "\n".join(parts)
    return text, i


def _flow_balanced(text: str) -> bool:
    """True when every flow bracket opened in the text is closed."""
    depth = 0
    quote = None
    for i, c in enumerate(text):
        if quote:
            if c == quote and text[i - 1] != "\\":
                quote = None
            continue
        if c in "\"'":
            quote = c
            continue
        if c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
    return depth <= 0


def _collect_flow(lines: list[_Line], idx: int) -> tuple[str, int]:
    """Join the lines of a flow collection that may span several lines."""
    parts = [lines[idx].text]
    i = idx + 1
    while not _flow_balanced(" ".join(parts)) and i < len(lines):
        parts.append(lines[i].text)
        i += 1
    return " ".join(parts), i


def _parse_block(lines: list[_Line], idx: int, indent: int):
    """Parse a block node at the given indentation."""
    if idx >= len(lines):
        return None, idx
    if lines[idx].text.startswith("- "):
        return _parse_seq(lines, idx, indent)
    if lines[idx].text == "-":
        return _parse_seq(lines, idx, indent)
    return _parse_map(lines, idx, indent)


def _parse_seq(lines: list[_Line], idx: int, indent: int):
    items = []
    while idx < len(lines):
        ln = lines[idx]
        if ln.indent < indent:
            break
        if ln.indent > indent:
            raise YAMLError(f"line {ln.no}: unexpected indent in sequence")
        if not (ln.text == "-" or ln.text.startswith("- ")):
            break
        rest = ln.text[1:].strip()
        idx += 1
        if not rest:
            # value lives on the following lines
            if idx < len(lines) and lines[idx].indent > indent:
                if lines[idx].text.startswith(("[", "{")):
                    flow, idx = _collect_flow(lines, idx)
                    val = _parse_flow(flow)
                else:
                    val, idx = _parse_block(lines, idx, lines[idx].indent)
            else:
                val = None
            items.append(val)
            continue
        # "- key: value" starts a mapping whose indent is the position of key
        if _looks_like_mapping(rest):
            sub_indent = ln.indent + 2
            synthetic = [_Line(sub_indent, rest, ln.no, ln.raw)]
            j = idx
            while j < len(lines) and lines[j].indent > ln.indent:
                synthetic.append(lines[j])
                j += 1
            val, _ = _parse_map(synthetic, 0, sub_indent)
            items.append(val)
            idx = j
            continue
        items.append(_parse_value(rest))
    return items, idx


def _looks_like_mapping(text: str) -> bool:
    """True when the text is `key: value` or `key:`."""
    if text.startswith(("[", "{", '"', "'")):
        return False
    if ":" not in text:
        return False
    # a colon followed by space (or end) marks a mapping
    m = re.match(r"^[^:]+:(?:\s|$)", text)
    return bool(m)


def _parse_map(lines: list[_Line], idx: int, indent: int):
    out = {}
    while idx < len(lines):
        ln = lines[idx]
        if ln.indent < indent:
            break
        if ln.indent > indent:
            raise YAMLError(f"line {ln.no}: unexpected indent in mapping")
        if ln.text.startswith("- "):
            break
        text = _strip_comment(ln.text)
        if not text:
            idx += 1
            continue
        if ":" not in text:
            raise YAMLError(f"line {ln.no}: expected 'key: value', got {text!r}")
        key, _, rest = text.partition(":")
        key = _parse_scalar(key.strip())
        rest = rest.strip()
        idx += 1
        if rest in ("|", ">", "|-", ">-", "|+", ">+"):
            value, idx = _block_scalar(lines, idx, ln.indent, rest[0])
            out[str(key)] = value
            continue
        if rest:
            out[str(key)] = _parse_value(rest)
            continue
        # value on following lines
        if idx < len(lines) and lines[idx].indent > ln.indent:
            # a flow collection may start on its own (possibly indented) line
            if lines[idx].text.startswith(("[", "{")):
                flow, idx = _collect_flow(lines, idx)
                out[str(key)] = _parse_flow(flow)
                continue
            value, idx = _parse_block(lines, idx, lines[idx].indent)
            out[str(key)] = value
        elif (idx < len(lines) and lines[idx].indent == ln.indent
              and (lines[idx].text == "-" or lines[idx].text.startswith("- "))):
            value, idx = _parse_seq(lines, idx, ln.indent)
            out[str(key)] = value
        else:
            out[str(key)] = None
    return out, idx


def _parse_value(text: str) -> Any:
    text = text.strip()
    if text.startswith("[") or text.startswith("{"):
        return _parse_flow(text)
    return _parse_scalar(text)


# ── public API ────────────────────────────────────────────────────────────

def safe_load(stream) -> Any:
    """Parse a YAML document into Python data."""
    if hasattr(stream, "read"):
        text = stream.read()
    else:
        text = stream
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    if HAS_PYYAML:
        return _pyyaml.safe_load(text)
    if not text.strip():
        return None
    lines = _tokenize(text)
    if not lines:
        return None
    value, _ = _parse_block(lines, 0, lines[0].indent)
    return value


def load(stream, Loader=None):        # noqa: N803 - PyYAML-compatible name
    return safe_load(stream)


def load_all(stream):                 # noqa: N803
    text = stream.read() if hasattr(stream, "read") else stream
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    if HAS_PYYAML:
        return list(_pyyaml.safe_load_all(text))
    return [d for d in (safe_load(text),) if d is not None]


def _dump_scalar(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    s = str(v)
    if s == "":
        return "''"
    if s[0] in "&*!|>%@`{}[]#,\"'" or ": " in s or s.endswith(":"):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if "\n" in s:
        return None            # caller uses a block scalar
    return s


def _dump_node(obj: Any, indent: int, out: list[str]) -> None:
    pad = " " * indent
    if isinstance(obj, dict):
        if not obj:
            out[-1] += " {}"
            return
        for k, v in obj.items():
            key = str(k)
            if isinstance(v, (dict, list)) and v:
                out.append(f"{pad}{key}:")
                _dump_node(v, indent + 2, out)
            elif isinstance(v, (dict, list)):
                out.append(f"{pad}{key}: {'{}' if isinstance(v, dict) else '[]'}")
            else:
                s = _dump_scalar(v)
                if s is None:                 # multi-line string
                    out.append(f"{pad}{key}: |-")
                    for line in str(v).split("\n"):
                        out.append(f"{pad}  {line}")
                else:
                    out.append(f"{pad}{key}: {s}")
    elif isinstance(obj, list):
        if not obj:
            out[-1] += " []"
            return
        for item in obj:
            if isinstance(item, dict) and item:
                sub: list[str] = []
                _dump_node(item, indent + 2, sub)
                first = sub[0].lstrip()
                out.append(f"{pad}- {first}")
                out.extend(sub[1:])
            elif isinstance(item, (dict, list)):
                out.append(f"{pad}- {'{}' if isinstance(item, dict) else '[]'}")
            else:
                s = _dump_scalar(item)
                if s is None:
                    out.append(f"{pad}- |-")
                    for line in str(item).split("\n"):
                        out.append(f"{pad}  {line}")
                else:
                    out.append(f"{pad}- {s}")
    else:
        s = _dump_scalar(obj)
        out.append(f"{pad}{s if s is not None else str(obj)}")


def safe_dump(data: Any, stream=None, allow_unicode: bool = True,
              **kwargs) -> str | None:
    """Serialise Python data to YAML."""
    if HAS_PYYAML:
        return _pyyaml.safe_dump(data, stream, allow_unicode=allow_unicode,
                                  **kwargs)
    out: list[str] = []
    if isinstance(data, (dict, list)) and data:
        _dump_node(data, 0, out)
    elif data is None:
        out.append("null")
    else:
        s = _dump_scalar(data)
        out.append(s if s is not None else str(data))
    text = "\n".join(out) + "\n"
    if stream is not None:
        stream.write(text)
        return None
    return text


def dump(data: Any, stream=None, **kwargs):
    return safe_dump(data, stream, **kwargs)


__all__ = ["safe_load", "safe_dump", "load", "load_all", "dump",
           "YAMLError", "HAS_PYYAML"]
