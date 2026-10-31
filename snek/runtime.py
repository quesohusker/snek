import glob
import io
import json
import os

import numpy as np
import pandas as pd

FORMATS = {
    ".csv": "csv",
    ".txt": "csv",
    ".tsv": "tsv",
    ".tab": "tsv",
    ".xlsx": "excel",
    ".xlsm": "excel",
    ".xls": "excel",
    ".json": "json",
    ".jsonl": "jsonl",
    ".ndjson": "jsonl",
    ".parquet": "parquet",
    ".pq": "parquet",
}


def match_files(path):
    pattern = os.path.expanduser(path)
    if any(ch in pattern for ch in "*?["):
        return sorted(glob.glob(pattern))
    return [pattern]


def read_any(path, fmt="auto", sheet=None, sep=None, encoding="utf-8", flatten=False, skiprows=0, nrows=None, filename_col=None):
    files = match_files(path)
    if not files:
        raise FileNotFoundError(f"No files match {path}")
    frames = []
    for file in files:
        kind = fmt if fmt != "auto" else FORMATS.get(os.path.splitext(file)[1].lower(), "csv")
        if kind in ("csv", "tsv"):
            df = pd.read_csv(file, sep=sep or ("\t" if kind == "tsv" else ","), encoding=encoding, skiprows=skiprows or None, nrows=nrows)
        elif kind == "excel":
            df = pd.read_excel(file, sheet_name=sheet or 0, skiprows=skiprows or None, nrows=nrows)
        else:
            if kind == "parquet":
                df = pd.read_parquet(file)
            elif kind == "jsonl":
                df = pd.read_json(file, lines=True, encoding=encoding)
            elif kind == "json":
                with open(file, encoding=encoding) as fh:
                    data = json.load(fh)
                records = data if isinstance(data, list) else [data]
                df = pd.json_normalize(records) if flatten else pd.DataFrame(records)
            else:
                raise ValueError(f"Unknown format {kind!r}")
            if skiprows:
                df = df.iloc[skiprows:]
            if nrows:
                df = df.head(nrows)
        if filename_col:
            df.insert(0, filename_col, os.path.basename(file))
        frames.append(df)
    if len(frames) == 1:
        return frames[0].reset_index(drop=True)
    return pd.concat(frames, ignore_index=True)


EXTENSIONS = {"csv": ".csv", "tsv": ".tsv", "excel": ".xlsx", "json": ".json", "jsonl": ".jsonl", "parquet": ".parquet"}


def output_path(path, fmt="auto"):
    target = os.path.abspath(os.path.expanduser(path))
    if not os.path.splitext(target)[1]:
        target += EXTENSIONS.get(fmt, ".csv")
    return target


def nested_to_json(df):
    out = df
    for i, col in enumerate(df.columns):
        s = df.iloc[:, i]
        if s.dtype == object and s.map(lambda v: isinstance(v, (dict, list))).any():
            if out is df:
                out = df.copy(deep=False)
            out.iloc[:, i] = s.map(lambda v: json.dumps(v, default=str) if isinstance(v, (dict, list)) else v)
    return out


def write_any(df, path, fmt="auto"):
    target = output_path(path, fmt)
    kind = fmt if fmt != "auto" else FORMATS.get(os.path.splitext(target)[1].lower(), "csv")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if kind in ("csv", "tsv"):
        nested_to_json(df).to_csv(target, index=False, sep="\t" if kind == "tsv" else ",")
    elif kind == "excel":
        out = nested_to_json(df).copy(deep=False)
        for col in out.columns:
            if isinstance(out[col].dtype, pd.DatetimeTZDtype):
                out[col] = out[col].dt.tz_localize(None)
        out.to_excel(target, index=False)
    elif kind == "parquet":
        df.to_parquet(target, index=False)
    elif kind == "jsonl":
        df.to_json(target, orient="records", lines=True, date_format="iso")
    elif kind == "json":
        df.to_json(target, orient="records", indent=2, date_format="iso")
    else:
        raise ValueError(f"Unknown format {kind!r}")
    return target


def join_lrj(left, right, left_on, right_on, suffix="_right"):
    joined = left.merge(right, left_on=left_on, right_on=right_on, how="inner", suffixes=("", suffix))
    right_keys = right[right_on].drop_duplicates().set_axis(left_on, axis=1)
    left_keys = left[left_on].drop_duplicates().set_axis(right_on, axis=1)
    left_only = left[left_on].merge(right_keys, on=left_on, how="left", indicator=True)["_merge"].eq("left_only").to_numpy()
    right_only = right[right_on].merge(left_keys, on=right_on, how="left", indicator=True)["_merge"].eq("left_only").to_numpy()
    return left[left_only].reset_index(drop=True), joined, right[right_only].reset_index(drop=True)


def unnest(df, column, prefix=True):
    flat = pd.json_normalize([v if isinstance(v, dict) else {} for v in df[column]], max_level=0)
    flat.index = df.index
    if prefix:
        flat = flat.add_prefix(f"{column}.")
    pos = df.columns.get_loc(column)
    rest = df.drop(columns=[column])
    clash = sorted(set(rest.columns) & set(flat.columns))
    if clash:
        raise ValueError(f"Unnest would duplicate columns {clash}. Turn on the prefix option.")
    return pd.concat([rest.iloc[:, :pos], flat, rest.iloc[:, pos:]], axis=1)


def iif(cond, then, otherwise):
    cond = pd.Series(cond).fillna(False).astype(bool)
    if not isinstance(then, pd.Series):
        then = pd.Series(then, index=cond.index)
    return then.where(cond, otherwise)


def auto_type(df, columns=None):
    bool_words = {"true": True, "false": False, "yes": True, "no": False, "t": True, "f": False, "y": True, "n": False}
    date_like = r"^\s*(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/\d{2,4})"
    out = df.copy()
    for col in list(df.columns) if columns is None else columns:
        s = out[col]
        if not (pd.api.types.is_string_dtype(s) or s.dtype == object):
            continue
        values = s.dropna()
        if not all(isinstance(v, str) for v in values):
            continue
        text = values.str.strip()
        text = text[text != ""]
        if text.empty:
            continue
        clean = s.where(s.isna(), s.astype("string").str.strip()).replace("", None)
        nums = pd.to_numeric(text, errors="coerce")
        if nums.notna().all() and not text.str.match(r"^0\d{3,}").any():
            converted = pd.to_numeric(clean, errors="coerce")
            out[col] = converted.astype("Int64") if (nums % 1 == 0).all() else converted.astype("float64")
        elif text.str.lower().isin(bool_words).all():
            out[col] = clean.str.lower().map(bool_words).astype("boolean")
        elif text.str.match(date_like).all() and pd.to_datetime(text, errors="coerce", format="mixed").notna().all():
            out[col] = pd.to_datetime(clean, errors="coerce", format="mixed")
    return out


def list_files(folder, pattern="*", recursive=False):
    root = os.path.abspath(os.path.expanduser(folder))
    found = glob.glob(os.path.join(root, "**", pattern), recursive=True) if recursive else glob.glob(os.path.join(root, pattern))
    rows = []
    for path in sorted(found):
        if os.path.isfile(path):
            st = os.stat(path)
            rows.append({
                "path": path,
                "name": os.path.basename(path),
                "folder": os.path.dirname(path),
                "extension": os.path.splitext(path)[1].lower(),
                "size_bytes": st.st_size,
                "modified": pd.Timestamp.fromtimestamp(st.st_mtime).floor("s"),
            })
    return pd.DataFrame(rows, columns=["path", "name", "folder", "extension", "size_bytes", "modified"])


def read_many(paths, filename_col=None, **options):
    frames = []
    for path in paths:
        df = read_any(path, **options)
        if filename_col:
            df.insert(0, filename_col, os.path.basename(path))
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def weighted_average(df, value, weight, group_by=(), name="WeightedAverage"):
    group_by = list(group_by)
    valid = df[value].notna() & df[weight].notna()
    work = df.loc[valid, group_by].assign(_vw=df.loc[valid, value] * df.loc[valid, weight], _w=df.loc[valid, weight])
    if group_by:
        out = work.groupby(group_by, dropna=False)[["_vw", "_w"]].sum().reset_index()
    else:
        out = pd.DataFrame({"_vw": [work["_vw"].sum()], "_w": [work["_w"].sum()]})
    out[name] = out["_vw"] / out["_w"]
    return out.drop(columns=["_vw", "_w"])


def select_rows(df, spec):
    keep = []
    n = len(df)
    for token in str(spec).replace("\n", ",").split(","):
        t = token.strip()
        if not t:
            continue
        if t.endswith("+"):
            keep.extend(range(int(t[:-1]) - 1, n))
        elif t.startswith("-"):
            keep.extend(range(0, int(t[1:])))
        elif "-" in t:
            a, b = t.split("-", 1)
            keep.extend(range(int(a) - 1, int(b)))
        else:
            keep.append(int(t) - 1)
    return df.iloc[sorted({i for i in keep if 0 <= i < n})].reset_index(drop=True)


def parse_json(value, strict=False):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return json.loads(value)
    except ValueError:
        if strict:
            raise
        return None


HELPERS = {
    "read_any": ([match_files, read_any], ["glob", "json", "os"], ["FORMATS"]),
    "write_any": ([output_path, nested_to_json, write_any], ["json", "os"], ["FORMATS", "EXTENSIONS"]),
    "join_lrj": ([join_lrj], [], []),
    "unnest": ([unnest], [], []),
    "iif": ([iif], [], []),
    "auto_type": ([auto_type], [], []),
    "list_files": ([list_files], ["glob", "os"], []),
    "read_many": ([match_files, read_any, read_many], ["glob", "json", "os"], ["FORMATS"]),
    "weighted_average": ([weighted_average], [], []),
    "select_rows": ([select_rows], [], []),
    "parse_json": ([parse_json], ["json"], []),
}

NAMESPACE = {
    "pd": pd,
    "np": np,
    "io": io,
    "FORMATS": FORMATS,
    "EXTENSIONS": EXTENSIONS,
    "output_path": output_path,
    "nested_to_json": nested_to_json,
    "match_files": match_files,
    "read_any": read_any,
    "write_any": write_any,
    "join_lrj": join_lrj,
    "unnest": unnest,
    "iif": iif,
    "auto_type": auto_type,
    "list_files": list_files,
    "read_many": read_many,
    "weighted_average": weighted_average,
    "select_rows": select_rows,
    "parse_json": parse_json,
}
