import json

import pandas as pd


def to_rows(df):
    page = df.set_axis(range(df.shape[1]), axis=1)
    return json.loads(page.to_json(orient="values", date_format="iso", default_handler=str))


def scalar(value):
    return to_rows(pd.DataFrame({"v": [value]}))[0][0]


def profile_column(s):
    info = {"nulls": int(s.isna().sum()), "unique": None, "min": None, "max": None, "mean": None}
    try:
        info["unique"] = int(s.nunique(dropna=True))
    except TypeError:
        pass
    numeric = pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s)
    if numeric or pd.api.types.is_datetime64_any_dtype(s):
        valid = s.dropna()
        if len(valid):
            info["min"] = scalar(valid.min())
            info["max"] = scalar(valid.max())
            if numeric:
                info["mean"] = scalar(valid.mean())
    elif info["unique"] is not None:
        top = s.value_counts(dropna=True).head(1)
        if len(top):
            info["top"] = scalar(top.index[0])
            info["top_count"] = int(top.iloc[0])
    return info


def preview(df, offset=0, limit=100, profile=False):
    offset = max(int(offset), 0)
    limit = max(min(int(limit), 2000), 1)
    columns = [{"name": str(c), "dtype": str(t)} for c, t in df.dtypes.items()]
    if profile:
        for i, col in enumerate(columns):
            col.update(profile_column(df.iloc[:, i]))
    return {
        "total": int(len(df)),
        "offset": offset,
        "limit": limit,
        "columns": columns,
        "rows": to_rows(df.iloc[offset:offset + limit]),
    }
