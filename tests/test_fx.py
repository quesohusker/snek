import math
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from snek import fx
from snek.codegen import export_script
from snek.engine import Engine
from snek.expr import translate
from snek.fx_docs import DOCS, GROUPS, SKIP
from snek.runtime import HELPERS, NAMESPACE
from tests.test_tools import chain, out, run


def evaluate(text):
    return eval(translate(text, "df", []), dict(NAMESPACE))


def same(got, want):
    if isinstance(want, float):
        return got == pytest.approx(want, rel=1e-9, abs=1e-12)
    return got == want


def test_every_function_is_documented_once():
    names = [d[0].replace(".", "_") for d in DOCS]
    assert len(names) == len(set(names))
    assert set(names) == set(fx.FUNCTIONS)
    assert {d[1] for d in DOCS} <= set(GROUPS)
    assert len(DOCS) == 138


@pytest.mark.parametrize("doc", DOCS, ids=[d[0] for d in DOCS])
def test_documented_example(doc):
    name, _, syntax, description, example, expected, _ = doc
    assert syntax.startswith(name + "(")
    assert description.endswith(".")
    got = evaluate(example)
    if expected == SKIP:
        assert got is not None
        return
    want = eval(expected, {"pd": pd, "np": np})
    assert same(got, want), f"{example} gave {got!r}, expected {want!r}"


def test_dotted_names_and_logical_words_are_rewritten():
    assert translate("CEILING.MATH([a], 5) + NETWORKDAYS.INTL([a], [a], 11)", "df", ["a"]) == "CEILING_MATH(df['a'], 5) + NETWORKDAYS_INTL(df['a'], df['a'], 11)"
    assert translate("IF([a] <> 5, TRUE, FALSE)", "df", ["a"]) == "IF(df['a'] != 5, True, False)"
    assert translate("'TRUE' + [a].str.upper()", "df", ["a"]) == "'TRUE' + df['a'].str.upper()"
    assert translate("TRUE()", "df", []) == "TRUE()"
    assert translate("np.PI(1) + FOO.BAR(2)", "df", []) == "np.PI(1) + FOO.BAR(2)"


def test_row_functions_work_on_columns_and_keep_the_index():
    s = pd.Series([50, 150, np.nan, 200], index=[10, 11, 12, 13])
    r = fx.IF(s > 100, "high", "low")
    assert r.index.tolist() == [10, 11, 12, 13]
    assert r.tolist() == ["low", "high", "low", "high"]
    assert fx.IF(s > 100, 1, 0).dtype == np.int64
    assert fx.ROUND(s / 7, 1).tolist()[:2] == [7.1, 21.4]
    assert math.isnan(fx.ROUND(s, 0)[12])
    assert fx.LEFT(pd.Series(["abcdef", None, "xy"]), pd.Series([2, 2, 5])).tolist()[0] == "ab"
    assert fx.LEFT(pd.Series(["abcdef", None, "xy"]), 2).isna().tolist() == [False, True, False]


def test_blanks_stay_blank_except_where_excel_says_otherwise():
    s = pd.Series(["Ab ", np.nan])
    assert fx.UPPER(s).isna().tolist() == [False, True]
    assert fx.LEN(s).tolist() == [3, 0]
    assert fx.CONCAT(s, "!").tolist() == ["Ab !", "!"]
    assert fx.TEXTJOIN("-", True, s, "x").tolist() == ["Ab -x", "x"]
    assert fx.ISBLANK(s).tolist() == [False, True]
    assert fx.N(s).tolist() == [0, 0]
    assert fx.IFERROR(pd.Series([1.0, np.nan, np.inf]), 0).tolist() == [1.0, 0.0, 0.0]
    assert fx.IFNA(pd.Series([1.0, np.nan, np.inf]), 0).tolist() == [1.0, 0.0, np.inf]
    assert fx.YEAR(pd.Series(["2024-02-29", None])).isna().tolist() == [False, True]


def test_errors_become_blanks():
    assert math.isnan(fx.MID("abc", 0, 2))
    assert math.isnan(fx.FIND("z", "abc"))
    assert math.isnan(fx.SQRT(-4))
    assert math.isnan(fx.MOD(5, 0))
    assert math.isnan(fx.LN(0))
    assert math.isnan(fx.DATEDIF("2020-05-01", "2020-01-01", "D"))
    assert math.isnan(fx.CONVERT(2.5, "ft", "sec"))
    assert math.isnan(fx.DEC2BIN(600))
    assert math.isnan(fx.POWER(0, 0))


def test_wrong_argument_counts_raise():
    with pytest.raises(ValueError):
        fx.IFS(True)
    with pytest.raises(ValueError):
        fx.SWITCH(1)


def test_rounding_follows_excel_on_decimal_ties():
    assert fx.ROUND(2.675, 2) == 2.68
    assert fx.ROUND(1.005, 2) == 1.01
    assert fx.ROUND(-2.5, 0) == -3
    assert fx.ROUND(1.4999999999, 0) == 1
    assert fx.ROUNDDOWN(0.29, 2) == 0.29
    assert fx.ROUNDUP(4.35, 2) == 4.35
    assert fx.MROUND(1.3, 0.2) == 1.4
    assert fx.ROUND(pd.Series([0.5, 1.5, 2.5, -0.5]), 0).tolist() == [1.0, 2.0, 3.0, -1.0]


def test_text_edges():
    assert fx.RIGHT("abc", 0) == ""
    assert fx.RIGHT("abc", 10) == "abc"
    assert fx.PROPER("o'neil mc-donald 76budget") == "O'Neil Mc-Donald 76Budget"
    assert fx.TRIM("  a   b ") == "a b"
    assert fx.SUBSTITUTE("aaa", "a", "b", 2) == "aba"
    assert fx.SEARCH("~?", "what?") == 5
    assert fx.SEARCH("w*t", "what") == 1
    assert fx.REPLACE("abc", 5, 1, "Z") == "abcZ"
    assert fx.TEXTBEFORE("a-b-c", "-", 2) == "a-b"
    assert math.isnan(fx.TEXTBEFORE("a-b-c", "-", 3))
    assert fx.TEXTBEFORE("a-b-c", "-", 3, if_not_found="none") == "none"
    assert fx.TEXTAFTER("a-b-c", "-", 3, match_end=1) == ""
    assert fx.TEXTBEFORE("Red riding hood's red hood", "red", 2, 1) == "Red riding hood's "
    assert fx.REGEXEXTRACT("a1b22", r"\d+", 1) == ["1", "22"]
    assert fx.REGEXEXTRACT("k=v", r"(\w)=(\w)", 2) == ["k", "v"]
    assert fx.REGEXREPLACE("a1b2c3", r"\d", "#", -1) == "a1b2c#"
    assert fx.REGEXTEST("ABC", "abc", 1) == True
    assert fx.REGEXTEST("ABC", "abc") == False
    assert fx.NUMBERVALUE("3.5%") == pytest.approx(0.035)
    assert fx.VALUE("(100)") == -100
    assert fx.VALUE("2020-01-01") == 43831
    assert fx.CODE("é") == 233
    assert fx.CHAR(233) == "é"


@pytest.mark.parametrize("value,fmt,want", [
    (1234.567, "$#,##0.00", "$1,234.57"),
    (0.285, "0.0%", "28.5%"),
    (1234, "00000", "01234"),
    (1234.5, "#,##0", "1,235"),
    (0.5, "#.##", ".5"),
    (1234567, "0.00E+00", "1.23E+06"),
    (0.000123, "0.00E+00", "1.23E-04"),
    (-5, "0.00;(0.00)", "(5.00)"),
    (0, "0;-0;zero", "zero"),
    (42, '0" units"', "42 units"),
    (1234567, "#,##0,", "1,235"),
    (-1234.5, "#,##0.00", "-1,234.50"),
    (-0.5, "0", "-1"),
    (2.5, "0", "3"),
    (1234.5678, "#,##0.0#", "1,234.57"),
    (5, "General", "5"),
    (pd.Timestamp("2024-03-05 14:07:09"), "yyyy-mm-dd", "2024-03-05"),
    (pd.Timestamp("2024-03-05 14:07:09"), "mm/dd/yy", "03/05/24"),
    (pd.Timestamp("2024-03-05 14:07:09"), "mmm d, yyyy", "Mar 5, 2024"),
    (pd.Timestamp("2024-03-05 14:07:09"), "dddd", "Tuesday"),
    (pd.Timestamp("2024-03-05 14:07:09"), "h:mm AM/PM", "2:07 PM"),
    (pd.Timestamp("2024-03-05 14:07:09"), "hh:mm:ss", "14:07:09"),
    (pd.Timestamp("2024-03-05 14:07:09"), "m/d/yyyy h:mm", "3/5/2024 14:07"),
    (45000, "yyyy-mm-dd", "2023-03-15"),
])
def test_text_formats(value, fmt, want):
    assert fx.TEXT(value, fmt) == want


@pytest.mark.parametrize("kind,want", [(1, 5), (2, 4), (3, 3), (11, 4), (12, 3), (13, 2), (14, 1), (15, 7), (16, 6), (17, 5)])
def test_weekday_types(kind, want):
    assert fx.WEEKDAY("2008-02-14", kind) == want


def test_date_functions():
    assert fx.DATE(2008, 1, -15) == pd.Timestamp("2007-12-16")
    assert fx.DATE(108, 1, 2) == pd.Timestamp("2008-01-02")
    assert fx.DATE(2024, 3, 0) == pd.Timestamp("2024-02-29")
    assert fx.EDATE("2011-01-31", 1) == pd.Timestamp("2011-02-28")
    assert fx.EOMONTH("2024-01-31", 1) == pd.Timestamp("2024-02-29")
    assert fx.TIME(27, 0, 0) == pd.Timedelta(hours=3)
    assert fx.DATE(2024, 1, 5) + fx.TIME(9, 30, 0) == pd.Timestamp("2024-01-05 09:30")
    assert [fx.WEEKNUM("2012-03-09", k) for k in (1, 2, 11, 12, 21)] == [10, 11, 11, 11, 10]
    assert fx.ISOWEEKNUM("2021-01-03") == 53
    assert fx.DATEDIF("2001-06-15", "2002-08-15", "YM") == 2
    assert fx.DATEDIF("2001-06-15", "2002-08-10", "YD") == 56
    assert fx.DATEDIF("2001-06-15", "2002-08-15", "MD") == 0
    assert fx.DATEDIF("2020-01-31", "2020-02-29", "M") == 0
    assert [round(fx.YEARFRAC("2012-01-01", "2012-07-30", b), 10) for b in range(5)] == [0.5805555556, 0.5765027322, 0.5861111111, 0.5780821918, 0.5805555556]
    assert fx.DAYS360("2011-01-30", "2011-02-01") == 1
    assert fx.DAYS360("2011-01-31", "2011-03-31", True) == 60
    assert fx.NETWORKDAYS("2012-10-01", "2013-03-01", ["2012-11-22", "2012-12-04", "2013-01-21"]) == 107
    assert fx.NETWORKDAYS("2013-03-01", "2012-10-01") == -110
    assert fx.NETWORKDAYS_INTL("2012-01-02", "2012-01-08", "0000011") == 5
    assert fx.WORKDAY("2008-10-01", 151, ["2008-11-26", "2008-12-04", "2009-01-21"]) == pd.Timestamp("2009-05-05")
    assert fx.WORKDAY("2008-10-04", 1) == pd.Timestamp("2008-10-06")
    assert fx.WORKDAY("2008-10-05", -1) == pd.Timestamp("2008-10-03")
    assert fx.WORKDAY("2008-10-04", 0) == pd.Timestamp("2008-10-04")
    assert fx.YEAR(45000) == 2023
    assert fx.HOUR(pd.Timestamp("2024-01-01 13:45:10")) == 13


def test_date_functions_on_columns():
    d = pd.Series(pd.to_datetime(["2024-02-29", "2023-12-31", None]))
    assert fx.YEAR(d).tolist()[:2] == [2024, 2023]
    assert fx.MONTH(d).isna().tolist() == [False, False, True]
    assert fx.WEEKDAY(d, 2).tolist()[:2] == [4, 7]
    assert fx.EOMONTH(d, 0).dt.day.tolist()[:2] == [29, 31]
    assert fx.NETWORKDAYS(d, "2024-03-31").isna().tolist() == [False, False, True]
    assert fx.WORKDAY(d, 5).isna().tolist() == [False, False, True]
    assert fx.WORKDAY(d, pd.Series([1, -1, 1])).tolist()[:2] == [pd.Timestamp("2024-03-01"), pd.Timestamp("2023-12-29")]


def test_math_functions():
    assert fx.CEILING(-2.5, -2) == -4
    assert fx.CEILING(-2.5, 2) == -2
    assert math.isnan(fx.CEILING(2.5, -1))
    assert fx.FLOOR(-2.5, 2) == -4
    assert fx.CEILING_MATH(-8.1, 2) == -8
    assert fx.FLOOR_MATH(-8.1, 2) == -10
    assert fx.MOD(3, -2) == -1
    assert fx.QUOTIENT(-10, 3) == -3
    assert fx.ATAN2(-1, -1) == pytest.approx(-2.356194490192345)
    assert math.isnan(fx.FACT(171))
    assert fx.FACT(170) == pytest.approx(7.257415615307994e306)
    assert fx.ODD(0) == 1
    assert fx.EVEN(0) == 0
    assert fx.TRUNC(31415.9, -2) == 31400
    assert fx.SUM(pd.Series([5, 15, 30, np.nan]), 2) == 52
    assert fx.SUM(pd.Series([1, 2]), pd.Series([3])) == 6
    assert fx.PRODUCT() == 0
    assert fx.SUMPRODUCT(pd.Series([3, 8, 6, 1, 9]), pd.Series([2, 6, 5, 7, 7])) == 154
    share = pd.Series([1.0, 3.0]) / fx.SUM(pd.Series([1.0, 3.0]))
    assert share.tolist() == [0.25, 0.75]


def test_random_functions():
    col = pd.Series(range(200), index=range(5, 205))
    r = fx.RAND(col)
    assert len(r) == 200 and r.index[0] == 5 and r.between(0, 1).all() and r.nunique() > 150
    d = fx.RANDBETWEEN(1, 6, col)
    assert set(d.unique()) == {1.0, 2.0, 3.0, 4.0, 5.0, 6.0}
    assert 1 <= fx.RANDBETWEEN(1, 6) <= 6
    with pytest.raises(ValueError):
        fx.RANDBETWEEN(6, 1)


def test_engineering_functions():
    assert fx.BIN2DEC("1111111111") == -1
    assert fx.HEX2DEC("FFFFFFFF5B") == -165
    assert fx.DEC2BIN(-100) == "1110011100"
    assert fx.DEC2HEX(-54) == "FFFFFFFFCA"
    assert fx.DEC2HEX(28, 4) == "001C"
    assert math.isnan(fx.DEC2BIN(9, 2))
    assert math.isnan(fx.BITAND(-1, 5))
    assert fx.CONVERT(1.0, "lbm", "kg") == pytest.approx(0.45359237)
    assert fx.CONVERT(100, "C", "K") == pytest.approx(373.15)
    assert fx.CONVERT(1, "m3", "l") == pytest.approx(1000)
    assert fx.CONVERT(1, "kbyte", "bit") == pytest.approx(8000)
    assert fx.CONVERT(fx.CONVERT(100, "ft", "m"), "ft", "m") == pytest.approx(9.290304)


def test_information_functions():
    s = pd.Series([1, "a", True, np.nan, np.inf, pd.Timestamp("2020-01-01")], dtype=object)
    assert fx.ISNUMBER(s).tolist() == [True, False, False, False, False, False]
    assert fx.ISTEXT(s).tolist() == [False, True, False, False, False, False]
    assert fx.ISLOGICAL(s).tolist() == [False, False, True, False, False, False]
    assert fx.ISNONTEXT(s).tolist() == [True, False, True, True, True, True]
    assert fx.ISERROR(s).tolist() == [False, False, False, True, True, False]
    assert fx.TYPE(s).tolist() == [1, 2, 4, 1, 16, 1]
    assert fx.ISEVEN(pd.Series([2, 3, "4", np.nan])).isna().tolist() == [False, False, False, True]
    assert fx.N(pd.Timestamp("2020-01-01")) == 43831


def test_logical_functions_on_columns():
    a = pd.Series([1, 5, 9])
    assert fx.IFS(a > 7, "hi", a > 3, "mid", True, "lo").tolist() == ["lo", "mid", "hi"]
    assert fx.SWITCH(pd.Series(["a", "B", "z"]), "A", 1, "b", 2, 99).tolist() == [1, 2, 99]
    assert fx.SWITCH(pd.Series(["a", "z"]), "a", 1).isna().tolist() == [False, True]
    assert fx.AND(a > 2, a < 8).tolist() == [False, True, False]
    assert fx.OR(a < 2, a > 8).tolist() == [True, False, True]
    assert fx.XOR(a > 2, a > 4, a > 8).tolist() == [False, False, True]
    assert fx.NOT(a > 4).tolist() == [True, False, False]
    assert fx.IF(a > 4, pd.Series(["x", "y", "z"]), "n").tolist() == ["n", "y", "z"]
    assert fx.IF(a > 4, True, False).dtype == bool


def test_formula_tool_uses_spreadsheet_functions():
    data = "name,sales,day\n  Ann Lee ,120.456,2024-03-05\nbob,80,2024-12-31\n,,\n"
    steps = [("formula", {"formulas": [
        {"column": "level", "expression": 'IF([sales] > 100, "high", "low")', "dtype": ""},
        {"column": "tidy", "expression": "PROPER(TRIM([name]))", "dtype": ""},
        {"column": "rounded", "expression": "ROUND([sales], 1)", "dtype": ""},
        {"column": "label", "expression": 'TEXT([day], "mmm d, yyyy")', "dtype": ""},
        {"column": "share", "expression": "[sales] / SUM([sales])", "dtype": ""},
        {"column": "capped", "expression": "CEILING.MATH([sales], 10)", "dtype": ""},
        {"column": "safe", "expression": "IFERROR([sales] / (([sales] > 100) * 1), 0)", "dtype": ""},
    ]})]
    ev = run(chain(*steps, data=data))
    df = out(ev, 2)
    assert df["level"].tolist() == ["high", "low", "low"]
    assert df["tidy"].tolist()[:2] == ["Ann Lee", "Bob"]
    assert df["rounded"].tolist()[:2] == [120.5, 80.0]
    assert df["label"].tolist()[:2] == ["Mar 5, 2024", "Dec 31, 2024"]
    assert df["share"].tolist()[:2] == pytest.approx([120.456 / 200.456, 80 / 200.456])
    assert df["capped"].tolist()[:2] == [130.0, 80.0]
    assert df["safe"].tolist() == [120.456, 0.0, 0.0]


def test_filter_tool_uses_spreadsheet_functions():
    data = "name,sales\nann,120\nbob,80\ncy,95\n"
    ev = run(chain(("filter", {"mode": "expression", "expression": 'AND([sales] > 90, LEN([name]) <> 3)'}), data=data))
    assert out(ev, 2, "true")["name"].tolist() == ["cy"]


def test_export_carries_only_the_functions_used():
    data = "name,sales,day\n  Ann Lee ,120.456,2024-03-05\nbob,80,2024-12-31\n"
    steps = [("formula", {"formulas": [
        {"column": "tidy", "expression": "PROPER(TRIM([name]))", "dtype": ""},
        {"column": "later", "expression": "WORKDAY([day], 3)", "dtype": ""},
    ]})]
    code = export_script(run(chain(*steps, data=data)), "fx")
    assert "def PROPER" in code and "def TRIM" in code and "def WORKDAY" in code
    assert "def STDEV" not in code and "def CONVERT" not in code and "def TEXT" not in code


def test_exported_script_reproduces_the_result(tmp_path):
    data = "name,sales,day\n  Ann Lee ,120.456,2024-03-05\nbob,80,2024-12-31\n"
    target = tmp_path / "engine.csv"
    nodes = [
        (1, "text_input", {"data": data}),
        (2, "formula", {"formulas": [
            {"column": "level", "expression": 'IF([sales] > 100, "high", "low")', "dtype": ""},
            {"column": "tidy", "expression": "PROPER(TRIM([name]))", "dtype": ""},
            {"column": "label", "expression": 'TEXT([day], "mmm d, yyyy")', "dtype": ""},
            {"column": "later", "expression": "WORKDAY([day], 3)", "dtype": ""},
            {"column": "x", "expression": "ROUND([sales] / 7, 2) + CEILING.MATH([sales], 5)", "dtype": ""},
        ]}),
        (3, "output", {"path": str(target)}),
    ]
    from tests.test_tools import workflow

    wf = workflow(nodes, [(1, "out", 2, "in"), (2, "out", 3, "in")])
    ev = Engine().evaluate(wf, run_side_effects=True)
    assert all(r.status == "ok" for r in ev.results.values()), [r.error for r in ev.results.values()]
    other = tmp_path / "script.csv"
    code = export_script(ev, "fx").replace(repr(str(target)), repr(str(other)))
    script = tmp_path / "exported.py"
    script.write_text(code)
    subprocess.run([sys.executable, "-I", str(script)], check=True, cwd=tmp_path)
    pd.testing.assert_frame_equal(pd.read_csv(target), pd.read_csv(other))


def test_helpers_cover_every_function():
    for name in fx.FUNCTIONS:
        fns, imports, constants, packages = HELPERS[name]
        assert fns[-1] is fx.FUNCTIONS[name]
        assert not constants and not packages
        assert set(imports) <= {"math", "re", "decimal"}
