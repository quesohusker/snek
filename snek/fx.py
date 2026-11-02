import decimal
import math
import re

import numpy as np
import pandas as pd


def _blank(v):
    if isinstance(v, (list, tuple, dict, set, np.ndarray)):
        return False
    return bool(pd.isna(v))


def _is_seq(a):
    return isinstance(a, (pd.Series, pd.Index, list, tuple, np.ndarray))


def _cols(args):
    index = None
    for a in args:
        if isinstance(a, pd.Series):
            index = a.index
            break
    if index is None:
        for a in args:
            if _is_seq(a):
                index = pd.RangeIndex(len(a))
                break
    if index is None:
        return None, [pd.Series([a]) for a in args]
    cols = []
    for a in args:
        if isinstance(a, pd.Series):
            cols.append(a if a.index.equals(index) else a.set_axis(index))
        elif _is_seq(a):
            cols.append(pd.Series(list(a), index=index))
        else:
            cols.append(pd.Series([a] * len(index), index=index))
    return index, cols


def _done(out, index):
    if index is not None:
        return out
    v = out.iloc[0]
    return v.item() if isinstance(v, np.generic) else v


def _each(func, *args, keep_blank=False):
    index, cols = _cols(args)
    out = []
    for vals in zip(*cols):
        if not keep_blank and any(_blank(v) for v in vals):
            out.append(np.nan)
            continue
        try:
            out.append(func(*vals))
        except (ValueError, TypeError, ArithmeticError, IndexError, KeyError):
            out.append(np.nan)
    return _done(pd.Series(out, index=cols[0].index), index)


def _f64(s):
    return pd.to_numeric(s, errors="coerce").to_numpy(dtype="float64", na_value=np.nan)


def _vec(func, *args):
    index, cols = _cols(args)
    arrays = [_f64(c) for c in cols]
    with np.errstate(all="ignore"):
        out = np.asarray(func(*arrays), dtype="float64")
    out = np.where(np.isfinite(out), out, np.nan)
    return _done(pd.Series(out, index=cols[0].index), index)


def _flat(args):
    return _values(args)


def _truth(s):
    if isinstance(s.dtype, np.dtype) and s.dtype.kind == "b":
        return s.to_numpy()
    if isinstance(s.dtype, np.dtype) and s.dtype.kind in "iuf":
        v = s.to_numpy(dtype="float64")
        return (v != 0) & ~np.isnan(v)

    def one(v):
        if _blank(v):
            return False
        if isinstance(v, str):
            return v.strip().upper() == "TRUE"
        return bool(v)

    return np.fromiter((one(v) for v in s), dtype=bool, count=len(s))


def _pick(cond, a, b):
    numeric = all(isinstance(x.dtype, np.dtype) and x.dtype.kind in "iuf" for x in (a, b))
    if numeric:
        return pd.Series(np.where(cond, a.to_numpy(), b.to_numpy()), index=a.index)
    vals = np.where(cond, a.astype(object).to_numpy(), b.astype(object).to_numpy())
    return pd.Series(vals, index=a.index).infer_objects()


def _num1(v):
    if isinstance(v, (bool, np.bool_)):
        return float(v)
    if isinstance(v, str):
        return float(v.strip())
    if isinstance(v, pd.Timestamp):
        return _serial(v)
    return float(v)


def _serial(ts):
    days = (ts - pd.Timestamp("1899-12-30")) / pd.Timedelta(days=1)
    return days - 1 if ts < pd.Timestamp("1900-03-01") else days


def _date_text_serial(text):
    t = text.strip()
    time = r"\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:\s*[AaPp][Mm])?"
    if re.fullmatch(time, t):
        stamp = pd.Timestamp("2000-01-01 " + t)
        return (stamp - stamp.normalize()) / pd.Timedelta(days=1)
    dates = rf"\d{{4}}-\d{{1,2}}-\d{{1,2}}(?:[ T]{time})?|\d{{1,2}}/\d{{1,2}}/\d{{2,4}}(?:\s+{time})?|[A-Za-z]{{3,9}}\.? \d{{1,2}},? \d{{4}}|\d{{1,2}} [A-Za-z]{{3,9}}\.? \d{{4}}"
    if re.fullmatch(dates, t):
        return _serial(pd.Timestamp(t))
    raise ValueError("not a date")


def _num_text(f):
    if f == 0:
        return "0"
    sign = "-" if f < 0 else ""
    mant, exp = format(abs(f), ".14e").split("e")
    digits = mant.replace(".", "").rstrip("0") or "0"
    e10 = int(exp)
    decimals = max(0, len(digits) - 1 - e10)
    if e10 < 20 and decimals <= 18:
        if e10 >= 0:
            whole = digits[:e10 + 1].ljust(e10 + 1, "0")
            frac = digits[e10 + 1:]
            return sign + whole + ("." + frac if frac else "")
        return sign + "0." + "0" * (-e10 - 1) + digits
    body = digits[0] + ("." + digits[1:] if len(digits) > 1 else "")
    return f"{sign}{body}E{'-' if e10 < 0 else '+'}{abs(e10):02d}"


def _txt(v):
    if _blank(v):
        return ""
    if isinstance(v, (bool, np.bool_)):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (float, np.floating)):
        f = float(v)
        return "#NUM!" if math.isinf(f) else _num_text(f)
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d") if v == v.normalize() else v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)


def _nn(n):
    k = int(_num1(n))
    if k < 0:
        raise ValueError("negative")
    return k


def IF(logical_test, value_if_true=True, value_if_false=False):
    index, (t, a, b) = _cols((logical_test, value_if_true, value_if_false))
    return _done(_pick(_truth(t), a, b), index)


def IFS(*args):
    if len(args) < 2 or len(args) % 2:
        raise ValueError("IFS needs pairs of a test and a value")
    index, cols = _cols(args)
    n = len(cols[0])
    res = np.full(n, np.nan, dtype=object)
    done = np.zeros(n, dtype=bool)
    for i in range(0, len(cols), 2):
        hit = _truth(cols[i]) & ~done
        res[hit] = cols[i + 1].astype(object).to_numpy()[hit]
        done |= hit
    return _done(pd.Series(res, index=cols[0].index).infer_objects(), index)


def _errors(s):
    if isinstance(s.dtype, np.dtype) and s.dtype.kind == "f":
        v = s.to_numpy()
        return np.isnan(v) | np.isinf(v)
    return np.fromiter((_blank(v) or (isinstance(v, float) and math.isinf(v)) for v in s), dtype=bool, count=len(s))


def IFERROR(value, value_if_error):
    index, (v, e) = _cols((value, value_if_error))
    return _done(_pick(_errors(v), e, v), index)


def IFNA(value, value_if_na):
    index, (v, e) = _cols((value, value_if_na))
    return _done(_pick(v.isna().to_numpy(), e, v), index)


def SWITCH(expression, *args):
    if len(args) < 2:
        raise ValueError("SWITCH needs at least one value and result")
    index, cols = _cols((expression,) + args)
    n = len(cols[0])
    has_default = len(args) % 2 == 1
    pairs = len(args) // 2
    res = np.full(n, np.nan, dtype=object)
    done = np.zeros(n, dtype=bool)

    def fold(v):
        return v.lower() if isinstance(v, str) else v

    target = [fold(v) for v in cols[0]]
    for i in range(pairs):
        cand = [fold(v) for v in cols[1 + 2 * i]]
        hit = np.fromiter((a == b for a, b in zip(target, cand)), dtype=bool, count=n) & ~done
        res[hit] = cols[2 + 2 * i].astype(object).to_numpy()[hit]
        done |= hit
    if has_default:
        res[~done] = cols[-1].astype(object).to_numpy()[~done]
    return _done(pd.Series(res, index=cols[0].index).infer_objects(), index)


def _logic(args, reducer):
    index, cols = _cols(args)
    out = reducer([_truth(c) for c in cols])
    return _done(pd.Series(out, index=cols[0].index), index)


def AND(*args):
    return _logic(args, lambda parts: np.logical_and.reduce(parts))


def OR(*args):
    return _logic(args, lambda parts: np.logical_or.reduce(parts))


def XOR(*args):
    return _logic(args, lambda parts: np.sum(parts, axis=0) % 2 == 1)


def NOT(logical):
    return _logic((logical,), lambda parts: ~parts[0])


def TRUE():
    return True


def FALSE():
    return False


def ISBLANK(value):
    return _each(_blank, value, keep_blank=True)


def ISNUMBER(value):
    def check(v):
        if isinstance(v, (bool, np.bool_)) or not isinstance(v, (int, float, np.integer, np.floating)):
            return False
        return not _blank(v) and not math.isinf(v)

    return _each(check, value, keep_blank=True)


def ISTEXT(value):
    return _each(lambda v: isinstance(v, str), value, keep_blank=True)


def ISNONTEXT(value):
    return _each(lambda v: not isinstance(v, str), value, keep_blank=True)


def ISLOGICAL(value):
    return _each(lambda v: isinstance(v, (bool, np.bool_)), value, keep_blank=True)


def ISERROR(value):
    return _each(lambda v: _blank(v) or (isinstance(v, float) and math.isinf(v)), value, keep_blank=True)


def ISNA(value):
    return _each(_blank, value, keep_blank=True)


def ISEVEN(number):
    return _each(lambda v: int(_num1(v)) % 2 == 0, number)


def ISODD(number):
    return _each(lambda v: int(_num1(v)) % 2 == 1, number)


def NA():
    return np.nan


def N(value):
    def one(v):
        if _blank(v) or isinstance(v, str):
            return 0
        if isinstance(v, (bool, np.bool_)):
            return int(v)
        if isinstance(v, pd.Timestamp):
            return _serial(v)
        return v

    return _each(one, value, keep_blank=True)


def TYPE(value):
    def one(v):
        if isinstance(v, (bool, np.bool_)):
            return 4
        if isinstance(v, str):
            return 2
        if isinstance(v, (list, tuple, np.ndarray)):
            return 64
        if isinstance(v, float) and math.isinf(v):
            return 16
        return 1

    return _each(one, value, keep_blank=True)


def _proper(s):
    out, prev = [], False
    for ch in s:
        if ch.isalpha():
            out.append(ch.lower() if prev else ch.upper())
            prev = True
        else:
            out.append(ch)
            prev = False
    return "".join(out)


def LEFT(text, num_chars=1):
    return _each(lambda t, n: _txt(t)[:_nn(n)], text, num_chars)


def RIGHT(text, num_chars=1):
    def one(t, n):
        s, k = _txt(t), _nn(n)
        return s[len(s) - k:] if k < len(s) else s

    return _each(one, text, num_chars)


def MID(text, start_num, num_chars):
    def one(t, a, n):
        start, k = int(_num1(a)), _nn(n)
        if start < 1:
            raise ValueError("start")
        return _txt(t)[start - 1:start - 1 + k]

    return _each(one, text, start_num, num_chars)


def LEN(text):
    return _each(lambda t: len(_txt(t)), text, keep_blank=True)


def UPPER(text):
    return _each(lambda t: _txt(t).upper(), text)


def LOWER(text):
    return _each(lambda t: _txt(t).lower(), text)


def PROPER(text):
    return _each(lambda t: _proper(_txt(t)), text)


def TRIM(text):
    return _each(lambda t: re.sub(" +", " ", _txt(t)).strip(" "), text)


def CLEAN(text):
    return _each(lambda t: re.sub(r"[\x00-\x1f]", "", _txt(t)), text)


def CONCAT(*text):
    return _each(lambda *v: "".join(_txt(x) for x in v), *text, keep_blank=True)


def CONCATENATE(*text):
    return CONCAT(*text)


def TEXTJOIN(delimiter, ignore_empty, *text):
    def one(d, skip, *v):
        parts = [_txt(x) for x in v]
        if _truth(pd.Series([skip]))[0]:
            parts = [p for p in parts if p != ""]
        return _txt(d).join(parts)

    return _each(one, delimiter, ignore_empty, *text, keep_blank=True)


def _occurrences(text, delim, mode, match_end, instance):
    if instance == 0:
        raise ValueError("instance")
    if delim == "":
        spans = [(0, 0)] if instance > 0 else [(len(text), len(text))]
    else:
        spans = [m.span() for m in re.finditer(re.escape(delim), text, re.IGNORECASE if mode else 0)]
    if match_end:
        if instance > 0:
            spans.append((len(text), len(text)))
        else:
            spans.insert(0, (0, 0))
    pos = instance - 1 if instance > 0 else instance
    if pos >= len(spans) or pos < -len(spans):
        raise ValueError("not found")
    return spans[pos]


def TEXTBEFORE(text, delimiter, instance_num=1, match_mode=0, match_end=0, if_not_found=np.nan):
    def one(t, d):
        try:
            start, _ = _occurrences(_txt(t), _txt(d), match_mode, match_end, int(instance_num))
        except ValueError:
            return if_not_found
        return _txt(t)[:start]

    return _each(one, text, delimiter)


def TEXTAFTER(text, delimiter, instance_num=1, match_mode=0, match_end=0, if_not_found=np.nan):
    def one(t, d):
        try:
            _, end = _occurrences(_txt(t), _txt(d), match_mode, match_end, int(instance_num))
        except ValueError:
            return if_not_found
        return _txt(t)[end:]

    return _each(one, text, delimiter)


def FIND(find_text, within_text, start_num=1):
    def one(f, w, a):
        within, start = _txt(w), int(_num1(a))
        if start < 1 or start > len(within):
            raise ValueError("start")
        i = within.find(_txt(f), start - 1)
        if i < 0:
            raise ValueError("not found")
        return i + 1

    return _each(one, find_text, within_text, start_num, keep_blank=True)


def _wildcard(pattern):
    out, i = [], 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "~" and i + 1 < len(pattern) and pattern[i + 1] in "*?~":
            out.append(re.escape(pattern[i + 1]))
            i += 2
            continue
        out.append(".*" if ch == "*" else "." if ch == "?" else re.escape(ch))
        i += 1
    return re.compile("".join(out), re.IGNORECASE | re.DOTALL)


def SEARCH(find_text, within_text, start_num=1):
    def one(f, w, a):
        within, start = _txt(w), int(_num1(a))
        if start < 1 or start > len(within):
            raise ValueError("start")
        m = _wildcard(_txt(f)).search(within, start - 1)
        if m is None:
            raise ValueError("not found")
        return m.start() + 1

    return _each(one, find_text, within_text, start_num, keep_blank=True)


def SUBSTITUTE(text, old_text, new_text, instance_num=None):
    def one(t, o, n):
        s, old, new = _txt(t), _txt(o), _txt(n)
        if old == "":
            return s
        if instance_num is None:
            return s.replace(old, new)
        k, pos = int(_num1(instance_num)), -1
        if k < 1:
            raise ValueError("instance")
        for _ in range(k):
            pos = s.find(old, pos + 1)
            if pos < 0:
                return s
        return s[:pos] + new + s[pos + len(old):]

    return _each(one, text, old_text, new_text, keep_blank=True)


def REPLACE(old_text, start_num, num_chars, new_text):
    def one(t, a, n, r):
        s, start, k = _txt(t), int(_num1(a)), _nn(n)
        if start < 1:
            raise ValueError("start")
        return s[:start - 1] + _txt(r) + s[start - 1 + k:]

    return _each(one, old_text, start_num, num_chars, new_text, keep_blank=True)


def REPT(text, number_times):
    def one(t, n):
        s, k = _txt(t), _nn(n)
        if len(s) * k > 32767:
            raise ValueError("too long")
        return s * k

    return _each(one, text, number_times)


def EXACT(text1, text2):
    return _each(lambda a, b: _txt(a) == _txt(b), text1, text2, keep_blank=True)


def _strict_number(s):
    t = s.strip()
    if not t:
        raise ValueError("empty")
    negative = len(t) > 1 and t[0] == "(" and t[-1] == ")"
    if negative:
        t = t[1:-1].strip()
    percent = 0
    if t.startswith("%"):
        percent, t = 1, t[1:].strip()
    elif t.endswith("%"):
        percent, t = 1, t[:-1].strip()
    m = re.fullmatch(r"([+-]?)\s*[$\u20ac]?\s*([+-]?)\s*(.+)", t)
    if m is None or (m.group(1) and m.group(2)) or (negative and (m.group(1) or m.group(2))):
        raise ValueError("sign")
    body = m.group(3)
    plain = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d*)?(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?"
    mixed = re.fullmatch(r"(\d+) (\d+)/(\d+)", body)
    if mixed:
        value = int(mixed.group(1)) + int(mixed.group(2)) / int(mixed.group(3))
    elif re.fullmatch(plain, body):
        value = float(body.replace(",", ""))
    else:
        raise ValueError("number")
    if m.group(1) == "-" or m.group(2) == "-" or negative:
        value = -value
    return value / (100 ** percent)


def _loose_number(s, decimal_sep, group_sep):
    t = s.replace(" ", "")
    if not t:
        return 0.0
    negative = len(t) > 1 and t[0] == "(" and t[-1] == ")"
    if negative:
        t = t[1:-1]
    percent = len(t) - len(t.rstrip("%"))
    t = t.rstrip("%").replace("$", "")
    if not decimal_sep or len(decimal_sep) != 1 or decimal_sep == group_sep:
        raise ValueError("separators")
    if t.count(decimal_sep) > 1:
        raise ValueError("decimal")
    whole, sep, frac = t.partition(decimal_sep)
    if group_sep and group_sep in frac:
        raise ValueError("group")
    if group_sep:
        whole = whole.replace(group_sep, "")
    t = whole + ("." if sep else "") + frac
    if not re.fullmatch(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?", t):
        raise ValueError("number")
    value = float(t)
    return (-value if negative else value) / (100 ** percent)


def VALUE(text):
    def one(v):
        if isinstance(v, (bool, np.bool_)):
            raise ValueError("logical")
        if isinstance(v, (int, float, np.integer, np.floating)):
            return float(v)
        if isinstance(v, pd.Timestamp):
            return _serial(v)
        s = _txt(v)
        try:
            return _strict_number(s)
        except ValueError:
            return _date_text_serial(s)

    return _each(one, text)


def NUMBERVALUE(text, decimal_separator=".", group_separator=None):
    group = group_separator if group_separator is not None else ("." if decimal_separator == "," else ",")

    def one(t):
        s = _txt(t)
        try:
            return _loose_number(s, decimal_separator, group)
        except ValueError:
            return _date_text_serial(s)

    return _each(one, text)


def _dec(x):
    return decimal.Decimal(format(float(x), ".15g"))


def _half_up(x, digits):
    return _dec(x).quantize(decimal.Decimal(1).scaleb(-digits), rounding=decimal.ROUND_HALF_UP)


def _fixed(x, digits, commas):
    q = _half_up(x, digits)
    body = format(abs(q), ",f" if commas else "f")
    if digits < 0:
        body = body.split(".")[0]
    return ("-" if q < 0 else "") + body


def FIXED(number, decimals=2, no_commas=False):
    return _each(lambda x, d: _fixed(_num1(x), int(_num1(d)), not _truth(pd.Series([no_commas]))[0]), number, decimals)


def DOLLAR(number, decimals=2):
    def one(x, d):
        v, k = _num1(x), int(_num1(d))
        s = _fixed(abs(v), k, True)
        return f"(${s})" if v < 0 else f"${s}"

    return _each(one, number, decimals)


def _split_sections(fmt):
    sections, cur, i, quote = [], [], 0, False
    while i < len(fmt):
        ch = fmt[i]
        if ch == '"':
            quote = not quote
        if ch == "\\" and i + 1 < len(fmt) and not quote:
            cur.append(fmt[i:i + 2])
            i += 2
            continue
        if ch == ";" and not quote:
            sections.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    sections.append("".join(cur))
    return sections


def _tokens(fmt):
    out, i = [], 0
    pattern = re.compile(r"(AM/PM|am/pm|A/P|a/p|yyyy|yy|mmmmm|mmmm|mmm|mm|m|dddd|ddd|dd|d|hh|h|ss|s)", re.IGNORECASE)
    while i < len(fmt):
        ch = fmt[i]
        if ch == '"':
            j = fmt.find('"', i + 1)
            j = len(fmt) if j < 0 else j
            out.append(("lit", fmt[i + 1:j]))
            i = j + 1
            continue
        if ch == "\\" and i + 1 < len(fmt):
            out.append(("lit", fmt[i + 1]))
            i += 2
            continue
        if ch == "_" and i + 1 < len(fmt):
            out.append(("lit", " "))
            i += 2
            continue
        m = pattern.match(fmt, i)
        if m:
            out.append(("tok", m.group(0)))
            i = m.end()
            continue
        out.append(("lit", ch))
        i += 1
    return out


def _format_date(ts, fmt):
    toks = _tokens(fmt)
    twelve = any(k == "tok" and v.upper() in ("AM/PM", "A/P") for k, v in toks)
    kinds = [v.lower() if k == "tok" else None for k, v in toks]
    out = []
    for n, (kind, val) in enumerate(toks):
        if kind == "lit":
            out.append(val)
            continue
        t = val.lower()
        if t in ("m", "mm"):
            before = next((kinds[j] for j in range(n - 1, -1, -1) if kinds[j] is not None), None)
            after = next((kinds[j] for j in range(n + 1, len(kinds)) if kinds[j] is not None), None)
            if before in ("h", "hh") or after in ("s", "ss"):
                out.append(f"{ts.minute:02d}" if t == "mm" else str(ts.minute))
                continue
        hour = (ts.hour % 12 or 12) if twelve else ts.hour
        out.append({
            "yyyy": f"{ts.year:04d}", "yy": f"{ts.year % 100:02d}",
            "mmmmm": ts.strftime("%B")[0], "mmmm": ts.strftime("%B"), "mmm": ts.strftime("%b"),
            "mm": f"{ts.month:02d}", "m": str(ts.month),
            "dddd": ts.strftime("%A"), "ddd": ts.strftime("%a"), "dd": f"{ts.day:02d}", "d": str(ts.day),
            "hh": f"{hour:02d}", "h": str(hour), "ss": f"{ts.second:02d}", "s": str(ts.second),
            "am/pm": ("AM" if ts.hour < 12 else "PM"), "a/p": ("A" if ts.hour < 12 else "P"),
        }[t])
        if t == "am/pm" and val != "AM/PM":
            out[-1] = out[-1].lower()
        if t == "a/p" and val != "A/P":
            out[-1] = out[-1].lower()
    return "".join(out)


def _literalize(fmt):
    out, lits, i = [], [], 0
    while i < len(fmt):
        ch = fmt[i]
        if ch == '"':
            j = fmt.find('"', i + 1)
            j = len(fmt) if j < 0 else j
            lits.append(fmt[i + 1:j])
            out.append("\x00")
            i = j + 1
            continue
        if ch == "\\" and i + 1 < len(fmt):
            lits.append(fmt[i + 1])
            out.append("\x00")
            i += 2
            continue
        if ch == "_" and i + 1 < len(fmt):
            lits.append(" ")
            out.append("\x00")
            i += 2
            continue
        if ch == "*" and i + 1 < len(fmt):
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out), lits


def _format_number(v, fmt):
    masked, lits = _literalize(fmt)
    pending = iter(lits)

    def restore(seg):
        return re.sub("\x00", lambda m: next(pending, ""), seg)

    body = re.search(r"[0#?][0#?,]*(?:\.[0#?]*)?,*(?:[Ee][+-]0+)?|\.[0#?]+,*", masked)
    if body is None:
        return restore(masked), False
    start, end = body.span()
    prefix, suffix = restore(masked[:start]), restore(masked[end:])
    spec = masked[start:end]
    exp = re.search(r"[Ee]([+-])(0+)$", spec)
    if exp:
        spec = spec[:exp.start()]
    trailing = len(spec) - len(spec.rstrip(","))
    int_spec, _, dec_spec = spec.rstrip(",").partition(".")
    thousands = "," in int_spec
    digits_int = int_spec.replace(",", "")
    min_int = digits_int.count("0")
    decimals = len(dec_spec)
    x = _dec(abs(v)) * (100 ** masked.count("%")) / (1000 ** trailing)
    quantum = decimal.Decimal(1).scaleb(-decimals)
    if exp:
        engineering = "#" in digits_int
        step = max(len(digits_int), 1) if engineering else 1
        adjusted = 0 if x == 0 else x.adjusted()
        e10 = (adjusted // step) * step
        q = x.scaleb(-e10).quantize(quantum, rounding=decimal.ROUND_HALF_UP)
        if q >= decimal.Decimal(10) ** step and x != 0:
            e10 += step
            q = x.scaleb(-e10).quantize(quantum, rounding=decimal.ROUND_HALF_UP)
        whole, _, frac = format(q, "f").partition(".")
        whole = whole.rjust(min_int, "0")
        esign = "-" if e10 < 0 else ("+" if exp.group(1) == "+" else "")
        num = whole + ("." + frac if decimals else "") + "E" + esign + str(abs(e10)).zfill(len(exp.group(2)))
        return prefix + num + suffix, q != 0
    q = x.quantize(quantum, rounding=decimal.ROUND_HALF_UP)
    whole, _, frac = format(q, "f").partition(".")
    sig = frac.rstrip("0")
    frac_out = "".join(sig[i] if i < len(sig) else {"0": "0", "?": " ", "#": ""}[dec_spec[i]] for i in range(decimals))
    w = whole.lstrip("0")
    zeros, spaces = "", ""
    for k in range(len(w), len(digits_int)):
        ph = digits_int[len(digits_int) - 1 - k]
        if ph == "0":
            zeros += "0"
        elif ph == "?":
            spaces += " "
    core = zeros + w
    if thousands:
        core = re.sub(r"(?<=\d)(?=(\d{3})+$)", ",", core)
    num = spaces + core + ("." + frac_out if decimals or "." in spec else "")
    return prefix + num + suffix, q != 0


def _format_text(value, fmt):
    if fmt.strip().lower() == "general":
        return _txt(value)
    fmt = re.sub(r"\[\$([^\]-]*)[^\]]*\]", lambda m: '"' + m.group(1) + '"', fmt)
    sections = _split_sections(fmt)
    stripped = lambda sec: re.sub(r'"[^"]*"|\\.|_.|\[[^\]]*\]', "", sec)
    if isinstance(value, str):
        try:
            value = _strict_number(value)
        except ValueError:
            try:
                value = pd.Timestamp(value.strip())
            except (ValueError, TypeError):
                text_sec = sections[3] if len(sections) > 3 else (sections[0] if "@" in sections[0] else None)
                return text_sec.replace("@", value) if text_sec is not None else value
    if isinstance(value, (bool, np.bool_)):
        return _txt(value)
    stamp = value if isinstance(value, pd.Timestamp) else None
    number = None if stamp is not None else float(value)
    idx = 0
    if number is not None and len(sections) > 1:
        if number < 0:
            idx = 1
        elif number == 0 and len(sections) > 2:
            idx = 2
    sec = sections[idx]
    plain = stripped(sec)
    if re.search(r"[0#?]\s*/\s*[0#?\d]", plain):
        raise ValueError("fractions are not supported")
    if re.search(r"[ymdhsYMDHS]|[AaPp]/[AaPp]|AM/PM", plain):
        if stamp is None:
            stamp = pd.Timestamp("1899-12-30") + pd.Timedelta(days=number)
        return _format_date(stamp, re.sub(r"\[[^\]]*\]", "", sec))
    if stamp is not None:
        number = _serial(stamp)
    if "@" in plain and not re.search(r"[0#?]", plain):
        return sec.replace("@", _txt(value) if stamp is None else _txt(number), 1) if "@@" not in plain else _txt(value)
    use = abs(number) if idx else number
    text, nonzero = _format_number(abs(use), re.sub(r"\[[^\]]*\]", "", sec))
    return ("-" if use < 0 and len(sections) == 1 and nonzero else "") + text


def TEXT(value, format_text):
    return _each(lambda v, f: _format_text(v, _txt(f)), value, format_text)


def CHAR(number):
    def one(n):
        k = int(_num1(n))
        if not 1 <= k <= 255:
            raise ValueError("range")
        return bytes([k]).decode("cp1252", errors="replace")

    return _each(one, number)


def CODE(text):
    def one(t):
        s = _txt(t)
        if not s:
            raise ValueError("empty")
        try:
            return s[0].encode("cp1252")[0]
        except UnicodeEncodeError:
            return 63

    return _each(one, text)


def UNICHAR(number):
    def one(n):
        k = int(_num1(n))
        if k < 1 or k > 0x10FFFF or 0xD800 <= k <= 0xDFFF:
            raise ValueError("range")
        return chr(k)

    return _each(one, number)


def UNICODE(text):
    def one(t):
        s = _txt(t)
        if not s:
            raise ValueError("empty")
        return ord(s[0])

    return _each(one, text)


def T(value):
    return _each(lambda v: v if isinstance(v, str) else "", value, keep_blank=True)


def REGEXTEST(text, pattern, case_sensitivity=0):
    flags = re.IGNORECASE if int(case_sensitivity) == 1 else 0
    return _each(lambda t, p: re.search(_txt(p), _txt(t), flags) is not None, text, pattern)


def REGEXEXTRACT(text, pattern, return_mode=0, case_sensitivity=0):
    flags = re.IGNORECASE if int(case_sensitivity) == 1 else 0

    def one(t, p):
        rx = re.compile(_txt(p), flags)
        if int(return_mode) == 1:
            return [m.group(0) for m in rx.finditer(_txt(t))]
        m = rx.search(_txt(t))
        if m is None:
            raise ValueError("no match")
        if int(return_mode) == 2:
            return list(m.groups())
        return m.group(0)

    return _each(one, text, pattern)


def REGEXREPLACE(text, pattern, replacement, occurrence=0, case_sensitivity=0):
    flags = re.IGNORECASE if int(case_sensitivity) == 1 else 0

    def one(t, p, r):
        rx = re.compile(_txt(p), flags)
        s = _txt(t)
        template = re.sub(r"\$(\d+)", r"\\g<\1>", _txt(r).replace("\\", "\\\\").replace("$$", "\x00")).replace("\x00", "$")
        k = int(occurrence)
        if k == 0:
            return rx.sub(template, s)
        spans = list(rx.finditer(s))
        if not spans or abs(k) > len(spans):
            return s
        m = spans[k - 1] if k > 0 else spans[k]
        return s[:m.start()] + m.expand(template) + s[m.end():]

    return _each(one, text, pattern, replacement)


def _ts(v):
    if isinstance(v, pd.Timestamp):
        return v
    if isinstance(v, str):
        return pd.Timestamp(v.strip())
    if isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, (bool, np.bool_)):
        base = "1899-12-31" if 0 <= v < 61 else "1899-12-30"
        return pd.Timestamp(base) + pd.Timedelta(days=float(v))
    return pd.Timestamp(v)


def _from_serials(v):
    base = pd.Timestamp("1899-12-30") + pd.to_timedelta(v, unit="D")
    early = (v >= 0) & (v < 61)
    return base.where(~early, base + pd.Timedelta(days=1))


def _dates(s):
    if isinstance(s.dtype, pd.DatetimeTZDtype) or (isinstance(s.dtype, np.dtype) and s.dtype.kind == "M"):
        return s
    if isinstance(s.dtype, np.dtype) and s.dtype.kind == "m":
        return pd.Timestamp("1899-12-30") + s
    if isinstance(s.dtype, np.dtype) and s.dtype.kind in "iuf":
        return _from_serials(s.astype("float64"))
    if pd.api.types.is_string_dtype(s) or s.dtype == object:
        return pd.Series([pd.NaT if _blank(v) else _try_ts(v) for v in s], index=s.index, dtype="datetime64[us]")
    return pd.to_datetime(s, errors="coerce")


def _try_ts(v):
    try:
        return _ts(v)
    except (ValueError, TypeError, OverflowError):
        return pd.NaT


def _part(value, func):
    index, (s,) = _cols((value,))
    if isinstance(s.dtype, np.dtype) and s.dtype.kind in "iuf":
        v = s.astype("float64")
        whole = np.floor(v)
        secs = np.floor((v - whole) * 86400 + 0.5)
        d = _from_serials(whole) + pd.to_timedelta(secs, unit="s")
    else:
        d = (_dates(s) + pd.Timedelta(milliseconds=500)).dt.floor("s")
    return _done(func(d).astype("Int64"), index)


def DATE(year, month, day):
    def one(y, m, d):
        yy, mm, dd = int(_num1(y)), int(_num1(m)), int(_num1(d))
        if yy < 0 or yy > 9999:
            raise ValueError("year")
        if yy < 1900:
            yy += 1900
        total = yy * 12 + (mm - 1)
        return pd.Timestamp(year=total // 12, month=total % 12 + 1, day=1) + pd.Timedelta(days=dd - 1)

    return _each(one, year, month, day)


def TIME(hour, minute, second):
    def one(h, m, s):
        parts = [int(_num1(x)) for x in (h, m, s)]
        if any(abs(x) > 32767 for x in parts):
            raise ValueError("range")
        secs = parts[0] * 3600 + parts[1] * 60 + parts[2]
        if secs < 0:
            raise ValueError("negative")
        return pd.Timedelta(seconds=secs % 86400)

    return _each(one, hour, minute, second)


def DATEVALUE(date_text):
    return _each(lambda t: pd.Timestamp(_txt(t).strip()).normalize(), date_text)


def TIMEVALUE(time_text):
    def one(t):
        stamp = pd.Timestamp(_txt(t).strip())
        return stamp - stamp.normalize()

    return _each(one, time_text)


def NOW():
    return pd.Timestamp.now()


def TODAY():
    return pd.Timestamp.now().normalize()


def YEAR(serial_number):
    return _part(serial_number, lambda d: d.dt.year)


def MONTH(serial_number):
    return _part(serial_number, lambda d: d.dt.month)


def DAY(serial_number):
    return _part(serial_number, lambda d: d.dt.day)


def HOUR(serial_number):
    return _part(serial_number, lambda d: d.dt.hour)


def MINUTE(serial_number):
    return _part(serial_number, lambda d: d.dt.minute)


def SECOND(serial_number):
    return _part(serial_number, lambda d: d.dt.second)


def WEEKDAY(serial_number, return_type=1):
    kind = int(return_type)
    if kind not in (1, 2, 3, 11, 12, 13, 14, 15, 16, 17):
        raise ValueError("return_type")

    def shape(d):
        dow = d.dt.day_of_week
        if kind in (1, 17):
            return (dow + 1) % 7 + 1
        if kind in (2, 11):
            return dow + 1
        if kind == 3:
            return dow
        return (dow - (kind - 11)) % 7 + 1

    return _part(serial_number, shape)


def _week_start(kind):
    starts = {1: 6, 2: 0, 11: 0, 12: 1, 13: 2, 14: 3, 15: 4, 16: 5, 17: 6}
    if kind not in starts:
        raise ValueError("return_type")
    return starts[kind]


def WEEKNUM(serial_number, return_type=1):
    kind = int(return_type)
    if kind == 21:
        return ISOWEEKNUM(serial_number)
    start = _week_start(kind)

    def one(v):
        d = _ts(v)
        offset = (pd.Timestamp(year=d.year, month=1, day=1).day_of_week - start) % 7
        return (d.day_of_year - 1 + offset) // 7 + 1

    return _each(one, serial_number)


def ISOWEEKNUM(date):
    return _part(date, lambda d: d.dt.isocalendar().week)


def EDATE(start_date, months):
    return _each(lambda d, m: (_ts(d) + pd.DateOffset(months=int(_num1(m)))).normalize(), start_date, months)


def EOMONTH(start_date, months):
    def one(d, m):
        shifted = _ts(d) + pd.DateOffset(months=int(_num1(m)))
        return (shifted + pd.offsets.MonthEnd(0)).normalize()

    return _each(one, start_date, months)


def DAYS(end_date, start_date):
    return _each(lambda e, s: (_ts(e).normalize() - _ts(s).normalize()).days, end_date, start_date)


def DATEDIF(start_date, end_date, unit):
    def one(a, b):
        s, e = _ts(a).normalize(), _ts(b).normalize()
        if e < s:
            raise ValueError("end before start")
        months = (e.year - s.year) * 12 + e.month - s.month - (1 if e.day < s.day else 0)
        u = str(unit).upper()
        if u == "Y":
            return months // 12
        if u == "M":
            return months
        if u == "D":
            return (e - s).days
        if u == "YM":
            return months % 12
        if u == "MD":
            if e.day >= s.day:
                return e.day - s.day
            return e.day + (e.replace(day=1) - pd.Timedelta(days=1)).day - s.day
        if u == "YD":
            def anchor(year):
                try:
                    return s.replace(year=year)
                except ValueError:
                    return pd.Timestamp(year=year, month=3, day=1)

            t = anchor(e.year)
            if t > e:
                t = anchor(e.year - 1)
            return (e - t).days
        raise ValueError("unit")

    return _each(one, start_date, end_date)


def _last_feb(t):
    return t.month == 2 and t.day == t.days_in_month


def _days360(s, e, european, yearfrac=False):
    d1, d2 = s.day, e.day
    if european:
        d1 = min(d1, 30)
        d2 = min(d2, 30)
    elif yearfrac:
        if d2 == 31 and d1 >= 30:
            d2 = 30
        if d1 == 31:
            d1 = 30
        if _last_feb(s):
            d1 = 30
            if _last_feb(e):
                d2 = 30
    else:
        if _last_feb(s):
            d1 = 30
        if d1 == 31:
            d1 = 30
        if d2 == 31 and d1 >= 30:
            d2 = 30
    return (e.year - s.year) * 360 + (e.month - s.month) * 30 + (d2 - d1)


def DAYS360(start_date, end_date, method=False):
    european = bool(_truth(pd.Series([method]))[0])
    return _each(lambda a, b: _days360(_ts(a).normalize(), _ts(b).normalize(), european), start_date, end_date)


def YEARFRAC(start_date, end_date, basis=0):
    kind = int(basis)
    if kind not in (0, 1, 2, 3, 4):
        raise ValueError("basis")

    def leap(y):
        return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)

    def one(a, b):
        s, e = _ts(a).normalize(), _ts(b).normalize()
        if s > e:
            s, e = e, s
        days = (e - s).days
        if kind in (0, 4):
            return _days360(s, e, kind == 4, yearfrac=True) / 360
        if kind == 2:
            return days / 360
        if kind == 3:
            return days / 365
        if s.year == e.year:
            return days / (366 if leap(s.year) else 365)
        within_year = e.year == s.year + 1 and (e.month, e.day) <= (s.month, s.day)
        if within_year:
            feb29 = (leap(s.year) and (s.month, s.day) <= (2, 29)) or (leap(e.year) and (e.month, e.day) >= (2, 29))
            return days / (366 if feb29 else 365)
        years = range(s.year, e.year + 1)
        return days / (sum(366 if leap(y) else 365 for y in years) / len(years))

    return _each(one, start_date, end_date)


def _weekmask(weekend):
    if isinstance(weekend, str) and len(weekend) == 7 and set(weekend) <= {"0", "1"}:
        return "".join("0" if c == "1" else "1" for c in weekend)
    code = int(weekend)
    if 1 <= code <= 7:
        off = {((code + 4) % 7), ((code + 5) % 7)}
    elif 11 <= code <= 17:
        off = {(code - 11 + 6) % 7}
    else:
        raise ValueError("weekend")
    return "".join("0" if i in off else "1" for i in range(7))


def _holidays(holidays):
    if holidays is None:
        return np.array([], dtype="datetime64[D]")
    s = pd.Series(list(holidays) if _is_seq(holidays) else [holidays])
    d = _dates(s).dropna()
    return d.dt.tz_localize(None).to_numpy().astype("datetime64[D]") if len(d) else np.array([], dtype="datetime64[D]")


def _day_array(s):
    d = _dates(s)
    if isinstance(d.dtype, pd.DatetimeTZDtype):
        d = d.dt.tz_localize(None)
    return d.to_numpy().astype("datetime64[D]")


def _networkdays(start_date, end_date, weekend, holidays):
    index, (a, b) = _cols((start_date, end_date))
    s, e = _day_array(a), _day_array(b)
    bad = np.isnat(s) | np.isnat(e)
    s0 = np.where(bad, np.datetime64("1970-01-01"), s)
    e0 = np.where(bad, np.datetime64("1970-01-01"), e)
    mask, hol = _weekmask(weekend), _holidays(holidays)
    one = np.timedelta64(1, "D")
    fwd = np.busday_count(s0, e0 + one, weekmask=mask, holidays=hol)
    back = -np.busday_count(e0, s0 + one, weekmask=mask, holidays=hol)
    out = np.where(s0 <= e0, fwd, back).astype("float64")
    out[bad] = np.nan
    return _done(pd.Series(out, index=a.index), index)


def NETWORKDAYS(start_date, end_date, holidays=None):
    return _networkdays(start_date, end_date, 1, holidays)


def NETWORKDAYS_INTL(start_date, end_date, weekend=1, holidays=None):
    return _networkdays(start_date, end_date, weekend, holidays)


def _workday(start_date, days, weekend, holidays):
    index, (a, n) = _cols((start_date, days))
    s = _day_array(a)
    k = _f64(n)
    bad = np.isnat(s) | np.isnan(k)
    s0 = np.where(bad, np.datetime64("1970-01-01"), s)
    k0 = np.floor(np.where(bad, 0, k)).astype("int64")
    mask, hol = _weekmask(weekend), _holidays(holidays)
    ahead = np.busday_offset(s0, k0, roll="backward", weekmask=mask, holidays=hol)
    behind = np.busday_offset(s0, k0, roll="forward", weekmask=mask, holidays=hol)
    out = np.where(k0 > 0, ahead, np.where(k0 < 0, behind, s0))
    res = pd.Series(out.astype("datetime64[us]"), index=a.index)
    res[bad] = pd.NaT
    return _done(res, index)


def WORKDAY(start_date, days, holidays=None):
    return _workday(start_date, days, 1, holidays)


def WORKDAY_INTL(start_date, days, weekend=1, holidays=None):
    return _workday(start_date, days, weekend, holidays)


def _snap(scaled):
    near = np.round(scaled)
    return np.where(np.abs(scaled - near) <= 2 * np.spacing(np.abs(scaled)), near, scaled)


def _scale_for(x, d):
    p = 10.0 ** np.abs(d)
    return np.where(d >= 0, np.abs(x) * p, np.abs(x) / p), p


def _unscale(r, d, p, x):
    return np.sign(x) * np.where(d >= 0, r / p, r * p)


def _tidy(out):
    r = np.round(out, 9)
    return np.where((r != 0) & (np.abs(r - out) <= 8e-16 * np.abs(out)), r, out)


def _round_core(x, d):
    x, d = np.broadcast_arrays(x, np.trunc(d))
    scaled, p = _scale_for(x, d)
    base = np.floor(scaled)
    frac = scaled - base
    up = frac >= 0.5
    for i in np.flatnonzero(np.abs(frac - 0.5) < 1e-6):
        exact = _dec(abs(x.flat[i])).scaleb(int(d.flat[i]))
        up.flat[i] = exact - exact.to_integral_value(decimal.ROUND_FLOOR) >= decimal.Decimal("0.5")
    return _unscale(base + up, d, p, x)


def ABS(number):
    return _vec(np.abs, number)


def SIGN(number):
    return _vec(np.sign, number)


def ROUND(number, num_digits=0):
    return _vec(_round_core, number, num_digits)


def ROUNDUP(number, num_digits=0):
    def core(x, d):
        x, d = np.broadcast_arrays(x, np.trunc(d))
        scaled, p = _scale_for(x, d)
        return _unscale(np.ceil(_snap(scaled)), d, p, x)

    return _vec(core, number, num_digits)


def ROUNDDOWN(number, num_digits=0):
    def core(x, d):
        x, d = np.broadcast_arrays(x, np.trunc(d))
        scaled, p = _scale_for(x, d)
        return _unscale(np.floor(_snap(scaled)), d, p, x)

    return _vec(core, number, num_digits)


def MROUND(number, multiple):
    def core(x, m):
        ratio = _snap(np.abs(x) / np.where(m == 0, np.nan, np.abs(m)))
        r = np.floor(ratio + 0.5)
        out = np.sign(x) * r * np.abs(m)
        out = np.where(m == 0, 0.0, out)
        return _tidy(np.where((x * m < 0), np.nan, out))

    return _vec(core, number, multiple)


def CEILING(number, significance=1):
    def core(x, s):
        out = np.ceil(_snap(x / np.where(s == 0, np.nan, s))) * s
        out = np.where(s == 0, 0.0, out)
        return _tidy(np.where((x > 0) & (s < 0), np.nan, out))

    return _vec(core, number, significance)


def FLOOR(number, significance=1):
    def core(x, s):
        out = np.floor(_snap(x / np.where(s == 0, np.nan, s))) * s
        out = np.where(s == 0, np.nan, out)
        return _tidy(np.where((x > 0) & (s < 0), np.nan, out))

    return _vec(core, number, significance)


def CEILING_MATH(number, significance=1, mode=0):
    def core(x, s, m):
        s = np.abs(s)
        ratio = _snap(x / np.where(s == 0, np.nan, s))
        out = np.where((x < 0) & (m != 0), np.floor(ratio), np.ceil(ratio)) * s
        return _tidy(np.where(s == 0, 0.0, out))

    return _vec(core, number, significance, mode)


def FLOOR_MATH(number, significance=1, mode=0):
    def core(x, s, m):
        s = np.abs(s)
        ratio = _snap(x / np.where(s == 0, np.nan, s))
        out = np.where((x < 0) & (m != 0), np.ceil(ratio), np.floor(ratio)) * s
        return _tidy(np.where(s == 0, 0.0, out))

    return _vec(core, number, significance, mode)


def INT(number):
    return _vec(np.floor, number)


def TRUNC(number, num_digits=0):
    def core(x, d):
        x, d = np.broadcast_arrays(x, np.trunc(d))
        scaled, p = _scale_for(x, d)
        return _unscale(np.floor(_snap(scaled)), d, p, x)

    return _vec(core, number, num_digits)


def MOD(number, divisor):
    return _vec(lambda x, d: np.mod(x, np.where(d == 0, np.nan, d)), number, divisor)


def QUOTIENT(numerator, denominator):
    return _vec(lambda n, d: np.trunc(_snap(n / np.where(d == 0, np.nan, d))), numerator, denominator)


def POWER(number, power):
    def core(x, y):
        x, y = np.broadcast_arrays(x, y)
        plain = np.power(x, y)
        inv = 1 / np.where(y == 0, np.nan, y)
        root = np.round(inv)
        odd_root = (np.abs(inv - root) < 1e-9) & (root % 2 == 1)
        out = np.where((x < 0) & (y != np.floor(y)) & odd_root, -np.power(np.abs(x), y), plain)
        return np.where((x == 0) & (y == 0), np.nan, out)

    return _vec(core, number, power)


def SQRT(number):
    return _vec(np.sqrt, number)


def SQRTPI(number):
    return _vec(lambda x: np.sqrt(x * np.pi), number)


def EXP(number):
    return _vec(np.exp, number)


def LN(number):
    return _vec(np.log, number)


def LOG(number, base=10):
    return _vec(lambda x, b: np.log(x) / np.where((b == 1) | (b <= 0), np.nan, np.log(np.where(b > 0, b, 1.0))), number, base)


def LOG10(number):
    return _vec(np.log10, number)


def PI():
    return math.pi


def DEGREES(angle):
    return _vec(np.degrees, angle)


def RADIANS(angle):
    return _vec(np.radians, angle)


def SIN(number):
    return _vec(np.sin, number)


def COS(number):
    return _vec(np.cos, number)


def TAN(number):
    return _vec(np.tan, number)


def ASIN(number):
    return _vec(np.arcsin, number)


def ACOS(number):
    return _vec(np.arccos, number)


def ATAN(number):
    return _vec(np.arctan, number)


def ATAN2(x_num, y_num):
    return _vec(lambda x, y: np.where((x == 0) & (y == 0), np.nan, np.arctan2(y, x)), x_num, y_num)


def SINH(number):
    return _vec(np.sinh, number)


def COSH(number):
    return _vec(np.cosh, number)


def TANH(number):
    return _vec(np.tanh, number)


def FACT(number):
    table = np.array([math.factorial(i) for i in range(171)], dtype="float64")

    def core(x):
        k = np.floor(x)
        ok = (k >= 0) & (k <= 170)
        return np.where(ok, table[np.clip(np.where(ok, k, 0), 0, 170).astype(int)], np.nan)

    return _vec(core, number)


def COMBIN(number, number_chosen):
    def one(n, k):
        n, k = int(_num1(n)), int(_num1(k))
        if n < 0 or k < 0 or k > n:
            raise ValueError("range")
        return float(math.comb(n, k))

    return _each(one, number, number_chosen)


def GCD(*numbers):
    def one(*v):
        ints = [int(_num1(x)) for x in v]
        if any(i < 0 for i in ints):
            raise ValueError("negative")
        return math.gcd(*ints)

    return _each(one, *numbers)


def LCM(*numbers):
    def one(*v):
        ints = [int(_num1(x)) for x in v]
        if any(i < 0 for i in ints):
            raise ValueError("negative")
        return math.lcm(*ints)

    return _each(one, *numbers)


def EVEN(number):
    return _vec(lambda x: np.sign(x) * 2 * np.ceil(_snap(np.abs(x) / 2)), number)


def ODD(number):
    def core(x):
        a = np.ceil(_snap(np.abs(x)))
        a = np.where(a % 2 == 0, a + 1, a)
        return np.sign(x) * a + np.where(x == 0, 1.0, 0.0)

    return _vec(core, number)


def RAND(like=None):
    rng = np.random.default_rng()
    if like is None:
        return float(rng.random())
    index, cols = _cols((like,))
    return _done(pd.Series(rng.random(len(cols[0])), index=cols[0].index), index)


def RANDBETWEEN(bottom, top, like=None):
    rng = np.random.default_rng()
    args = (bottom, top) if like is None else (bottom, top, like)
    index, cols = _cols(args)
    lo = np.ceil(_f64(cols[0]))
    hi = np.floor(_f64(cols[1]))
    if np.any(lo > hi):
        raise ValueError("bottom is larger than top")
    out = np.floor(rng.random(len(lo)) * (hi - lo + 1)) + lo
    return _done(pd.Series(out, index=cols[0].index), index)


def SUM(*numbers):
    return float(_flat(numbers).sum())


def PRODUCT(*numbers):
    v = _flat(numbers)
    return float(v.prod()) if len(v) else 0.0


def SUMSQ(*numbers):
    return float((_flat(numbers) ** 2).sum())


def SUMPRODUCT(*arrays):
    index, cols = _cols(arrays)
    if index is None:
        return float(np.prod([np.nan_to_num(_f64(c)) for c in cols]))
    return float(np.prod([np.nan_to_num(_f64(c)) for c in cols], axis=0).sum())


def _bit_args(n):
    k = int(_num1(n))
    if k < 0 or k >= 2 ** 48 or float(_num1(n)) != k:
        raise ValueError("range")
    return k


def BITAND(number1, number2):
    return _each(lambda a, b: _bit_args(a) & _bit_args(b), number1, number2)


def BITOR(number1, number2):
    return _each(lambda a, b: _bit_args(a) | _bit_args(b), number1, number2)


def BITXOR(number1, number2):
    return _each(lambda a, b: _bit_args(a) ^ _bit_args(b), number1, number2)


def _shifted(n, amount):
    k, sh = _bit_args(n), int(_num1(amount))
    if k == 0:
        return 0
    if abs(sh) > 53:
        raise ValueError("shift")
    if sh >= 49:
        return 0
    out = k << sh if sh >= 0 else k >> -sh
    if out >= 2 ** 48:
        raise ValueError("range")
    return out


def BITLSHIFT(number, shift_amount):
    return _each(lambda n, s: _shifted(n, s), number, shift_amount)


def BITRSHIFT(number, shift_amount):
    return _each(lambda n, s: _shifted(n, -int(_num1(s))), number, shift_amount)


def _from_base(text, base, bits):
    s = _txt(text)
    if s == "":
        return 0
    if len(s) > 10 or not re.fullmatch("[01]+" if base == 2 else "[0-9A-Fa-f]+", s):
        raise ValueError("digits")
    v = int(s, base)
    return v - 2 ** bits if len(s) == 10 and v >= 2 ** (bits - 1) else v


def _to_base(number, places, base, bits):
    v = int(math.floor(_num1(number)))
    if not -2 ** (bits - 1) <= v < 2 ** (bits - 1):
        raise ValueError("range")
    if v < 0:
        v += 2 ** bits
        places = None
    s = format(v, "b" if base == 2 else "X")
    if places is not None:
        p = int(_num1(places))
        if p < len(s) or p > 10 or p < 1:
            raise ValueError("places")
        s = s.zfill(p)
    return s


def BIN2DEC(number):
    return _each(lambda t: _from_base(t, 2, 10), number)


def HEX2DEC(number):
    return _each(lambda t: _from_base(t, 16, 40), number)


def DEC2BIN(number, places=None):
    return _each(lambda n: _to_base(n, places, 2, 10), number)


def DEC2HEX(number, places=None):
    return _each(lambda n: _to_base(n, places, 16, 40), number)


def DELTA(number1, number2=0):
    return _each(lambda a, b: int(_num1(a) == _num1(b)), number1, number2)


def _convert_units():
    prefixes = {"Y": 1e24, "Z": 1e21, "E": 1e18, "P": 1e15, "T": 1e12, "G": 1e9, "M": 1e6, "k": 1e3, "h": 1e2, "da": 1e1, "e": 1e1, "d": 1e-1, "c": 1e-2, "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15, "a": 1e-18, "z": 1e-21, "y": 1e-24}
    metric = {"g", "m", "sec", "s", "Pa", "p", "N", "J", "W", "w", "T", "l", "L", "lt", "bit", "byte", "ga", "e", "eV", "ev", "c", "cal", "Wh", "wh", "mi_none"}
    units = {
        "mass": {"g": 1.0, "sg": 14593.9029372064, "lbm": 453.59237, "u": 1.660538782e-24, "ozm": 28.349523125, "grain": 0.06479891, "cwt": 45359.237, "shweight": 45359.237, "uk_cwt": 50802.34544, "stone": 6350.29318, "ton": 907184.74, "uk_ton": 1016046.9088},
        "distance": {"m": 1.0, "mi": 1609.344, "Nmi": 1852.0, "in": 0.0254, "ft": 0.3048, "yd": 0.9144, "ang": 1e-10, "ly": 9.4607304725808e15, "parsec": 3.08567758128155e16, "pc": 3.08567758128155e16, "survey_mi": 1609.3472186944},
        "time": {"yr": 31557600.0, "day": 86400.0, "d": 86400.0, "hr": 3600.0, "mn": 60.0, "min": 60.0, "sec": 1.0, "s": 1.0},
        "pressure": {"Pa": 1.0, "p": 1.0, "atm": 101325.0, "at": 101325.0, "mmHg": 133.322, "psi": 6894.757293168, "Torr": 133.322368421053},
        "force": {"N": 1.0, "dyn": 1e-5, "dy": 1e-5, "lbf": 4.4482216152605, "pond": 0.00980665},
        "energy": {"J": 1.0, "e": 1e-7, "c": 4.184, "cal": 4.1868, "eV": 1.60217646e-19, "ev": 1.60217646e-19, "HPh": 2684519.53769617, "hh": 2684519.53769617, "Wh": 3600.0, "wh": 3600.0, "flb": 1.3558179483314, "BTU": 1055.05585262, "btu": 1055.05585262},
        "power": {"W": 1.0, "w": 1.0, "HP": 745.699871582270, "h": 745.699871582270, "PS": 735.49875},
        "magnetism": {"T": 1.0, "ga": 1e-4},
        "volume": {"tsp": 4.92892159375e-6, "tspm": 5e-6, "tbs": 1.478676478125e-5, "oz": 2.95735295625e-5, "cup": 2.365882365e-4, "pt": 4.73176473e-4, "us_pt": 4.73176473e-4, "uk_pt": 5.6826125e-4, "qt": 9.46352946e-4, "uk_qt": 1.1365225e-3, "gal": 3.785411784e-3, "uk_gal": 4.54609e-3, "l": 1e-3, "L": 1e-3, "lt": 1e-3, "ang3": 1e-30, "barrel": 0.158987294928, "bushel": 0.03523907016688, "ft3": 0.028316846592, "in3": 1.6387064e-5, "ly3": 8.46786664623715e47, "m3": 1.0, "mi3": 4168181825.440579584, "yd3": 0.764554857984, "Nmi3": 6352182208.0, "regton": 2.8316846592, "GRT": 2.8316846592},
        "area": {"uk_acre": 4046.8564224, "us_acre": 4046.87260987425, "ang2": 1e-20, "ar": 100.0, "ft2": 0.09290304, "ha": 10000.0, "in2": 0.00064516, "ly2": 8.95054210748189e31, "m2": 1.0, "mi2": 2589988.110336, "Nmi2": 3429904.0, "yd2": 0.83612736},
        "information": {"bit": 1.0, "byte": 8.0},
        "speed": {"admkn": 0.514773333333333, "kn": 0.514444444444444, "m/h": 1 / 3600, "m/s": 1.0, "mph": 0.44704},
    }
    return prefixes, metric, units


def _unit_lookup(name):
    prefixes, metric, units = _convert_units()
    for cat, table in units.items():
        if name in table:
            return cat, table[name]
    powers = {"m2": 2, "m3": 3}
    for cat, table in units.items():
        for pre in sorted(prefixes, key=len, reverse=True):
            base = name[len(pre):]
            if name.startswith(pre) and base in table and (base in metric or base in powers):
                return cat, table[base] * prefixes[pre] ** powers.get(base, 1)
    raise ValueError("unit")


def CONVERT(number, from_unit, to_unit):
    temp = {"C": "C", "cel": "C", "F": "F", "fah": "F", "K": "K", "kel": "K", "Rank": "Rank", "Reau": "Reau"}

    def one(x, a, b):
        a, b, v = str(a), str(b), _num1(x)
        if a in temp and b in temp:
            kelvin = {"C": lambda t: t + 273.15, "F": lambda t: (t - 32) * 5 / 9 + 273.15, "K": lambda t: t, "Rank": lambda t: t * 5 / 9, "Reau": lambda t: t * 5 / 4 + 273.15}[temp[a]](v)
            return {"C": lambda k: k - 273.15, "F": lambda k: (k - 273.15) * 9 / 5 + 32, "K": lambda k: k, "Rank": lambda k: k * 9 / 5, "Reau": lambda k: (k - 273.15) * 4 / 5}[temp[b]](kelvin)
        cat_a, fa = _unit_lookup(a)
        cat_b, fb = _unit_lookup(b)
        if cat_a != cat_b:
            raise ValueError("incompatible units")
        return v * fa / fb

    return _each(one, number, from_unit, to_unit)



def _sp():
    from scipy import special, stats

    return special, stats


def _range_f64(s):
    kind = s.dtype.kind if isinstance(s.dtype, np.dtype) else "O"
    if kind == "M":
        return s.map(lambda t: np.nan if pd.isna(t) else _serial(t)).to_numpy(dtype="float64")
    if kind in "biuf":
        return _f64(s)
    if kind == "m":
        return np.full(len(s), np.nan)
    if isinstance(s.dtype, pd.api.extensions.ExtensionDtype) and not pd.api.types.is_string_dtype(s.dtype):
        return _f64(s)
    return np.fromiter((float(v) if isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, (bool, np.bool_)) else (_serial(v) if isinstance(v, pd.Timestamp) else np.nan) for v in s), dtype="float64", count=len(s))


def _values(args, text_zero=False):
    parts = []
    for a in args:
        if isinstance(a, (pd.Series, pd.Index, list, tuple, np.ndarray)):
            s = a if isinstance(a, pd.Series) else pd.Series(list(a))
            if text_zero:
                parts.append(np.array([_a_value(v) for v in s if not _blank(v)], dtype="float64"))
            else:
                parts.append(_range_f64(s))
        else:
            parts.append(np.array([_a_value(a, True)], dtype="float64") if text_zero else _f64(pd.Series([a])))
    v = np.concatenate(parts) if parts else np.array([], dtype="float64")
    return v[~np.isnan(v)]


def _a_value(v, direct=False):
    if isinstance(v, (bool, np.bool_)):
        return float(v)
    if isinstance(v, str):
        if direct:
            return _strict_number(v)
        return 0.0
    if isinstance(v, pd.Timestamp):
        return _serial(v)
    return float(v)


def AVERAGE(*numbers):
    v = _values(numbers)
    return float(v.mean()) if len(v) else np.nan


def AVERAGEA(*values):
    v = _values(values, True)
    return float(v.mean()) if len(v) else np.nan


def MEDIAN(*numbers):
    v = _values(numbers)
    return float(np.median(v)) if len(v) else np.nan


def MODE_SNGL(*numbers):
    v = _values(numbers)
    if not len(v):
        return np.nan
    seen = {}
    for x in v:
        seen[x] = seen.get(x, 0) + 1
    top = max(seen.values())
    if top < 2:
        return np.nan
    return float(next(x for x in v if seen[x] == top))


def _extreme(args, func, text_zero):
    dates = [a for a in args if isinstance(a, pd.Series) and isinstance(a.dtype, np.dtype) and a.dtype.kind == "M"]
    if dates and len(dates) == len(args):
        stamps = pd.concat(dates).dropna()
        return (stamps.min() if func is np.min else stamps.max()) if len(stamps) else pd.NaT
    v = _values(args, text_zero)
    return float(func(v)) if len(v) else 0.0


def MIN(*numbers):
    return _extreme(numbers, np.min, False)


def MAX(*numbers):
    return _extreme(numbers, np.max, False)


def MINA(*values):
    return _extreme(values, np.min, True)


def MAXA(*values):
    return _extreme(values, np.max, True)


def COUNT(*values):
    return float(len(_values(values)))


def COUNTA(*values):
    total = 0
    for a in values:
        if _is_seq(a):
            total += sum(1 for v in (a if isinstance(a, pd.Series) else pd.Series(list(a))) if not _blank(v))
        else:
            total += 0 if _blank(a) else 1
    return float(total)


def COUNTBLANK(range):
    s = range if isinstance(range, pd.Series) else pd.Series(list(range) if _is_seq(range) else [range])
    return float(sum(1 for v in s if _blank(v) or (isinstance(v, str) and v == "")))


def _spread(numbers, ddof, minimum):
    v = _values(numbers)
    return v, len(v) >= minimum


def STDEV_S(*numbers):
    v, ok = _spread(numbers, 1, 2)
    return float(v.std(ddof=1)) if ok else np.nan


def STDEV_P(*numbers):
    v, ok = _spread(numbers, 0, 1)
    return float(v.std(ddof=0)) if ok else np.nan


def VAR_S(*numbers):
    v, ok = _spread(numbers, 1, 2)
    return float(v.var(ddof=1)) if ok else np.nan


def VAR_P(*numbers):
    v, ok = _spread(numbers, 0, 1)
    return float(v.var(ddof=0)) if ok else np.nan


def SKEW(*numbers):
    v = _values(numbers)
    n = len(v)
    sd = v.std(ddof=1) if n > 1 else 0
    if n < 3 or sd == 0:
        return np.nan
    return float(n / ((n - 1) * (n - 2)) * (((v - v.mean()) / sd) ** 3).sum())


def SKEW_P(*numbers):
    v = _values(numbers)
    sd = v.std(ddof=0) if len(v) else 0
    if len(v) < 1 or sd == 0:
        return np.nan
    return float((((v - v.mean()) / sd) ** 3).mean())


def KURT(*numbers):
    v = _values(numbers)
    n = len(v)
    sd = v.std(ddof=1) if n > 1 else 0
    if n < 4 or sd == 0:
        return np.nan
    return float(n * (n + 1) / ((n - 1) * (n - 2) * (n - 3)) * (((v - v.mean()) / sd) ** 4).sum() - 3 * (n - 1) ** 2 / ((n - 2) * (n - 3)))


def DEVSQ(*numbers):
    v = _values(numbers)
    return float(((v - v.mean()) ** 2).sum()) if len(v) else np.nan


def AVEDEV(*numbers):
    v = _values(numbers)
    return float(np.abs(v - v.mean()).mean()) if len(v) else np.nan


def GEOMEAN(*numbers):
    v = _values(numbers)
    return float(np.exp(np.log(v).mean())) if len(v) and (v > 0).all() else np.nan


def HARMEAN(*numbers):
    v = _values(numbers)
    return float(len(v) / (1 / v).sum()) if len(v) and (v > 0).all() else np.nan


def TRIMMEAN(array, percent):
    v = np.sort(_values((array,)))
    p = float(percent)
    if not len(v) or p < 0 or p >= 1:
        return np.nan
    cut = int(math.floor(len(v) * p + 1e-12)) // 2
    return float(v[cut:len(v) - cut].mean())


def _interp_percentile(v, k, exclusive):
    n = len(v)
    if n == 0 or math.isnan(k):
        return np.nan
    if exclusive:
        if k < 1 / (n + 1) or k > n / (n + 1):
            return np.nan
        rank = k * (n + 1)
        lo = int(math.floor(rank + 1e-12))
        frac = rank - lo
        if lo >= n:
            return float(v[n - 1])
        return float(v[lo - 1] + frac * (v[lo] - v[lo - 1]))
    if k < 0 or k > 1:
        return np.nan
    rank = k * (n - 1)
    lo = int(math.floor(rank + 1e-12))
    frac = rank - lo
    if lo >= n - 1:
        return float(v[n - 1])
    return float(v[lo] + frac * (v[lo + 1] - v[lo]))


def _percentile(array, k, exclusive):
    v = np.sort(_values((array,)))
    return _each(lambda kk: _interp_percentile(v, _num1(kk), exclusive), k)


def PERCENTILE_INC(array, k):
    return _percentile(array, k, False)


def PERCENTILE_EXC(array, k):
    return _percentile(array, k, True)


def QUARTILE_INC(array, quart):
    v = np.sort(_values((array,)))

    def one(q):
        k = int(_num1(q))
        if k < 0 or k > 4:
            return np.nan
        return _interp_percentile(v, k / 4, False)

    return _each(one, quart)


def QUARTILE_EXC(array, quart):
    v = np.sort(_values((array,)))

    def one(q):
        k = int(_num1(q))
        if k < 1 or k > 3:
            return np.nan
        return _interp_percentile(v, k / 4, True)

    return _each(one, quart)


def _percent_rank(array, x, significance, exclusive):
    v = np.sort(_values((array,)))
    n = len(v)
    digits = int(significance)
    if digits < 1:
        raise ValueError("significance")

    def one(xx):
        t = _num1(xx)
        if n == 0 or t < v[0] or t > v[-1]:
            raise ValueError("range")
        if (v == t).any():
            if n == 1:
                return 1.0
            position = float((v < t).sum())
        else:
            lo, hi = v[v < t].max(), v[v > t].min()
            last_lo = float((v <= lo).sum() - 1)
            first_hi = float((v < hi).sum())
            position = last_lo + (t - lo) / (hi - lo) * (first_hi - last_lo)
        r = (position + 1) / (n + 1) if exclusive else position / (n - 1)
        scale = 10.0 ** digits
        return float(np.floor(_snap(np.array(r * scale))) / scale)

    return _each(one, x)


def PERCENTRANK_INC(array, x, significance=3):
    return _percent_rank(array, x, significance, False)


def PERCENTRANK_EXC(array, x, significance=3):
    return _percent_rank(array, x, significance, True)


def _rank(number, ref, order, average):
    v = _values((ref,))
    ascending = bool(_num1(order))

    def one(x):
        t = _num1(x)
        ties = int((v == t).sum())
        if ties == 0:
            raise ValueError("not found")
        first = int((v < t).sum() if ascending else (v > t).sum()) + 1
        return first + (ties - 1) / 2 if average else first

    return _each(one, number)


def RANK_EQ(number, ref, order=0):
    return _rank(number, ref, order, False)


def RANK_AVG(number, ref, order=0):
    return _rank(number, ref, order, True)


def _kth(array, k, largest):
    v = np.sort(_values((array,)))

    def one(kk):
        kv = _num1(kk)
        if kv < 1:
            raise ValueError("k")
        pos = int(math.ceil(kv - 1e-12)) if largest else int(math.floor(kv + 1e-12))
        if pos > len(v):
            raise ValueError("k")
        return float(v[-pos] if largest else v[pos - 1])

    return _each(one, k)


def LARGE(array, k):
    return _kth(array, k, True)


def SMALL(array, k):
    return _kth(array, k, False)


def STANDARDIZE(x, mean, standard_dev):
    return _vec(lambda a, m, s: np.where(s > 0, (a - m) / np.where(s > 0, s, 1.0), np.nan), x, mean, standard_dev)


def _pairs(array1, array2):
    a = array1 if isinstance(array1, pd.Series) else pd.Series(list(array1))
    b = array2 if isinstance(array2, pd.Series) else pd.Series(list(array2))
    if len(a) != len(b):
        raise ValueError("arrays differ in size")
    x, y = _range_f64(a), _range_f64(b)
    keep = ~(np.isnan(x) | np.isnan(y))
    return x[keep], y[keep]


def CORREL(array1, array2):
    x, y = _pairs(array1, array2)
    if len(x) < 2 or x.std() == 0 or y.std() == 0:
        return np.nan
    return float(np.corrcoef(x, y)[0, 1])


def PEARSON(array1, array2):
    return CORREL(array1, array2)


def COVARIANCE_P(array1, array2):
    x, y = _pairs(array1, array2)
    return float(((x - x.mean()) * (y - y.mean())).mean()) if len(x) else np.nan


def COVARIANCE_S(array1, array2):
    x, y = _pairs(array1, array2)
    return float(((x - x.mean()) * (y - y.mean())).sum() / (len(x) - 1)) if len(x) > 1 else np.nan


def _line(known_y, known_x):
    x, y = _pairs(known_x, known_y)
    if len(x) < 2:
        raise ValueError("too few points")
    sxx = ((x - x.mean()) ** 2).sum()
    if sxx == 0:
        raise ValueError("constant x")
    slope = ((x - x.mean()) * (y - y.mean())).sum() / sxx
    return slope, y.mean() - slope * x.mean(), x, y


def SLOPE(known_y_s, known_x_s):
    try:
        return float(_line(known_y_s, known_x_s)[0])
    except ValueError:
        return np.nan


def INTERCEPT(known_y_s, known_x_s):
    try:
        return float(_line(known_y_s, known_x_s)[1])
    except ValueError:
        return np.nan


def RSQ(known_y_s, known_x_s):
    r = CORREL(known_y_s, known_x_s)
    return r * r


def STEYX(known_y_s, known_x_s):
    try:
        slope, intercept, x, y = _line(known_y_s, known_x_s)
    except ValueError:
        return np.nan
    if len(x) < 3:
        return np.nan
    return float(np.sqrt(((y - (intercept + slope * x)) ** 2).sum() / (len(x) - 2)))


def FORECAST_LINEAR(x, known_y_s, known_x_s):
    try:
        slope, intercept, _, _ = _line(known_y_s, known_x_s)
    except ValueError:
        return np.nan
    return _vec(lambda t: intercept + slope * t, x)


def TREND(known_y_s, known_x_s=None, new_x_s=None, const=True):
    y = known_y_s if isinstance(known_y_s, pd.Series) else pd.Series(list(known_y_s))
    x = pd.Series(np.arange(1, len(y) + 1), index=y.index) if known_x_s is None else (known_x_s if isinstance(known_x_s, pd.Series) else pd.Series(list(known_x_s)))
    target = x if new_x_s is None else (new_x_s if isinstance(new_x_s, pd.Series) else pd.Series(list(new_x_s) if _is_seq(new_x_s) else [new_x_s]))
    kx, ky = _pairs(y, x)[1], _pairs(y, x)[0]
    if len(kx) < 2:
        return pd.Series(np.nan, index=target.index)
    if bool(_truth(pd.Series([const]))[0]):
        sxx = ((kx - kx.mean()) ** 2).sum()
        if sxx == 0:
            return pd.Series(np.nan, index=target.index)
        slope = ((kx - kx.mean()) * (ky - ky.mean())).sum() / sxx
        intercept = ky.mean() - slope * kx.mean()
    else:
        slope, intercept = (kx * ky).sum() / (kx * kx).sum(), 0.0
    return pd.Series(intercept + slope * _f64(target), index=target.index)


def PERMUT(number, number_chosen):
    def one(n, k):
        a, b = int(_num1(n)), int(_num1(k))
        if a < 0 or b < 0 or b > a:
            raise ValueError("range")
        return float(math.perm(a, b))

    return _each(one, number, number_chosen)


def FREQUENCY(data_array, bins_array):
    v = _values((data_array,))
    bins = np.sort(_values((bins_array,)))
    counts, previous = [], -np.inf
    for b in bins:
        counts.append(float(((v > previous) & (v <= b)).sum()))
        previous = b
    counts.append(float((v > previous).sum()))
    return pd.Series(counts)



def _crit_parts(criterion):
    if isinstance(criterion, str):
        m = re.fullmatch(r"(<=|>=|<>|<|>|=)?(.*)", criterion, re.S)
        return m.group(1) or "=", m.group(2)
    return "=", criterion


def _number_text(text):
    try:
        return _strict_number(text)
    except ValueError:
        return None


def _compare(op, a, b):
    return {"=": a == b, "<>": a != b, "<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]


def _match(series, criterion):
    op, val = _crit_parts(criterion)
    return _match_op(series, op, val)


def _match_op(series, op, val):
    if isinstance(val, str) and val.upper() in ("TRUE", "FALSE"):
        val = val.upper() == "TRUE"
    n = len(series)
    if isinstance(val, str) and val == "":
        blank = np.fromiter((_blank(v) or (isinstance(v, str) and v == "") for v in series), dtype=bool, count=n)
        return ~blank if op == "<>" else blank if op == "=" else np.zeros(n, dtype=bool)
    if op == "<>":
        return ~_match_op(series, "=", val) if not _numeric_criterion(val) else ~_numeric_cells(series, "=", val, False)
    kind = series.dtype.kind if isinstance(series.dtype, np.dtype) else "O"
    if kind == "M":
        stamp = None
        try:
            stamp = _ts(val) if isinstance(val, str) and _number_text(val) is None else None
        except (ValueError, TypeError):
            stamp = None
        if stamp is not None:
            return np.asarray(_compare(op, series.to_numpy(), np.datetime64(stamp)) & ~series.isna().to_numpy())
        num = _number_text(val) if isinstance(val, str) else (_serial(val) if isinstance(val, pd.Timestamp) else float(val))
        serials = series.map(lambda t: np.nan if pd.isna(t) else _serial(t)).to_numpy(dtype="float64")
        return np.asarray(_compare(op, serials, num) & ~np.isnan(serials)) if num is not None else np.zeros(n, dtype=bool)
    if isinstance(val, (bool, np.bool_)):
        return np.fromiter((isinstance(v, (bool, np.bool_)) and _compare(op, bool(v), bool(val)) for v in series), dtype=bool, count=n)
    if isinstance(val, pd.Timestamp):
        val = _serial(val)
    if _numeric_criterion(val):
        return _numeric_cells(series, op, val, True)
    if op == "=":
        rx = _wildcard(val)
        return np.fromiter((isinstance(v, str) and rx.fullmatch(v) is not None for v in series), dtype=bool, count=n)
    text = val.lower()
    return np.fromiter((isinstance(v, str) and bool(_compare(op, v.lower(), text)) for v in series), dtype=bool, count=n)


def _numeric_criterion(val):
    return (_number_text(val) is not None) if isinstance(val, str) else True


def _numeric_cells(series, op, val, text_numbers):
    num = _number_text(val) if isinstance(val, str) else float(val)

    def numeric(v):
        if isinstance(v, (bool, np.bool_)) or _blank(v):
            return None
        if isinstance(v, str):
            return _number_text(v) if (op == "=" and text_numbers) else None
        if isinstance(v, pd.Timestamp):
            return _serial(v)
        return float(v)

    return np.fromiter((x is not None and bool(_compare(op, x, num)) for x in (numeric(v) for v in series)), dtype=bool, count=len(series))


def _hkey(v):
    return "nan" if _blank(v) else (type(v).__name__, v)


def _criteria_reduce(how, target, mask):
    if how == "count":
        return float(mask.sum())
    v = target[mask]
    v = v[~np.isnan(v)]
    if how == "sum":
        return float(v.sum())
    if how == "average":
        return float(v.mean()) if len(v) else np.nan
    if how == "max":
        return float(v.max()) if len(v) else 0.0
    return float(v.min()) if len(v) else 0.0


def _ifs(how, target, pairs):
    ranges = [r if isinstance(r, pd.Series) else pd.Series(list(r) if _is_seq(r) else [r]) for r, _ in pairs]
    size = len(ranges[0])
    if any(len(r) != size for r in ranges):
        raise ValueError("the ranges differ in size")
    tvals = None
    if target is not None:
        t = target if isinstance(target, pd.Series) else pd.Series(list(target) if _is_seq(target) else [target])
        if len(t) != size:
            raise ValueError("the ranges differ in size")
        tvals = _range_f64(t)
    index, ccols = _cols(tuple(c for _, c in pairs))
    cache, out = {}, []
    for key in zip(*ccols):
        token = tuple(_hkey(k) for k in key)
        if token not in cache:
            mask = np.logical_and.reduce([_match(r, c) for r, c in zip(ranges, key)])
            cache[token] = _criteria_reduce(how, tvals, mask)
        out.append(cache[token])
    return _done(pd.Series(out, index=ccols[0].index, dtype="float64"), index)


def SUMIF(range, criteria, sum_range=None):
    return _ifs("sum", range if sum_range is None else sum_range, [(range, criteria)])


def COUNTIF(range, criteria):
    return _ifs("count", None, [(range, criteria)])


def AVERAGEIF(range, criteria, average_range=None):
    return _ifs("average", range if average_range is None else average_range, [(range, criteria)])


def _pairs_of(args):
    if len(args) % 2:
        raise ValueError("criteria ranges and criteria come in pairs")
    return [(args[i], args[i + 1]) for i in range(0, len(args), 2)]


def SUMIFS(sum_range, *criteria):
    return _ifs("sum", sum_range, _pairs_of(criteria))


def COUNTIFS(*criteria):
    return _ifs("count", None, _pairs_of(criteria))


def AVERAGEIFS(average_range, *criteria):
    return _ifs("average", average_range, _pairs_of(criteria))


def MAXIFS(max_range, *criteria):
    return _ifs("max", max_range, _pairs_of(criteria))


def MINIFS(min_range, *criteria):
    return _ifs("min", min_range, _pairs_of(criteria))


def SUBTOTAL(function_num, *ref):
    code = int(_num1(function_num)) % 100
    table = {1: AVERAGE, 2: COUNT, 3: COUNTA, 4: MAX, 5: MIN, 6: PRODUCT, 7: STDEV_S, 8: STDEV_P, 9: SUM, 10: VAR_S, 11: VAR_P}
    if code not in table or int(_num1(function_num)) not in list(range(1, 12)) + list(range(101, 112)):
        return np.nan
    return table[code](*ref)


def AGGREGATE(function_num, options, *ref):
    code = int(_num1(function_num))
    simple = {1: AVERAGE, 2: COUNT, 3: COUNTA, 4: MAX, 5: MIN, 6: PRODUCT, 7: STDEV_S, 8: STDEV_P, 9: SUM, 10: VAR_S, 11: VAR_P, 12: MEDIAN, 13: MODE_SNGL}
    if code in simple:
        return simple[code](*ref)
    keyed = {14: LARGE, 15: SMALL, 16: PERCENTILE_INC, 17: QUARTILE_INC, 18: PERCENTILE_EXC, 19: QUARTILE_EXC}
    if code in keyed and len(ref) == 2:
        return keyed[code](ref[0], ref[1])
    return np.nan


def PERCENTOF(subset, total):
    whole = SUM(total)
    return SUM(subset) / whole if whole else np.nan



def _flag(c):
    return c != 0


def _dist(core, *args):
    special, stats = _sp()
    return _vec(lambda *a: core(special, stats, *a), *args)


def NORM_DIST(x, mean, standard_dev, cumulative):
    def core(special, stats, x, m, sd, c):
        sd = np.where(sd > 0, sd, np.nan)
        return np.where(_flag(c), stats.norm.cdf(x, m, sd), stats.norm.pdf(x, m, sd))

    return _dist(core, x, mean, standard_dev, cumulative)


def NORM_INV(probability, mean, standard_dev):
    def core(special, stats, p, m, sd):
        return np.where((p > 0) & (p < 1) & (sd > 0), stats.norm.ppf(p, m, np.where(sd > 0, sd, 1.0)), np.nan)

    return _dist(core, probability, mean, standard_dev)


def NORM_S_DIST(z, cumulative=True):
    def core(special, stats, z, c):
        return np.where(_flag(c), stats.norm.cdf(z), stats.norm.pdf(z))

    return _dist(core, z, cumulative)


def NORM_S_INV(probability):
    def core(special, stats, p):
        return np.where((p > 0) & (p < 1), stats.norm.ppf(p), np.nan)

    return _dist(core, probability)


def GAUSS(z):
    return _dist(lambda special, stats, z: stats.norm.cdf(z) - 0.5, z)


def PHI(x):
    return _dist(lambda special, stats, x: stats.norm.pdf(x), x)


def T_DIST(x, deg_freedom, cumulative):
    def core(special, stats, x, df, c):
        df = np.floor(df)
        df = np.where(df >= 1, df, np.nan)
        return np.where(_flag(c), stats.t.cdf(x, df), stats.t.pdf(x, df))

    return _dist(core, x, deg_freedom, cumulative)


def T_DIST_2T(x, deg_freedom):
    def core(special, stats, x, df):
        df = np.floor(df)
        return np.where((x >= 0) & (df >= 1), 2 * stats.t.sf(x, np.where(df >= 1, df, 1.0)), np.nan)

    return _dist(core, x, deg_freedom)


def T_DIST_RT(x, deg_freedom):
    def core(special, stats, x, df):
        df = np.floor(df)
        return np.where(df >= 1, stats.t.sf(x, np.where(df >= 1, df, 1.0)), np.nan)

    return _dist(core, x, deg_freedom)


def T_INV(probability, deg_freedom):
    def core(special, stats, p, df):
        df = np.floor(df)
        return np.where((p > 0) & (p < 1) & (df >= 1), stats.t.ppf(p, np.where(df >= 1, df, 1.0)), np.nan)

    return _dist(core, probability, deg_freedom)


def T_INV_2T(probability, deg_freedom):
    def core(special, stats, p, df):
        df = np.floor(df)
        return np.where((p > 0) & (p <= 1) & (df >= 1), stats.t.isf(p / 2, np.where(df >= 1, df, 1.0)), np.nan)

    return _dist(core, probability, deg_freedom)


def CHISQ_DIST(x, deg_freedom, cumulative):
    def core(special, stats, x, df, c):
        df = np.floor(df)
        ok = (x >= 0) & (df >= 1)
        df = np.where(ok, df, np.nan)
        return np.where(_flag(c), stats.chi2.cdf(x, df), stats.chi2.pdf(x, df))

    return _dist(core, x, deg_freedom, cumulative)


def CHISQ_DIST_RT(x, deg_freedom):
    def core(special, stats, x, df):
        df = np.floor(df)
        return np.where((x >= 0) & (df >= 1), stats.chi2.sf(x, np.where(df >= 1, df, 1.0)), np.nan)

    return _dist(core, x, deg_freedom)


def CHISQ_INV(probability, deg_freedom):
    def core(special, stats, p, df):
        df = np.floor(df)
        return np.where((p >= 0) & (p < 1) & (df >= 1), stats.chi2.ppf(p, np.where(df >= 1, df, 1.0)), np.nan)

    return _dist(core, probability, deg_freedom)


def CHISQ_INV_RT(probability, deg_freedom):
    def core(special, stats, p, df):
        df = np.floor(df)
        return np.where((p > 0) & (p <= 1) & (df >= 1), stats.chi2.isf(p, np.where(df >= 1, df, 1.0)), np.nan)

    return _dist(core, probability, deg_freedom)


def F_DIST(x, deg_freedom1, deg_freedom2, cumulative):
    def core(special, stats, x, d1, d2, c):
        d1, d2 = np.floor(d1), np.floor(d2)
        ok = (x >= 0) & (d1 >= 1) & (d2 >= 1)
        d1, d2 = np.where(ok, d1, np.nan), np.where(ok, d2, np.nan)
        return np.where(_flag(c), stats.f.cdf(x, d1, d2), stats.f.pdf(x, d1, d2))

    return _dist(core, x, deg_freedom1, deg_freedom2, cumulative)


def F_DIST_RT(x, deg_freedom1, deg_freedom2):
    def core(special, stats, x, d1, d2):
        d1, d2 = np.floor(d1), np.floor(d2)
        ok = (x >= 0) & (d1 >= 1) & (d2 >= 1)
        return np.where(ok, stats.f.sf(x, np.where(ok, d1, 1.0), np.where(ok, d2, 1.0)), np.nan)

    return _dist(core, x, deg_freedom1, deg_freedom2)


def F_INV(probability, deg_freedom1, deg_freedom2):
    def core(special, stats, p, d1, d2):
        d1, d2 = np.floor(d1), np.floor(d2)
        ok = (p >= 0) & (p < 1) & (d1 >= 1) & (d2 >= 1)
        return np.where(ok, stats.f.ppf(p, np.where(ok, d1, 1.0), np.where(ok, d2, 1.0)), np.nan)

    return _dist(core, probability, deg_freedom1, deg_freedom2)


def F_INV_RT(probability, deg_freedom1, deg_freedom2):
    def core(special, stats, p, d1, d2):
        d1, d2 = np.floor(d1), np.floor(d2)
        ok = (p > 0) & (p <= 1) & (d1 >= 1) & (d2 >= 1)
        return np.where(ok, stats.f.isf(p, np.where(ok, d1, 1.0), np.where(ok, d2, 1.0)), np.nan)

    return _dist(core, probability, deg_freedom1, deg_freedom2)


def BINOM_DIST(number_s, trials, probability_s, cumulative):
    def core(special, stats, k, n, p, c):
        k, n = np.floor(k), np.floor(n)
        ok = (k >= 0) & (k <= n) & (p >= 0) & (p <= 1) & (n >= 0)
        k, n, p = np.where(ok, k, 0.0), np.where(ok, n, 1.0), np.where(ok, p, 0.5)
        return np.where(ok, np.where(_flag(c), stats.binom.cdf(k, n, p), stats.binom.pmf(k, n, p)), np.nan)

    return _dist(core, number_s, trials, probability_s, cumulative)


def BINOM_INV(trials, probability_s, alpha):
    def core(special, stats, n, p, a):
        n = np.floor(n)
        ok = (n >= 0) & (p >= 0) & (p <= 1) & (a > 0) & (a < 1)
        return np.where(ok, stats.binom.ppf(np.where(ok, a, 0.5), np.where(ok, n, 1.0), np.where(ok, p, 0.5)), np.nan)

    return _dist(core, trials, probability_s, alpha)


def POISSON_DIST(x, mean, cumulative):
    def core(special, stats, k, m, c):
        k = np.floor(k)
        ok = (k >= 0) & (m >= 0)
        k, m = np.where(ok, k, 0.0), np.where(ok, m, 1.0)
        return np.where(ok, np.where(_flag(c), stats.poisson.cdf(k, m), stats.poisson.pmf(k, m)), np.nan)

    return _dist(core, x, mean, cumulative)


def EXPON_DIST(x, lambda_, cumulative):
    def core(special, stats, x, lam, c):
        ok = (x >= 0) & (lam > 0)
        scale = np.where(ok, 1 / np.where(lam > 0, lam, 1.0), 1.0)
        xx = np.where(ok, x, 0.0)
        return np.where(ok, np.where(_flag(c), stats.expon.cdf(xx, scale=scale), stats.expon.pdf(xx, scale=scale)), np.nan)

    return _dist(core, x, lambda_, cumulative)


def GAMMA_DIST(x, alpha, beta, cumulative):
    def core(special, stats, x, a, b, c):
        ok = (x >= 0) & (a > 0) & (b > 0) & (_flag(c) | (x > 0) | (a > 1))
        xx, aa, bb = np.where(ok, x, 0.5), np.where(ok, a, 1.0), np.where(ok, b, 1.0)
        return np.where(ok, np.where(_flag(c), stats.gamma.cdf(xx, aa, scale=bb), stats.gamma.pdf(xx, aa, scale=bb)), np.nan)

    return _dist(core, x, alpha, beta, cumulative)


def GAMMA_INV(probability, alpha, beta):
    def core(special, stats, p, a, b):
        ok = (p >= 0) & (p < 1) & (a > 0) & (b > 0)
        return np.where(ok, stats.gamma.ppf(p, np.where(ok, a, 1.0), scale=np.where(ok, b, 1.0)), np.nan)

    return _dist(core, probability, alpha, beta)


def GAMMA(x):
    def core(special, stats, x):
        bad = (x <= 0) & (x == np.floor(x))
        return np.where(bad, np.nan, special.gamma(np.where(bad, 1.0, x)))

    return _dist(core, x)


def GAMMALN(x):
    return _dist(lambda special, stats, x: np.where(x > 0, special.gammaln(np.where(x > 0, x, 1.0)), np.nan), x)


def BETA_DIST(x, alpha, beta, cumulative, a=0, b=1):
    def core(special, stats, x, al, be, c, lo, hi):
        ok = (al > 0) & (be > 0) & (x >= lo) & (x <= hi) & (lo < hi)
        t = np.where(ok, (x - lo) / np.where(ok, hi - lo, 1.0), 0.5)
        al, be = np.where(ok, al, 1.0), np.where(ok, be, 1.0)
        value = np.where(_flag(c), stats.beta.cdf(t, al, be), stats.beta.pdf(t, al, be) / np.where(ok, hi - lo, 1.0))
        return np.where(ok, value, np.nan)

    return _dist(core, x, alpha, beta, cumulative, a, b)


def BETA_INV(probability, alpha, beta, a=0, b=1):
    def core(special, stats, p, al, be, lo, hi):
        ok = (p > 0) & (p < 1) & (al > 0) & (be > 0) & (lo < hi)
        t = stats.beta.ppf(np.where(ok, p, 0.5), np.where(ok, al, 1.0), np.where(ok, be, 1.0))
        return np.where(ok, lo + t * (hi - lo), np.nan)

    return _dist(core, probability, alpha, beta, a, b)


def LOGNORM_DIST(x, mean, standard_dev, cumulative):
    def core(special, stats, x, m, sd, c):
        ok = (x > 0) & (sd > 0)
        xx, ss = np.where(ok, x, 1.0), np.where(ok, sd, 1.0)
        return np.where(ok, np.where(_flag(c), stats.lognorm.cdf(xx, ss, scale=np.exp(m)), stats.lognorm.pdf(xx, ss, scale=np.exp(m))), np.nan)

    return _dist(core, x, mean, standard_dev, cumulative)


def LOGNORM_INV(probability, mean, standard_dev):
    def core(special, stats, p, m, sd):
        ok = (p > 0) & (p < 1) & (sd > 0)
        return np.where(ok, stats.lognorm.ppf(np.where(ok, p, 0.5), np.where(ok, sd, 1.0), scale=np.exp(m)), np.nan)

    return _dist(core, probability, mean, standard_dev)


def WEIBULL_DIST(x, alpha, beta, cumulative):
    def core(special, stats, x, a, b, c):
        ok = (x >= 0) & (a > 0) & (b > 0)
        xx, aa, bb = np.where(ok, x, 1.0), np.where(ok, a, 1.0), np.where(ok, b, 1.0)
        density = np.where(xx == 0, 0.0, stats.weibull_min.pdf(xx, aa, scale=bb))
        return np.where(ok, np.where(_flag(c), stats.weibull_min.cdf(xx, aa, scale=bb), density), np.nan)

    return _dist(core, x, alpha, beta, cumulative)


def HYPGEOM_DIST(sample_s, number_sample, population_s, number_pop, cumulative):
    def core(special, stats, k, n, K, M, c):
        k, n, K, M = np.floor(k), np.floor(n), np.floor(K), np.floor(M)
        ok = (n >= 1) & (n <= M) & (K >= 1) & (K <= M) & (k >= np.maximum(0, n - M + K))
        kk, nn, KK, MM = np.where(ok, np.minimum(k, np.minimum(n, K)), 0.0), np.where(ok, n, 1.0), np.where(ok, K, 1.0), np.where(ok, M, 2.0)
        over = k > np.minimum(n, K)
        value = np.where(_flag(c), np.where(over, 1.0, stats.hypergeom.cdf(kk, MM, KK, nn)), np.where(over, 0.0, stats.hypergeom.pmf(kk, MM, KK, nn)))
        return np.where(ok, value, np.nan)

    return _dist(core, sample_s, number_sample, population_s, number_pop, cumulative)


def NEGBINOM_DIST(number_f, number_s, probability_s, cumulative):
    def core(special, stats, f, s, p, c):
        f, s = np.floor(f), np.floor(s)
        ok = (f >= 0) & (s >= 1) & (p > 0) & (p < 1)
        ff, ss, pp = np.where(ok, f, 0.0), np.where(ok, s, 1.0), np.where(ok, p, 0.5)
        return np.where(ok, np.where(_flag(c), stats.nbinom.cdf(ff, ss, pp), stats.nbinom.pmf(ff, ss, pp)), np.nan)

    return _dist(core, number_f, number_s, probability_s, cumulative)


def CONFIDENCE_NORM(alpha, standard_dev, size):
    def core(special, stats, a, sd, n):
        n = np.floor(n)
        ok = (a > 0) & (a < 1) & (sd > 0) & (n >= 1)
        return np.where(ok, stats.norm.isf(np.where(ok, a, 0.5) / 2) * sd / np.sqrt(np.where(ok, n, 1.0)), np.nan)

    return _dist(core, alpha, standard_dev, size)


def CONFIDENCE_T(alpha, standard_dev, size):
    def core(special, stats, a, sd, n):
        n = np.floor(n)
        ok = (a > 0) & (a < 1) & (sd > 0) & (n > 1)
        nn = np.where(ok, n, 2.0)
        return np.where(ok, stats.t.isf(np.where(ok, a, 0.5) / 2, nn - 1) * sd / np.sqrt(nn), np.nan)

    return _dist(core, alpha, standard_dev, size)


def FISHER(x):
    return _vec(lambda x: np.where(np.abs(x) < 1, np.arctanh(np.where(np.abs(x) < 1, x, 0.0)), np.nan), x)


def FISHERINV(y):
    return _vec(np.tanh, y)


def Z_TEST(array, x, sigma=None):
    special, stats = _sp()
    v = _values((array,))
    n = len(v)
    sd = float(v.std(ddof=1)) if sigma is None and n > 1 else (float(sigma) if sigma is not None else np.nan)
    if n == 0 or not sd > 0:
        return np.nan
    return _vec(lambda t: stats.norm.sf((v.mean() - t) / (sd / np.sqrt(n))), x)


def T_TEST(array1, array2, tails, type):
    special, stats = _sp()
    a, b = _values((array1,)), _values((array2,))
    kind, tail = int(_num1(type)), int(_num1(tails))
    if tail not in (1, 2) or kind not in (1, 2, 3):
        return np.nan
    if kind == 1:
        x, y = _pairs(array1, array2)
        if len(x) < 2:
            return np.nan
        p = stats.ttest_rel(x, y).pvalue
    else:
        if len(a) < 2 or len(b) < 2:
            return np.nan
        p = stats.ttest_ind(a, b, equal_var=kind == 2).pvalue
    return float(p / 2 if tail == 1 else p)


def CHISQ_TEST(actual_range, expected_range):
    special, stats = _sp()
    a, e = _f64(pd.Series(list(actual_range)) if not isinstance(actual_range, pd.Series) else actual_range), _f64(pd.Series(list(expected_range)) if not isinstance(expected_range, pd.Series) else expected_range)
    if len(a) != len(e) or len(a) < 2 or (e <= 0).any():
        return np.nan
    return float(stats.chi2.sf(((a - e) ** 2 / e).sum(), len(a) - 1))


def F_TEST(array1, array2):
    special, stats = _sp()
    a, b = _values((array1,)), _values((array2,))
    if len(a) < 2 or len(b) < 2 or a.var(ddof=1) == 0 or b.var(ddof=1) == 0:
        return np.nan
    f = a.var(ddof=1) / b.var(ddof=1)
    p = 2 * min(stats.f.cdf(f, len(a) - 1, len(b) - 1), stats.f.sf(f, len(a) - 1, len(b) - 1))
    return float(min(p, 1.0))



def _annuity(r, n, t):
    growth = (1 + r) ** n
    return np.where(r == 0, n, (1 + r * t) * (growth - 1) / np.where(r == 0, 1.0, r)), growth


def PMT(rate, nper, pv, fv=0, type=0):
    def core(r, n, pv, fv, t):
        ann, growth = _annuity(r, n, t)
        return np.where(r == 0, -(pv + fv) / np.where(n == 0, np.nan, n), -(pv * growth + fv) / np.where(ann == 0, np.nan, ann))

    return _vec(core, rate, nper, pv, fv, type)


def FV(rate, nper, pmt, pv=0, type=0):
    def core(r, n, pmt, pv, t):
        ann, growth = _annuity(r, n, t)
        return -(pv * growth + pmt * ann)

    return _vec(core, rate, nper, pmt, pv, type)


def PV(rate, nper, pmt, fv=0, type=0):
    def core(r, n, pmt, fv, t):
        ann, growth = _annuity(r, n, t)
        return -(fv + pmt * ann) / growth

    return _vec(core, rate, nper, pmt, fv, type)


def NPER(rate, pmt, pv, fv=0, type=0):
    def core(r, pmt, pv, fv, t):
        flat = np.where(pmt == 0, np.nan, -(pv + fv) / np.where(pmt == 0, np.nan, pmt))
        top = pmt * (1 + r * t) - fv * r
        bottom = pmt * (1 + r * t) + pv * r
        grown = np.log(top / np.where(bottom == 0, np.nan, bottom)) / np.log1p(np.where(r == 0, 1.0, r))
        return np.where(r == 0, flat, grown)

    return _vec(core, rate, pmt, pv, fv, type)


def _ipmt_value(r, per, n, pv, fv, t):
    pay = PMT(r, n, pv, fv, t)
    balance = FV(r, per - 1, pay, pv, t) if t == 0 else (0.0 if per == 1 else FV(r, per - 2, pay, pv, 1) - pay)
    return float(balance * r) if t == 0 else float(balance * r) if per > 1 else 0.0


def IPMT(rate, per, nper, pv, fv=0, type=0):
    def one(r, k, n, p, f, t):
        r, k, n, p, f, t = (float(_num1(x)) for x in (r, k, n, p, f, t))
        if k < 1 or k > n or t not in (0, 1):
            raise ValueError("period")
        return _ipmt_value(r, k, n, p, f, int(t))

    return _each(one, rate, per, nper, pv, fv, type)


def PPMT(rate, per, nper, pv, fv=0, type=0):
    def one(r, k, n, p, f, t):
        r, k, n, p, f, t = (float(_num1(x)) for x in (r, k, n, p, f, t))
        if k < 1 or k > n or t not in (0, 1):
            raise ValueError("period")
        return float(PMT(r, n, p, f, t)) - _ipmt_value(r, k, n, p, f, int(t))

    return _each(one, rate, per, nper, pv, fv, type)


def CUMIPMT(rate, nper, pv, start_period, end_period, type):
    def one(r, n, p, a, b, t):
        r, n, p, a, b, t = (float(_num1(x)) for x in (r, n, p, a, b, t))
        if r <= 0 or n <= 0 or p <= 0 or a < 1 or b < a or b > n or t not in (0, 1):
            raise ValueError("arguments")
        return sum(_ipmt_value(r, k, n, p, 0.0, int(t)) for k in range(int(a), int(b) + 1))

    return _each(one, rate, nper, pv, start_period, end_period, type)


def CUMPRINC(rate, nper, pv, start_period, end_period, type):
    def one(r, n, p, a, b, t):
        r, n, p, a, b, t = (float(_num1(x)) for x in (r, n, p, a, b, t))
        if r <= 0 or n <= 0 or p <= 0 or a < 1 or b < a or b > n or t not in (0, 1):
            raise ValueError("arguments")
        pay = float(PMT(r, n, p, 0.0, t))
        return sum(pay - _ipmt_value(r, k, n, p, 0.0, int(t)) for k in range(int(a), int(b) + 1))

    return _each(one, rate, nper, pv, start_period, end_period, type)


def ISPMT(rate, per, nper, pv):
    return _vec(lambda r, k, n, p: p * r * (k / np.where(n == 0, np.nan, n) - 1), rate, per, nper, pv)


def _solve(func, guess, low=-0.999999, high=1e6):
    special, stats = _sp()
    from scipy import optimize

    x = guess
    for _ in range(60):
        step = 1e-6 * max(1.0, abs(x))
        f0 = func(x)
        slope = (func(x + step) - f0) / step
        if not np.isfinite(slope) or slope == 0:
            break
        nxt = x - f0 / slope
        if not np.isfinite(nxt) or nxt <= low:
            break
        if abs(nxt - x) < 1e-13 * max(1.0, abs(x)):
            return float(nxt)
        x = nxt
    grid = np.concatenate([np.linspace(low + 1e-6, 1, 400), np.geomspace(1, high, 200)])
    vals = np.array([func(g) for g in grid])
    for i in range(len(grid) - 1):
        if np.isfinite(vals[i]) and np.isfinite(vals[i + 1]) and vals[i] * vals[i + 1] <= 0:
            return float(optimize.brentq(func, grid[i], grid[i + 1], xtol=1e-14, rtol=1e-14))
    return np.nan


def RATE(nper, pmt, pv, fv=0, type=0, guess=0.1):
    def one(n, pmt, pv, fv, t, g):
        n, pmt, pv, fv, t, g = (float(_num1(x)) for x in (n, pmt, pv, fv, t, g))

        def balance(r):
            r = np.asarray(r)
            ann, growth = _annuity(r, n, t)
            return float(pv * growth + pmt * ann + fv)

        return _solve(balance, g)

    return _each(one, nper, pmt, pv, fv, type, guess)


def NPV(rate, *values):
    v = _values(values)
    return _each(lambda r: float((v / (1 + _num1(r)) ** np.arange(1, len(v) + 1)).sum()), rate)


def IRR(values, guess=0.1):
    v = _values((values,))
    if len(v) < 2 or not ((v > 0).any() and (v < 0).any()):
        return np.nan
    t = np.arange(len(v))
    return _solve(lambda r: float((v / (1 + r) ** t).sum()), float(guess))


def _dated(values, dates):
    v = values if isinstance(values, pd.Series) else pd.Series(list(values))
    d = _dates(dates if isinstance(dates, pd.Series) else pd.Series(list(dates)))
    if len(v) != len(d):
        raise ValueError("values and dates differ in size")
    amounts = _f64(v)
    days = d.map(lambda t: np.nan if pd.isna(t) else _serial(t)).to_numpy(dtype="float64")
    keep = ~(np.isnan(amounts) | np.isnan(days))
    amounts, days = amounts[keep], days[keep]
    return amounts, days - days[0]


def XNPV(rate, values, dates):
    amounts, days = _dated(values, dates)
    return _each(lambda r: float((amounts / (1 + _num1(r)) ** (days / 365)).sum()) if _num1(r) > 0 else np.nan, rate)


def XIRR(values, dates, guess=0.1):
    amounts, days = _dated(values, dates)
    if not ((amounts > 0).any() and (amounts < 0).any()):
        return np.nan
    return _solve(lambda r: float((amounts / (1 + r) ** (days / 365)).sum()), float(guess))


def MIRR(values, finance_rate, reinvest_rate):
    v = _values((values,))
    n = len(v)
    pos, neg = np.where(v > 0, v, 0.0), np.where(v < 0, v, 0.0)
    if n < 2 or not ((v > 0).any() and (v < 0).any()):
        return np.nan
    fr, rr = float(finance_rate), float(reinvest_rate)
    t = np.arange(1, n + 1)
    pv_neg = (neg / (1 + fr) ** t).sum() * (1 + fr)
    fv_pos = (pos / (1 + rr) ** t).sum() * (1 + rr) ** n
    return float((fv_pos / -pv_neg) ** (1 / (n - 1)) - 1)


def FVSCHEDULE(principal, schedule):
    return _vec(lambda p: p * np.prod(1 + _values((schedule,))), principal)


def SLN(cost, salvage, life):
    return _vec(lambda c, s, l: (c - s) / np.where(l == 0, np.nan, l), cost, salvage, life)


def SYD(cost, salvage, life, per):
    return _vec(lambda c, s, l, p: np.where((p >= 1) & (p <= l) & (l > 0), (c - s) * (l - p + 1) * 2 / (l * (l + 1)), np.nan), cost, salvage, life, per)


def DDB(cost, salvage, life, period, factor=2):
    def one(c, s, l, p, f):
        c, s, l, p, f = (float(_num1(x)) for x in (c, s, l, p, f))
        if c < 0 or s < 0 or l <= 0 or p <= 0 or p > l or f <= 0:
            raise ValueError("arguments")
        keep = max(0.0, 1 - f / l)
        before = c * (1 - keep ** (p - 1))
        return min(c * keep ** (p - 1) * (f / l), max(c - s - before, 0.0))

    return _each(one, cost, salvage, life, period, factor)


def DB(cost, salvage, life, period, month=12):
    def one(c, s, l, p, m):
        c, s, l, p, m = (float(_num1(x)) for x in (c, s, l, p, m))
        if c < 0 or s < 0 or l <= 0 or p <= 0 or m < 1 or m > 12 or p > l + (1 if m < 12 else 0) or c == 0 and False:
            raise ValueError("arguments")
        rate = math.floor((1 - (s / c) ** (1 / l)) * 1000 + 0.5) / 1000 if c else 0.0
        total = 0.0
        dep = 0.0
        for k in range(1, int(p) + 1):
            if k == 1:
                dep = c * rate * m / 12
            elif k == int(l) + 1:
                dep = (c - total) * rate * (12 - m) / 12
            else:
                dep = (c - total) * rate
            total += dep
        return dep

    return _each(one, cost, salvage, life, period, month)


def EFFECT(nominal_rate, npery):
    return _vec(lambda r, n: np.where((r > 0) & (np.floor(n) >= 1), (1 + r / np.floor(np.where(n >= 1, n, 1.0))) ** np.floor(np.where(n >= 1, n, 1.0)) - 1, np.nan), nominal_rate, npery)


def NOMINAL(effect_rate, npery):
    return _vec(lambda e, n: np.where((e > 0) & (np.floor(n) >= 1), np.floor(np.where(n >= 1, n, 1.0)) * ((1 + e) ** (1 / np.floor(np.where(n >= 1, n, 1.0))) - 1), np.nan), effect_rate, npery)


def RRI(nper, pv, fv):
    return _vec(lambda n, p, f: np.where((n > 0) & (p != 0), (f / np.where(p == 0, np.nan, p)) ** (1 / np.where(n > 0, n, np.nan)) - 1, np.nan), nper, pv, fv)


def PDURATION(rate, pv, fv):
    return _vec(lambda r, p, f: np.where((r > 0) & (p > 0) & (f > 0), (np.log(np.where(f > 0, f, 1.0)) - np.log(np.where(p > 0, p, 1.0))) / np.log1p(np.where(r > 0, r, 1.0)), np.nan), rate, pv, fv)


def CHOOSE(index_num, *value):
    if not value:
        raise ValueError("CHOOSE needs at least one value")
    index, cols = _cols((index_num,) + value)
    picks = np.floor(_f64(cols[0]))
    out = np.full(len(picks), np.nan, dtype=object)
    for i, k in enumerate(picks):
        if 1 <= k <= len(value):
            out[i] = cols[int(k)].iloc[i]
    return _done(pd.Series(out, index=cols[0].index).infer_objects(), index)


def _lookup_array(array):
    return array if isinstance(array, pd.Series) else pd.Series(list(array) if _is_seq(array) else [array])


def _comparable(v):
    if isinstance(v, str):
        return (1, v.lower())
    if isinstance(v, (bool, np.bool_)):
        return (2, bool(v))
    if isinstance(v, pd.Timestamp):
        return (0, _serial(v))
    return (0, float(v))


def MATCH(lookup_value, lookup_array, match_type=1):
    arr = list(_lookup_array(lookup_array))
    kind = int(np.sign(_num1(match_type)))

    def one(x):
        key = _comparable(x)
        if kind == 0:
            if isinstance(x, str):
                rx = _wildcard(x)
                for i, v in enumerate(arr):
                    if isinstance(v, str) and rx.fullmatch(v):
                        return i + 1
            else:
                for i, v in enumerate(arr):
                    if not _blank(v) and not isinstance(v, str) and _comparable(v) == key:
                        return i + 1
            raise ValueError("not found")
        best = None
        for i, v in enumerate(arr):
            if _blank(v) or _comparable(v)[0] != key[0]:
                continue
            ck = _comparable(v)
            if kind == 1 and ck <= key and (best is None or ck >= _comparable(arr[best])):
                best = i
            if kind == -1 and ck >= key and (best is None or ck <= _comparable(arr[best])):
                best = i
        if best is None:
            raise ValueError("not found")
        return best + 1

    return _each(one, lookup_value)


def XMATCH(lookup_value, lookup_array, match_mode=0, search_mode=1):
    arr = list(_lookup_array(lookup_array))
    mode, search = int(_num1(match_mode)), int(_num1(search_mode))
    order = range(len(arr)) if search in (1, 2) else range(len(arr) - 1, -1, -1)

    def one(x):
        key = _comparable(x)
        best = None
        for i in order:
            v = arr[i]
            if _blank(v):
                continue
            ck = _comparable(v)
            if mode == 2 and isinstance(x, str):
                if isinstance(v, str) and _wildcard(x).fullmatch(v):
                    return i + 1
                continue
            if ck == key:
                return i + 1
            if ck[0] != key[0]:
                continue
            if mode == -1 and ck < key and (best is None or ck > _comparable(arr[best])):
                best = i
            if mode == 1 and ck > key and (best is None or ck < _comparable(arr[best])):
                best = i
        if best is None:
            raise ValueError("not found")
        return best + 1

    return _each(one, lookup_value)


def INDEX(array, row_num, column_num=None):
    arr = _lookup_array(array)

    def one(k):
        pos = int(_num1(k))
        if pos < 1 or pos > len(arr):
            raise ValueError("row")
        return arr.iloc[pos - 1]

    return _each(one, row_num)


def LOOKUP(lookup_value, lookup_vector, result_vector=None):
    keys = list(_lookup_array(lookup_vector))
    results = _lookup_array(lookup_vector if result_vector is None else result_vector)

    def one(x):
        key = _comparable(x)
        best = None
        for i, v in enumerate(keys):
            if _blank(v) or _comparable(v)[0] != key[0]:
                continue
            if _comparable(v) <= key and (best is None or _comparable(v) >= _comparable(keys[best])):
                best = i
        if best is None or best >= len(results):
            raise ValueError("not found")
        return results.iloc[best]

    return _each(one, lookup_value)



def BETADIST(x, alpha, beta, a=0, b=1):
    return BETA_DIST(x, alpha, beta, True, a, b)


def BETAINV(probability, alpha, beta, a=0, b=1):
    return BETA_INV(probability, alpha, beta, a, b)


def BINOMDIST(number_s, trials, probability_s, cumulative):
    return BINOM_DIST(number_s, trials, probability_s, cumulative)


def CHIDIST(x, deg_freedom):
    return CHISQ_DIST_RT(x, deg_freedom)


def CHIINV(probability, deg_freedom):
    return CHISQ_INV_RT(probability, deg_freedom)


def CHITEST(actual_range, expected_range):
    return CHISQ_TEST(actual_range, expected_range)


def CONFIDENCE(alpha, standard_dev, size):
    return CONFIDENCE_NORM(alpha, standard_dev, size)


def COVAR(array1, array2):
    return COVARIANCE_P(array1, array2)


def CRITBINOM(trials, probability_s, alpha):
    return BINOM_INV(trials, probability_s, alpha)


def EXPONDIST(x, lambda_, cumulative):
    return EXPON_DIST(x, lambda_, cumulative)


def FDIST(x, deg_freedom1, deg_freedom2):
    return F_DIST_RT(x, deg_freedom1, deg_freedom2)


def FINV(probability, deg_freedom1, deg_freedom2):
    return F_INV_RT(probability, deg_freedom1, deg_freedom2)


def FORECAST(x, known_y_s, known_x_s):
    return FORECAST_LINEAR(x, known_y_s, known_x_s)


def FTEST(array1, array2):
    return F_TEST(array1, array2)


def GAMMADIST(x, alpha, beta, cumulative):
    return GAMMA_DIST(x, alpha, beta, cumulative)


def GAMMAINV(probability, alpha, beta):
    return GAMMA_INV(probability, alpha, beta)


def HYPGEOMDIST(sample_s, number_sample, population_s, number_pop):
    return HYPGEOM_DIST(sample_s, number_sample, population_s, number_pop, False)


def LOGINV(probability, mean, standard_dev):
    return LOGNORM_INV(probability, mean, standard_dev)


def LOGNORMDIST(x, mean, standard_dev):
    return LOGNORM_DIST(x, mean, standard_dev, True)


def MODE(*number):
    return MODE_SNGL(*number)


def NEGBINOMDIST(number_f, number_s, probability_s):
    return NEGBINOM_DIST(number_f, number_s, probability_s, False)


def NORMDIST(x, mean, standard_dev, cumulative):
    return NORM_DIST(x, mean, standard_dev, cumulative)


def NORMINV(probability, mean, standard_dev):
    return NORM_INV(probability, mean, standard_dev)


def NORMSDIST(z):
    return NORM_S_DIST(z, True)


def NORMSINV(probability):
    return NORM_S_INV(probability)


def PERCENTILE(array, k):
    return PERCENTILE_INC(array, k)


def PERCENTRANK(array, x, significance=3):
    return PERCENTRANK_INC(array, x, significance)


def POISSON(x, mean, cumulative):
    return POISSON_DIST(x, mean, cumulative)


def QUARTILE(array, quart):
    return QUARTILE_INC(array, quart)


def RANK(number, ref, order=0):
    return RANK_EQ(number, ref, order)


def STDEV(*number):
    return STDEV_S(*number)


def STDEVP(*number):
    return STDEV_P(*number)


def TDIST(x, deg_freedom, tails):
    return T_DIST_2T(x, deg_freedom) if int(_num1(tails)) == 2 else T_DIST_RT(x, deg_freedom) if int(_num1(tails)) == 1 else np.nan


def TINV(probability, deg_freedom):
    return T_INV_2T(probability, deg_freedom)


def TTEST(array1, array2, tails, type):
    return T_TEST(array1, array2, tails, type)


def VAR(*number):
    return VAR_S(*number)


def VARP(*number):
    return VAR_P(*number)


def WEIBULL(x, alpha, beta, cumulative):
    return WEIBULL_DIST(x, alpha, beta, cumulative)


def ZTEST(array, x, sigma=None):
    return Z_TEST(array, x, sigma)


FUNCTIONS = {n: o for n, o in list(globals().items()) if re.fullmatch(r"[A-Z][A-Z0-9_]*", n) and callable(o)}
DOTTED = {n.replace("_", "."): n for n in FUNCTIONS if "_" in n}


def _code_names(code):
    names = set(code.co_names)
    for const in code.co_consts:
        if hasattr(const, "co_names"):
            names |= _code_names(const)
    return names


def registry():
    scope = globals()
    out = {}

    def collect(fn, seen, order, mods, pkgs):
        names = _code_names(fn.__code__)
        if "scipy" in names:
            pkgs.add("scipy")
        for name in sorted(names):
            target = scope.get(name)
            if callable(target) and getattr(target, "__module__", None) == __name__ and name not in seen:
                seen.add(name)
                collect(target, seen, order, mods, pkgs)
                order.append(target)
            elif hasattr(target, "__name__") and hasattr(target, "__file__") and target.__name__ not in ("numpy", "pandas"):
                mods.add(target.__name__)

    for name, fn in FUNCTIONS.items():
        seen, order, mods, pkgs = {name}, [], set(), set()
        collect(fn, seen, order, mods, pkgs)
        out[name] = (order + [fn], sorted(mods), [], sorted(pkgs))
    return out
