import json
import math
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from snek.expr import translate
from snek.fx import _serial
from snek.runtime import NAMESPACE

FIXTURE = json.loads((Path(__file__).parent / "data" / "excel_fx.json").read_text(encoding="utf-8"))
SKIPPED = FIXTURE["known_differences"]
RANGES = json.loads((Path(__file__).parent / "data" / "excel_fx_ranges.json").read_text(encoding="utf-8"))
RANGE_SKIPPED = RANGES["known_differences"]
RANGE_CASES = [c for c in RANGES["cases"] if c[0] not in RANGE_SKIPPED]
SOLVERS = ("XIRR(", "IRR(", "RATE(", "MIRR(")
CASES = [c for c in FIXTURE["cases"] if c[0] not in SKIPPED]


def as_python(formula):
    out, i, inside = [], 0, False
    while i < len(formula):
        ch = formula[i]
        if ch == '"':
            if inside and formula[i + 1:i + 2] == '"':
                out.append('\\"')
                i += 2
                continue
            inside = not inside
        out.append(ch)
        i += 1
    return "".join(out)


def snek_value(formula):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            v = eval(translate(as_python(formula), "df", []), dict(NAMESPACE))
    except Exception:
        return ["error", ""]
    if isinstance(v, pd.Timestamp):
        return ["num", _serial(v)]
    if isinstance(v, pd.Timedelta):
        return ["num", v / pd.Timedelta(days=1)]
    if isinstance(v, bool) or type(v).__name__ == "bool_":
        return ["bool", bool(v)]
    if isinstance(v, str):
        return ["text", v]
    try:
        f = float(v)
    except (TypeError, ValueError):
        return ["other", repr(v)]
    return ["error", ""] if math.isnan(f) else ["num", f]


def test_fixture_is_recent_and_complete():
    assert FIXTURE["excel"].startswith("Microsoft Excel")
    assert len(FIXTURE["cases"]) > 1000
    assert len(RANGES["cases"]) > 1000
    names = set()
    for c in FIXTURE["cases"] + RANGES["cases"]:
        names |= set(re.findall(r"[A-Z][A-Z0-9_.]*(?=\()", c[0]))
    from snek.fx import FUNCTIONS

    wanted = {n.replace("_", ".") for n in FUNCTIONS} - {"NOW", "TODAY", "RAND", "RANDBETWEEN", "SUMPRODUCT", "NA", "TRUE", "FALSE", "PI"}
    assert not (wanted - names), sorted(wanted - names)


@pytest.mark.parametrize("formula,kind,expected", CASES, ids=[c[0] for c in CASES])
def test_agrees_with_excel(formula, kind, expected):
    got = snek_value(formula)
    assert got[0] == kind, f"{formula}: Excel gave {kind} {expected!r}, Snek gave {got!r}"
    if kind == "num":
        assert got[1] == pytest.approx(expected, rel=1e-9, abs=1e-9)
    elif kind != "error":
        assert got[1] == expected


RANGE_REF = re.compile(r"\b([A-Z])(\d+):([A-Z])(\d+)\b")


def column(col, first, last):
    cells = RANGES["data"][col][first - 1:last]
    kinds = {c[0] for c in cells} - {"x"}
    values = [np.nan if c[0] == "x" else pd.Timestamp(c[1]) if c[0] == "d" else c[1] for c in cells]
    if kinds == {"d"}:
        return pd.Series([pd.NaT if isinstance(v, float) else v for v in values], dtype="datetime64[us]")
    return pd.Series(values)


def snek_range_value(formula):
    scope = dict(NAMESPACE)

    def name(m):
        key = f"R_{m.group(1)}_{m.group(2)}_{m.group(4)}"
        scope[key] = column(m.group(1), int(m.group(2)), int(m.group(4)))
        return key

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            v = eval(translate(RANGE_REF.sub(name, formula), "df", []), scope)
    except Exception:
        return ["error", ""]
    if isinstance(v, pd.Series):
        v = v.iloc[0] if len(v) else np.nan
    if isinstance(v, pd.Timestamp):
        return ["num", _serial(v)]
    if isinstance(v, bool) or type(v).__name__ == "bool_":
        return ["bool", bool(v)]
    if isinstance(v, str):
        return ["text", v]
    try:
        f = float(v)
    except (TypeError, ValueError):
        return ["other", repr(v)]
    return ["error", ""] if math.isnan(f) else ["num", f]


@pytest.mark.parametrize("formula,kind,expected", RANGE_CASES, ids=[c[0] for c in RANGE_CASES])
def test_ranges_agree_with_excel(formula, kind, expected):
    got = snek_range_value(formula)
    assert got[0] == kind, f"{formula}: Excel gave {kind} {expected!r}, Snek gave {got!r}"
    if kind == "num":
        tolerance = 1e-7 if formula.startswith(SOLVERS) else 1e-9
        assert got[1] == pytest.approx(expected, rel=tolerance, abs=1e-9)
    elif kind != "error":
        assert got[1] == expected
