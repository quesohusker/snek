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
    parts = []
    for a in args:
        s = a if isinstance(a, pd.Series) else pd.Series(list(a) if _is_seq(a) else [a])
        parts.append(_f64(s))
    v = np.concatenate(parts) if parts else np.array([], dtype="float64")
    return v[~np.isnan(v)]


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

    def collect(fn, seen, order, mods):
        for name in sorted(_code_names(fn.__code__)):
            target = scope.get(name)
            if callable(target) and getattr(target, "__module__", None) == __name__ and name not in seen:
                seen.add(name)
                collect(target, seen, order, mods)
                order.append(target)
            elif hasattr(target, "__name__") and hasattr(target, "__file__") and target.__name__ not in ("numpy", "pandas"):
                mods.add(target.__name__)

    for name, fn in FUNCTIONS.items():
        seen, order, mods = {name}, [], set()
        collect(fn, seen, order, mods)
        out[name] = (order + [fn], sorted(mods), [], [])
    return out
