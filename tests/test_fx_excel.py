import json
import math
import warnings
from pathlib import Path

import pandas as pd
import pytest

from snek.expr import translate
from snek.fx import _serial
from snek.runtime import NAMESPACE

FIXTURE = json.loads((Path(__file__).parent / "data" / "excel_fx.json").read_text(encoding="utf-8"))
SKIPPED = FIXTURE["known_differences"]
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
    names = {c[0].split("(")[0] for c in FIXTURE["cases"]}
    from snek.fx import FUNCTIONS

    wanted = {n.replace("_", ".") for n in FUNCTIONS} - {"NOW", "TODAY", "RAND", "RANDBETWEEN", "SUMPRODUCT", "NA", "TRUE", "FALSE", "PI"}
    assert not (wanted - names - {"TEXT"}), sorted(wanted - names)


@pytest.mark.parametrize("formula,kind,expected", CASES, ids=[c[0] for c in CASES])
def test_agrees_with_excel(formula, kind, expected):
    got = snek_value(formula)
    assert got[0] == kind, f"{formula}: Excel gave {kind} {expected!r}, Snek gave {got!r}"
    if kind == "num":
        assert got[1] == pytest.approx(expected, rel=1e-9, abs=1e-9)
    elif kind != "error":
        assert got[1] == expected
