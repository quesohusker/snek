import difflib
import re

from snek.fx import DOTTED

IDENT_LIKE = re.compile(r"^[A-Za-z_][\w .\-]*$")
CALL = re.compile(r"[A-Z][A-Z0-9_]*(?:\.[A-Z][A-Z0-9_]*)*(?=\s*\()")
LOGICAL = re.compile(r"(TRUE|FALSE)\b(?!\s*\()")


class ExprError(ValueError):
    pass


def translate(expr, frame, columns):
    known = set(columns)
    out = []
    i = 0
    n = len(expr)
    while i < n:
        ch = expr[i]
        if ch in "'\"":
            j = skip_string(expr, i)
            out.append(expr[i:j])
            i = j
            continue
        if ch.isupper() and not previous_word_char(expr, i):
            m = CALL.match(expr, i)
            if m:
                out.append(DOTTED.get(m.group(0), m.group(0)))
                i = m.end()
                continue
            m = LOGICAL.match(expr, i)
            if m:
                out.append("True" if m.group(1) == "TRUE" else "False")
                i = m.end()
                continue
        if ch == "<" and expr[i + 1:i + 2] == ">":
            out.append("!=")
            i += 2
            continue
        if ch == "[":
            close = expr.find("]", i + 1)
            inner = expr[i + 1:close] if close != -1 else ""
            prev = previous_char(expr, i)
            indexing = bool(prev) and (prev.isalnum() or prev in "_)]")
            if close != -1 and "[" not in inner and not indexing:
                if inner in known:
                    out.append(f"{frame}[{inner!r}]")
                    i = close + 1
                    continue
                if IDENT_LIKE.match(inner):
                    raise ExprError(unknown_message(inner, columns))
        out.append(ch)
        i += 1
    return "".join(out)


def previous_word_char(expr, i):
    return i > 0 and (expr[i - 1].isalnum() or expr[i - 1] in "_.")


def skip_string(expr, start):
    quote = expr[start]
    triple = expr[start:start + 3] == quote * 3
    delim = quote * 3 if triple else quote
    i = start + len(delim)
    while i < len(expr):
        if expr[i] == "\\":
            i += 2
            continue
        if expr.startswith(delim, i):
            return i + len(delim)
        i += 1
    return len(expr)


def previous_char(expr, i):
    j = i - 1
    while j >= 0 and expr[j].isspace():
        j -= 1
    return expr[j] if j >= 0 else ""


def unknown_message(name, columns):
    close = difflib.get_close_matches(name, list(columns), n=3, cutoff=0.45)
    hint = f" Did you mean {', '.join('[' + c + ']' for c in close)}?" if close else ""
    return f"Unknown column [{name}].{hint}"
