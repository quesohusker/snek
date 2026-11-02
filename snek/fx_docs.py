GROUPS = ["Logical", "Information", "Text", "Date and time", "Math and trigonometry", "Engineering"]

SKIP = "skip"

DOCS = [
    ("IF", "Logical", "IF(test, value_if_true, value_if_false)", "Give one value when a test is true and another when it is false.", 'IF(5 > 3, "yes", "no")', '"yes"', "condition branch else"),
    ("IFS", "Logical", "IFS(test1, value1, test2, value2, ...)", "Check tests in order and return the value for the first true one. No match gives a blank.", 'IFS(5 > 9, "a", 5 > 3, "b")', '"b"', "multiple conditions nested if"),
    ("IFERROR", "Logical", "IFERROR(value, value_if_error)", "Replace a blank or an infinite result with another value. A divide by zero in a column gives such a result.", "IFERROR(NA(), 0)", "0", "catch error replace missing"),
    ("IFNA", "Logical", "IFNA(value, value_if_na)", "Replace a blank with another value. Infinite results stay.", "IFNA(NA(), 7)", "7", "fill missing replace blank"),
    ("SWITCH", "Logical", "SWITCH(expression, value1, result1, value2, result2, ..., default)", "Compare a value with a list and return the matching result. A last unpaired value is the default.", 'SWITCH("b", "a", 1, "b", 2, 99)', "2", "lookup map case"),
    ("AND", "Logical", "AND(test1, test2, ...)", "True when every test is true, row by row.", "AND(5 > 3, 2 < 4)", "True", "all both"),
    ("OR", "Logical", "OR(test1, test2, ...)", "True when at least one test is true, row by row.", "OR(5 < 3, 2 < 4)", "True", "any either"),
    ("NOT", "Logical", "NOT(test)", "Flip true and false.", "NOT(5 > 3)", "False", "negate invert"),
    ("XOR", "Logical", "XOR(test1, test2, ...)", "True when an odd number of tests are true.", "XOR(True, True)", "False", "exclusive or"),
    ("TRUE", "Logical", "TRUE()", "The value true.", "TRUE()", "True", ""),
    ("FALSE", "Logical", "FALSE()", "The value false.", "FALSE()", "False", ""),
    ("ISBLANK", "Information", "ISBLANK(value)", "True when a value is blank.", "ISBLANK(NA())", "True", "empty null missing nan"),
    ("ISNUMBER", "Information", "ISNUMBER(value)", "True when a value is a number. Text, true/false and blanks are not.", 'ISNUMBER("5")', "False", ""),
    ("ISTEXT", "Information", "ISTEXT(value)", "True when a value is text.", 'ISTEXT("a")', "True", "string"),
    ("ISNONTEXT", "Information", "ISNONTEXT(value)", "True when a value is not text. Blanks count as not text.", 'ISNONTEXT("a")', "False", ""),
    ("ISLOGICAL", "Information", "ISLOGICAL(value)", "True when a value is true or false.", "ISLOGICAL(True)", "True", "boolean"),
    ("ISEVEN", "Information", "ISEVEN(number)", "True when a number is even. A decimal is cut to a whole number first.", "ISEVEN(-2)", "True", ""),
    ("ISODD", "Information", "ISODD(number)", "True when a number is odd. A decimal is cut to a whole number first.", "ISODD(3)", "True", ""),
    ("ISERROR", "Information", "ISERROR(value)", "True for a blank or an infinite result.", "ISERROR(NA())", "True", "error check"),
    ("ISNA", "Information", "ISNA(value)", "True when a value is blank.", "ISNA(NA())", "True", ""),
    ("NA", "Information", "NA()", "A blank result.", "ISNA(NA())", "True", "missing nan"),
    ("N", "Information", "N(value)", "Turn a value into a number. Text and blanks give 0, true gives 1.", "N(True)", "1", "convert"),
    ("TYPE", "Information", "TYPE(value)", "Tell the kind of a value: 1 number, 2 text, 4 true/false, 16 error, 64 list.", 'TYPE("a")', "2", "kind"),
    ("LEFT", "Text", "LEFT(text, num_chars)", "The first characters of text.", 'LEFT("Sale price", 4)', '"Sale"', "first characters substring start"),
    ("RIGHT", "Text", "RIGHT(text, num_chars)", "The last characters of text.", 'RIGHT("Sale price", 5)', '"price"', "last characters substring end"),
    ("MID", "Text", "MID(text, start_num, num_chars)", "Characters from the middle of text. The first character is number 1.", 'MID("Fluid Flow", 1, 5)', '"Fluid"', "substring slice"),
    ("LEN", "Text", "LEN(text)", "The number of characters in text.", 'LEN("hello")', "5", "length count characters"),
    ("UPPER", "Text", "UPPER(text)", "Change text to capital letters.", 'UPPER("total")', '"TOTAL"', "uppercase capitalize"),
    ("LOWER", "Text", "LOWER(text)", "Change text to small letters.", 'LOWER("E. E. Cummings")', '"e. e. cummings"', "lowercase"),
    ("PROPER", "Text", "PROPER(text)", "Capitalize the first letter of every word.", 'PROPER("this is a TITLE")', '"This Is A Title"', "title case"),
    ("TRIM", "Text", "TRIM(text)", "Remove extra spaces. Keep one space between words.", 'TRIM("  First   Quarter  ")', '"First Quarter"', "remove spaces strip whitespace"),
    ("CLEAN", "Text", "CLEAN(text)", "Remove characters that cannot print, such as line breaks.", 'CLEAN("a" + CHAR(7) + "b")', '"ab"', "control characters non printable"),
    ("CONCAT", "Text", "CONCAT(text1, text2, ...)", "Join text values. Numbers become text and blanks become nothing.", 'CONCAT("a", 1, "b")', '"a1b"', "join combine append"),
    ("CONCATENATE", "Text", "CONCATENATE(text1, text2, ...)", "Join text values. The same as CONCAT.", 'CONCATENATE("Mr ", "Smith")', '"Mr Smith"', "join combine"),
    ("TEXTJOIN", "Text", "TEXTJOIN(delimiter, ignore_empty, text1, text2, ...)", "Join text values with a separator between them.", 'TEXTJOIN(", ", TRUE(), "a", "", "b")', '"a, b"', "join separator delimiter"),
    ("TEXTBEFORE", "Text", "TEXTBEFORE(text, delimiter, instance_num, match_mode, match_end, if_not_found)", "The text before a delimiter. A negative instance counts from the end.", 'TEXTBEFORE("a-b-c", "-", -1)', '"a-b"', "split left of"),
    ("TEXTAFTER", "Text", "TEXTAFTER(text, delimiter, instance_num, match_mode, match_end, if_not_found)", "The text after a delimiter. A negative instance counts from the end.", 'TEXTAFTER("a-b-c", "-")', '"b-c"', "split right of"),
    ("FIND", "Text", "FIND(find_text, within_text, start_num)", "The position of text inside other text. Capital letters matter. No match gives a blank.", 'FIND("M", "Miriam McGovern", 3)', "8", "position locate index"),
    ("SEARCH", "Text", "SEARCH(find_text, within_text, start_num)", "The position of text inside other text. Capital letters do not matter. ? and * are wildcards.", 'SEARCH("e?", "Statements")', "5", "position locate wildcard"),
    ("SUBSTITUTE", "Text", "SUBSTITUTE(text, old_text, new_text, instance_num)", "Replace old text with new text. Pick one occurrence with instance_num.", 'SUBSTITUTE("Quarter 1, 2008", "1", "2", 3)', '"Quarter 1, 2008"', "replace swap"),
    ("REPLACE", "Text", "REPLACE(old_text, start_num, num_chars, new_text)", "Replace characters by position.", 'REPLACE("abcdefghijk", 6, 5, "*")', '"abcde*k"', "overwrite insert"),
    ("REPT", "Text", "REPT(text, number_times)", "Repeat text a number of times.", 'REPT("*-", 3)', '"*-*-*-"', "repeat"),
    ("EXACT", "Text", "EXACT(text1, text2)", "True when two texts are the same, including capital letters.", 'EXACT("word", "Word")', "False", "equal compare"),
    ("VALUE", "Text", "VALUE(text)", "Turn text that looks like a number into a number. Dates become a day number.", 'VALUE("$1,234.50")', "1234.5", "convert to number parse"),
    ("NUMBERVALUE", "Text", "NUMBERVALUE(text, decimal_separator, group_separator)", "Turn text into a number with the separators you name.", 'NUMBERVALUE("2.500,27", ",", ".")', "2500.27", "parse locale convert"),
    ("TEXT", "Text", "TEXT(value, format_text)", "Format a number or date as text with a format such as 0.00, #,##0, 0% or yyyy-mm-dd.", 'TEXT(1234.567, "$#,##0.00")', '"$1,234.57"', "format number date string"),
    ("FIXED", "Text", "FIXED(number, decimals, no_commas)", "Round a number and give it as text with commas.", "FIXED(1234.567, 1)", '"1,234.6"', "round format"),
    ("DOLLAR", "Text", "DOLLAR(number, decimals)", "Round a number and give it as text with a dollar sign.", "DOLLAR(1234.567)", '"$1,234.57"', "currency format money"),
    ("CHAR", "Text", "CHAR(number)", "The character for a code from 1 to 255.", "CHAR(65)", '"A"', "character from code"),
    ("CODE", "Text", "CODE(text)", "The code of the first character.", 'CODE("A")', "65", "character to code"),
    ("UNICHAR", "Text", "UNICHAR(number)", "The Unicode character for a code.", "UNICHAR(9731)", '"\\u2603"', "character from code"),
    ("UNICODE", "Text", "UNICODE(text)", "The Unicode code of the first character.", 'UNICODE("A")', "65", "character to code"),
    ("T", "Text", "T(value)", "Give the value if it is text, or empty text if it is not.", 'T("a")', '"a"', ""),
    ("REGEXTEST", "Text", "REGEXTEST(text, pattern, case_sensitivity)", "True when text matches a regular expression. Set case_sensitivity to 1 to ignore capital letters.", r'REGEXTEST("abc123", r"\d+")', "True", "regex pattern match"),
    ("REGEXEXTRACT", "Text", "REGEXEXTRACT(text, pattern, return_mode, case_sensitivity)", "Pull text out with a regular expression. Mode 0 gives the first match, 1 all matches, 2 the groups.", r'REGEXEXTRACT("abc123def45", r"\d+")', '"123"', "regex pattern capture"),
    ("REGEXREPLACE", "Text", "REGEXREPLACE(text, pattern, replacement, occurrence, case_sensitivity)", "Replace text with a regular expression. Use $1, $2 for groups.", r'REGEXREPLACE("John Smith", r"(\w+) (\w+)", "$2, $1")', '"Smith, John"', "regex pattern substitute"),
    ("DATE", "Date and time", "DATE(year, month, day)", "Make a date from a year, month and day. Months and days past the end roll over.", "DATE(2008, 14, 2)", 'pd.Timestamp("2009-02-02")', "build construct"),
    ("TIME", "Date and time", "TIME(hour, minute, second)", "Make a time of day. Add it to a date.", "TIME(12, 30, 0)", 'pd.Timedelta(hours=12, minutes=30)', "build construct"),
    ("DATEVALUE", "Date and time", "DATEVALUE(date_text)", "Turn text into a date.", 'DATEVALUE("2008-07-24")', 'pd.Timestamp("2008-07-24")', "parse convert text to date"),
    ("TIMEVALUE", "Date and time", "TIMEVALUE(time_text)", "Turn text into a time of day.", 'TIMEVALUE("6:45 PM")', 'pd.Timedelta(hours=18, minutes=45)', "parse convert text to time"),
    ("NOW", "Date and time", "NOW()", "The date and time right now.", "NOW()", SKIP, "current time"),
    ("TODAY", "Date and time", "TODAY()", "Today's date.", "TODAY()", SKIP, "current date"),
    ("YEAR", "Date and time", "YEAR(date)", "The year of a date.", 'YEAR("2008-07-05")', "2008", "extract part"),
    ("MONTH", "Date and time", "MONTH(date)", "The month of a date, 1 to 12.", 'MONTH("2008-07-05")', "7", "extract part"),
    ("DAY", "Date and time", "DAY(date)", "The day of the month, 1 to 31.", 'DAY("2008-07-05")', "5", "extract part"),
    ("HOUR", "Date and time", "HOUR(time)", "The hour, 0 to 23.", 'HOUR("2008-07-05 13:45:10")', "13", "extract part"),
    ("MINUTE", "Date and time", "MINUTE(time)", "The minute, 0 to 59.", 'MINUTE("2008-07-05 13:45:10")', "45", "extract part"),
    ("SECOND", "Date and time", "SECOND(time)", "The second, 0 to 59.", 'SECOND("2008-07-05 13:45:10")', "10", "extract part"),
    ("WEEKDAY", "Date and time", "WEEKDAY(date, return_type)", "The day of the week as a number. Type 1 is Sunday=1, type 2 is Monday=1, type 3 is Monday=0.", 'WEEKDAY("2008-02-14", 2)', "4", "day of week"),
    ("WEEKNUM", "Date and time", "WEEKNUM(date, return_type)", "The week of the year. Type 1 starts weeks on Sunday, type 2 on Monday, type 21 follows ISO.", 'WEEKNUM("2012-03-09", 2)', "11", "week of year"),
    ("ISOWEEKNUM", "Date and time", "ISOWEEKNUM(date)", "The ISO week number of a date.", 'ISOWEEKNUM("2012-03-09")', "10", "iso week"),
    ("EDATE", "Date and time", "EDATE(start_date, months)", "The date a number of months before or after a date.", 'EDATE("2011-01-15", -1)', 'pd.Timestamp("2010-12-15")', "add months shift"),
    ("EOMONTH", "Date and time", "EOMONTH(start_date, months)", "The last day of the month, a number of months away.", 'EOMONTH("2011-01-01", 1)', 'pd.Timestamp("2011-02-28")', "month end last day"),
    ("DAYS", "Date and time", "DAYS(end_date, start_date)", "The number of days from the start date to the end date.", 'DAYS("2011-03-15", "2011-02-01")', "42", "difference between dates"),
    ("DATEDIF", "Date and time", "DATEDIF(start_date, end_date, unit)", 'The whole years ("Y"), months ("M") or days ("D") between two dates. "YM", "YD" and "MD" ignore the larger parts.', 'DATEDIF("2001-06-01", "2002-08-15", "D")', "440", "age difference years months"),
    ("YEARFRAC", "Date and time", "YEARFRAC(start_date, end_date, basis)", "The part of a year between two dates. Basis 0 is 30/360, 1 actual/actual, 2 actual/360, 3 actual/365, 4 European 30/360.", 'ROUND(YEARFRAC("2012-01-01", "2012-07-30", 3), 6)', "0.578082", "fraction of year"),
    ("NETWORKDAYS", "Date and time", "NETWORKDAYS(start_date, end_date, holidays)", "The number of weekdays between two dates, both included. Holidays are skipped.", 'NETWORKDAYS("2012-10-01", "2013-03-01")', "110", "business days working days"),
    ("NETWORKDAYS.INTL", "Date and time", "NETWORKDAYS.INTL(start_date, end_date, weekend, holidays)", "Like NETWORKDAYS with the weekend you choose. A weekend is a code 1 to 7 or 11 to 17, or seven 0/1 characters from Monday.", 'NETWORKDAYS.INTL("2012-01-01", "2013-02-01", 11)', "341", "business days working days weekend"),
    ("WORKDAY", "Date and time", "WORKDAY(start_date, days, holidays)", "The date a number of weekdays before or after a date. Holidays are skipped.", 'WORKDAY("2008-10-01", 151)', 'pd.Timestamp("2009-04-30")', "business days add working days"),
    ("WORKDAY.INTL", "Date and time", "WORKDAY.INTL(start_date, days, weekend, holidays)", "Like WORKDAY with the weekend you choose.", 'WORKDAY.INTL("2012-01-01", 30, 11)', 'pd.Timestamp("2012-02-04")', "business days add working days weekend"),
    ("DAYS360", "Date and time", "DAYS360(start_date, end_date, method)", "The days between two dates on a 360-day year of twelve 30-day months.", 'DAYS360("2011-01-01", "2011-12-31")', "360", "accounting days"),
    ("ABS", "Math and trigonometry", "ABS(number)", "The size of a number without its sign.", "ABS(-5)", "5", "absolute value"),
    ("SIGN", "Math and trigonometry", "SIGN(number)", "1 for a positive number, -1 for a negative one, 0 for zero.", "SIGN(-10)", "-1", ""),
    ("ROUND", "Math and trigonometry", "ROUND(number, num_digits)", "Round a number. Halves go away from zero. A negative num_digits rounds to the left of the point.", "ROUND(2.15, 1)", "2.2", "decimals"),
    ("ROUNDUP", "Math and trigonometry", "ROUNDUP(number, num_digits)", "Round a number away from zero.", "ROUNDUP(3.14159, 3)", "3.142", "ceiling decimals"),
    ("ROUNDDOWN", "Math and trigonometry", "ROUNDDOWN(number, num_digits)", "Round a number toward zero.", "ROUNDDOWN(3.14159, 3)", "3.141", "floor decimals truncate"),
    ("MROUND", "Math and trigonometry", "MROUND(number, multiple)", "Round a number to the nearest multiple.", "MROUND(10, 3)", "9", "nearest multiple"),
    ("CEILING", "Math and trigonometry", "CEILING(number, significance)", "Round up to a multiple of the significance.", "CEILING(2.5, 1)", "3", "round up multiple"),
    ("FLOOR", "Math and trigonometry", "FLOOR(number, significance)", "Round down to a multiple of the significance.", "FLOOR(3.7, 2)", "2", "round down multiple"),
    ("CEILING.MATH", "Math and trigonometry", "CEILING.MATH(number, significance, mode)", "Round up toward larger numbers. A non-zero mode rounds negative numbers away from zero.", "CEILING.MATH(-5.5, 2, 1)", "-6", "round up multiple"),
    ("FLOOR.MATH", "Math and trigonometry", "FLOOR.MATH(number, significance, mode)", "Round down toward smaller numbers. A non-zero mode rounds negative numbers toward zero.", "FLOOR.MATH(-5.5, 2, -1)", "-4", "round down multiple"),
    ("INT", "Math and trigonometry", "INT(number)", "Round down to the nearest whole number.", "INT(-8.9)", "-9", "floor whole number"),
    ("TRUNC", "Math and trigonometry", "TRUNC(number, num_digits)", "Cut off the decimals without rounding.", "TRUNC(-3.14159, 2)", "-3.14", "truncate decimals"),
    ("MOD", "Math and trigonometry", "MOD(number, divisor)", "The remainder after division. The result has the sign of the divisor.", "MOD(-3, 2)", "1", "remainder modulo"),
    ("QUOTIENT", "Math and trigonometry", "QUOTIENT(numerator, denominator)", "The whole part of a division.", "QUOTIENT(5, 2)", "2", "integer division"),
    ("POWER", "Math and trigonometry", "POWER(number, power)", "A number raised to a power.", "POWER(5, 2)", "25", "exponent square"),
    ("SQRT", "Math and trigonometry", "SQRT(number)", "The square root.", "SQRT(16)", "4", "root"),
    ("SQRTPI", "Math and trigonometry", "SQRTPI(number)", "The square root of the number times pi.", "ROUND(SQRTPI(2), 6)", "2.506628", ""),
    ("EXP", "Math and trigonometry", "EXP(number)", "e raised to a power.", "ROUND(EXP(1), 6)", "2.718282", "exponential"),
    ("LN", "Math and trigonometry", "LN(number)", "The natural logarithm.", "ROUND(LN(86), 6)", "4.454347", "log"),
    ("LOG", "Math and trigonometry", "LOG(number, base)", "The logarithm in a base. The default base is 10.", "LOG(8, 2)", "3", ""),
    ("LOG10", "Math and trigonometry", "LOG10(number)", "The base-10 logarithm.", "LOG10(100000)", "5", ""),
    ("PI", "Math and trigonometry", "PI()", "The number pi.", "ROUND(PI(), 5)", "3.14159", ""),
    ("DEGREES", "Math and trigonometry", "DEGREES(angle)", "Change radians to degrees.", "DEGREES(PI())", "180", "radians"),
    ("RADIANS", "Math and trigonometry", "RADIANS(angle)", "Change degrees to radians.", "ROUND(RADIANS(270), 6)", "4.712389", "degrees"),
    ("SIN", "Math and trigonometry", "SIN(number)", "The sine of an angle in radians.", "SIN(PI() / 2)", "1", "trig"),
    ("COS", "Math and trigonometry", "COS(number)", "The cosine of an angle in radians.", "COS(0)", "1", "trig"),
    ("TAN", "Math and trigonometry", "TAN(number)", "The tangent of an angle in radians.", "ROUND(TAN(0.785398163), 4)", "1", "trig"),
    ("ASIN", "Math and trigonometry", "ASIN(number)", "The arcsine, in radians.", "ROUND(ASIN(-0.5), 6)", "-0.523599", "trig inverse"),
    ("ACOS", "Math and trigonometry", "ACOS(number)", "The arccosine, in radians.", "ROUND(ACOS(-0.5), 6)", "2.094395", "trig inverse"),
    ("ATAN", "Math and trigonometry", "ATAN(number)", "The arctangent, in radians.", "ROUND(ATAN(1), 6)", "0.785398", "trig inverse"),
    ("ATAN2", "Math and trigonometry", "ATAN2(x_num, y_num)", "The angle of a point from the x axis, in radians. Note that x comes first.", "ROUND(ATAN2(1, 1), 6)", "0.785398", "trig angle"),
    ("SINH", "Math and trigonometry", "SINH(number)", "The hyperbolic sine.", "ROUND(SINH(1), 6)", "1.175201", "trig"),
    ("COSH", "Math and trigonometry", "COSH(number)", "The hyperbolic cosine.", "ROUND(COSH(4), 5)", "27.30823", "trig"),
    ("TANH", "Math and trigonometry", "TANH(number)", "The hyperbolic tangent.", "ROUND(TANH(-2), 6)", "-0.964028", "trig"),
    ("FACT", "Math and trigonometry", "FACT(number)", "The factorial of a number.", "FACT(5)", "120", "factorial"),
    ("COMBIN", "Math and trigonometry", "COMBIN(number, number_chosen)", "The number of ways to choose some items from a group, order ignored.", "COMBIN(8, 2)", "28", "combinations choose"),
    ("GCD", "Math and trigonometry", "GCD(number1, number2, ...)", "The greatest common divisor.", "GCD(24, 36)", "12", "greatest common factor"),
    ("LCM", "Math and trigonometry", "LCM(number1, number2, ...)", "The least common multiple.", "LCM(24, 36)", "72", ""),
    ("EVEN", "Math and trigonometry", "EVEN(number)", "Round away from zero to the next even whole number.", "EVEN(-1)", "-2", ""),
    ("ODD", "Math and trigonometry", "ODD(number)", "Round away from zero to the next odd whole number.", "ODD(2)", "3", ""),
    ("RAND", "Math and trigonometry", "RAND(like)", "A random number from 0 up to 1. Give a column as `like` to get a different number on every row.", "RAND()", SKIP, "random uniform"),
    ("RANDBETWEEN", "Math and trigonometry", "RANDBETWEEN(bottom, top, like)", "A random whole number between two numbers. Give a column as `like` to get a different number on every row.", "RANDBETWEEN(1, 6)", SKIP, "random dice integer"),
    ("SUM", "Math and trigonometry", "SUM(number1, number2, ...)", "The total of all the numbers in the columns and values given. Blanks are skipped.", "SUM(1, 2, 3)", "6", "total add"),
    ("PRODUCT", "Math and trigonometry", "PRODUCT(number1, number2, ...)", "All the numbers multiplied together.", "PRODUCT(5, 15, 30)", "2250", "multiply"),
    ("SUMPRODUCT", "Math and trigonometry", "SUMPRODUCT(array1, array2, ...)", "Multiply columns row by row, then add the results.", "SUMPRODUCT([3, 8, 6], [2, 6, 5])", "84", "weighted total dot product"),
    ("SUMSQ", "Math and trigonometry", "SUMSQ(number1, number2, ...)", "The total of the squares.", "SUMSQ(3, 4)", "25", "sum of squares"),
    ("BITAND", "Engineering", "BITAND(number1, number2)", "A bit-by-bit AND of two whole numbers.", "BITAND(1, 5)", "1", "binary"),
    ("BITOR", "Engineering", "BITOR(number1, number2)", "A bit-by-bit OR of two whole numbers.", "BITOR(23, 10)", "31", "binary"),
    ("BITXOR", "Engineering", "BITXOR(number1, number2)", "A bit-by-bit exclusive OR of two whole numbers.", "BITXOR(5, 3)", "6", "binary"),
    ("BITLSHIFT", "Engineering", "BITLSHIFT(number, shift_amount)", "Shift bits to the left.", "BITLSHIFT(4, 2)", "16", "binary"),
    ("BITRSHIFT", "Engineering", "BITRSHIFT(number, shift_amount)", "Shift bits to the right.", "BITRSHIFT(13, 2)", "3", "binary"),
    ("BIN2DEC", "Engineering", "BIN2DEC(number)", "Change a binary number to decimal.", 'BIN2DEC("1100100")', "100", "convert base"),
    ("DEC2BIN", "Engineering", "DEC2BIN(number, places)", "Change a decimal number to binary text.", "DEC2BIN(9, 4)", '"1001"', "convert base"),
    ("DEC2HEX", "Engineering", "DEC2HEX(number, places)", "Change a decimal number to hexadecimal text.", "DEC2HEX(255)", '"FF"', "convert base"),
    ("HEX2DEC", "Engineering", "HEX2DEC(number)", "Change a hexadecimal number to decimal.", 'HEX2DEC("A5")', "165", "convert base"),
    ("CONVERT", "Engineering", "CONVERT(number, from_unit, to_unit)", 'Change a number from one unit to another, such as "lbm" to "kg", "mi" to "km" or "F" to "C".', 'CONVERT(68, "F", "C")', "20", "units measurement"),
    ("DELTA", "Engineering", "DELTA(number1, number2)", "1 when two numbers are equal, otherwise 0.", "DELTA(5, 4)", "0", "equal test"),
]


def show(value):
    import numpy as np
    import pandas as pd

    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d") if value == value.normalize() else value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, pd.Timedelta):
        total = int(value.total_seconds())
        return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"
    if isinstance(value, (bool, np.bool_)):
        return "TRUE" if value else "FALSE"
    if isinstance(value, str):
        return '"' + value + '"'
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value)


def catalog():
    import numpy as np
    import pandas as pd

    rows = []
    for name, group, syntax, description, example, expected, words in DOCS:
        result = "varies" if expected == SKIP else show(eval(expected, {"pd": pd, "np": np}))
        rows.append({"name": name, "group": group, "syntax": syntax, "description": description, "example": example, "result": result, "words": words})
    return {"groups": GROUPS, "functions": rows}
