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


def write_any(df, path, fmt="auto"):
    target = os.path.expanduser(path)
    kind = fmt if fmt != "auto" else FORMATS.get(os.path.splitext(target)[1].lower(), "csv")
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    if kind in ("csv", "tsv"):
        df.to_csv(target, index=False, sep="\t" if kind == "tsv" else ",")
    elif kind == "excel":
        out = df.copy(deep=False)
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


HELPERS = {
    "read_any": [match_files, read_any],
    "write_any": [write_any],
    "join_lrj": [join_lrj],
    "unnest": [unnest],
    "iif": [iif],
}

NAMESPACE = {
    "pd": pd,
    "np": np,
    "io": io,
    "FORMATS": FORMATS,
    "match_files": match_files,
    "read_any": read_any,
    "write_any": write_any,
    "join_lrj": join_lrj,
    "unnest": unnest,
    "iif": iif,
}
