import csv
import io
import json
import os
import time
import urllib.error
import urllib.request
import uuid

import numpy as np
import pandas as pd

from snek.fx import _haversine, _initial_bearing, _state_lookup, _state_table, _unit_km

EARTH_RADIUS_KM = 6371.0088
US_BASEMAP = "https://cdn.jsdelivr.net/npm/vega-datasets@2.11.0/data/us-10m.json"
WORLD_BASEMAP = "https://cdn.jsdelivr.net/npm/vega-datasets@2.11.0/data/world-110m.json"
CENSUS_BATCH = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"


def coordinate_arrays(df, lat, lon):
    a = pd.to_numeric(df[lat], errors="coerce").to_numpy(dtype="float64", na_value=np.nan)
    b = pd.to_numeric(df[lon], errors="coerce").to_numpy(dtype="float64", na_value=np.nan)
    return a, b, (np.abs(a) <= 90) & (np.abs(b) <= 180)


def unused_name(df, name):
    return name if name not in df.columns else f"{name}_new"


def distance_between(df, lat1, lon1, lat2, lon2, unit="mi", name="distance", bearing=None):
    a1, o1, ok1 = coordinate_arrays(df, lat1, lon1)
    a2, o2, ok2 = coordinate_arrays(df, lat2, lon2)
    ok = ok1 & ok2
    out = df.copy()
    out[name] = np.where(ok, _haversine(a1, o1, a2, o2, EARTH_RADIUS_KM) / _unit_km(unit), np.nan)
    if bearing:
        out[bearing] = np.where(ok, _initial_bearing(a1, o1, a2, o2), np.nan)
    return out


def find_nearest(targets, places, target_lat, target_lon, place_lat, place_lon, count=1, max_distance=0, unit="mi", keep_unmatched=True, columns=None, rank_name="nearest_rank", distance_name="distance"):
    from sklearn.neighbors import BallTree

    factor = EARTH_RADIUS_KM / _unit_km(unit)
    ta, to, tok = coordinate_arrays(targets, target_lat, target_lon)
    pa, po, pok = coordinate_arrays(places, place_lat, place_lon)
    pool = places.reset_index(drop=True)
    wanted = list(columns) if columns else list(pool.columns)
    count = int(count or 0)
    limit = float(max_distance or 0)
    if count < 1 and limit <= 0:
        raise ValueError("Set a distance when you ask for every place within it")
    valid_targets = np.flatnonzero(tok)
    valid_places = np.flatnonzero(pok)
    t_index = np.array([], dtype="int64")
    p_index = np.array([], dtype="int64")
    ranks = np.array([], dtype="int64")
    dists = np.array([], dtype="float64")
    if len(valid_targets) and len(valid_places):
        tree = BallTree(np.radians(np.column_stack([pa[valid_places], po[valid_places]])), metric="haversine")
        query = np.radians(np.column_stack([ta[valid_targets], to[valid_targets]]))
        if count >= 1:
            k = min(count, len(valid_places))
            d, ix = tree.query(query, k=k)
            dist = (d * factor).ravel()
            keep = dist <= limit if limit > 0 else np.ones(len(dist), dtype=bool)
            t_index = np.repeat(valid_targets, k)[keep]
            p_index = valid_places[ix.ravel()][keep]
            ranks = np.tile(np.arange(1, k + 1), len(valid_targets))[keep]
            dists = dist[keep]
        else:
            ix, d = tree.query_radius(query, r=limit / factor, return_distance=True)
            parts_t, parts_p, parts_r, parts_d = [], [], [], []
            for row, found, near in zip(valid_targets, ix, d):
                order = np.argsort(near, kind="stable")
                parts_t.append(np.full(len(order), row))
                parts_p.append(valid_places[found[order]])
                parts_r.append(np.arange(1, len(order) + 1))
                parts_d.append(near[order] * factor)
            if parts_t:
                t_index, p_index, ranks, dists = (np.concatenate(x) for x in (parts_t, parts_p, parts_r, parts_d))
    pairs = pd.DataFrame({"_t": t_index, "_p": p_index, rank_name: pd.array(ranks, dtype="Int64"), distance_name: dists})
    left = targets.reset_index(drop=True).assign(_t=np.arange(len(targets)))
    out = left.merge(pairs, on="_t", how="left" if keep_unmatched else "inner")
    right = pool[wanted].assign(_p=np.arange(len(pool)))
    out = out.merge(right, on="_p", how="left", suffixes=("", "_place"))
    return out.drop(columns=["_t", "_p"]).reset_index(drop=True)


def census_batch(rows, benchmark):
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    boundary = uuid.uuid4().hex
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="benchmark"\r\n\r\n{benchmark}\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="addressFile"; filename="addresses.csv"\r\nContent-Type: text/csv\r\n\r\n{buf.getvalue()}\r\n'
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    request = urllib.request.Request(CENSUS_BATCH, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                text = response.read().decode("utf-8", errors="replace")
            break
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(2 * (attempt + 1))
    else:
        raise ConnectionError(f"The Census geocoder did not answer: {last}")
    found = {}
    for record in csv.reader(io.StringIO(text)):
        if len(record) < 3:
            continue
        status = record[2]
        if status == "Match" and len(record) >= 6 and "," in record[5]:
            lon, lat = record[5].split(",", 1)
            found[record[0]] = (status, record[3], record[4], float(lat), float(lon))
        else:
            found[record[0]] = (status, "", "", np.nan, np.nan)
    return found


def geocode_addresses(df, address=None, street=None, city=None, state=None, zip_code=None, batch_size=1000, benchmark="Public_AR_Current"):
    def text(col):
        if not col:
            return pd.Series("", index=df.index)
        return df[col].astype("string").fillna("").str.replace(r"\s+", " ", regex=True).str.strip()

    streets = text(address or street)
    cities, states, zips = text(city), text(state), text(zip_code)
    blank = ((streets == "") & (cities == "") & (states == "") & (zips == "")).to_numpy()
    n = len(df)
    status = np.where(blank, "Blank", "No_Match").astype(object)
    kind = np.full(n, "", dtype=object)
    matched = np.full(n, "", dtype=object)
    lat = np.full(n, np.nan)
    lon = np.full(n, np.nan)
    todo = np.flatnonzero(~blank)
    size = max(1, min(int(batch_size or 1000), 5000))
    for start in range(0, len(todo), size):
        chunk = todo[start:start + size]
        rows = [(str(i), streets.iloc[i], cities.iloc[i], states.iloc[i], zips.iloc[i]) for i in chunk]
        found = census_batch(rows, benchmark)
        for i in chunk:
            result = found.get(str(i))
            if result:
                status[i], kind[i], matched[i], lat[i], lon[i] = result
    out = df.copy()
    out[unused_name(out, "latitude")] = lat
    out[unused_name(out, "longitude")] = lon
    out[unused_name(out, "geocode_status")] = pd.Series(status, index=df.index).astype("string")
    out[unused_name(out, "matched_address")] = pd.Series(matched, index=df.index).astype("string").replace("", pd.NA)
    out[unused_name(out, "match_type")] = pd.Series(kind, index=df.index).astype("string").replace("", pd.NA)
    return out


def geometry_vertices(geometry):
    if not geometry:
        return []
    kind, coords = geometry.get("type"), geometry.get("coordinates")
    if kind == "Point":
        return [coords]
    if kind in ("MultiPoint", "LineString"):
        return list(coords)
    if kind in ("MultiLineString", "Polygon"):
        return [p for part in coords for p in part]
    if kind == "MultiPolygon":
        return [p for poly in coords for part in poly for p in part]
    if kind == "GeometryCollection":
        return [p for g in geometry.get("geometries", []) for p in geometry_vertices(g)]
    return []


def ring_centroid(ring):
    pts = np.asarray(ring, dtype="float64")[:, :2]
    x0, y0, x1, y1 = pts[:-1, 0], pts[:-1, 1], pts[1:, 0], pts[1:, 1]
    cross = x0 * y1 - x1 * y0
    area = cross.sum() / 2
    if abs(area) < 1e-12:
        return 0.0, float(pts[:, 0].mean()), float(pts[:, 1].mean())
    return float(area), float(((x0 + x1) * cross).sum() / (6 * area)), float(((y0 + y1) * cross).sum() / (6 * area))


def ring_area(ring):
    pts = np.asarray(ring, dtype="float64")[:, :2]
    return float((pts[:-1, 0] * pts[1:, 1] - pts[1:, 0] * pts[:-1, 1]).sum() / 2)


def wind_clockwise(geometry):
    def fix(rings):
        return [ring if (ring_area(ring) <= 0) == (i == 0) else ring[::-1] for i, ring in enumerate(rings)]

    kind, coords = geometry.get("type"), geometry.get("coordinates")
    if kind == "Polygon":
        return {"type": kind, "coordinates": fix(coords)}
    if kind == "MultiPolygon":
        return {"type": kind, "coordinates": [fix(polygon) for polygon in coords]}
    return geometry


def geometry_centroid(geometry):
    if not geometry:
        return np.nan, np.nan
    kind, coords = geometry.get("type"), geometry.get("coordinates")
    if kind in ("Polygon", "MultiPolygon"):
        polygons = [coords] if kind == "Polygon" else coords
        total, sx, sy = 0.0, 0.0, 0.0
        for rings in polygons:
            for i, ring in enumerate(rings):
                area, cx, cy = ring_centroid(ring)
                weight = abs(area) * (1 if i == 0 else -1)
                total += weight
                sx += weight * cx
                sy += weight * cy
        if total > 0:
            return sx / total, sy / total
    points = np.asarray(geometry_vertices(geometry), dtype="float64")
    if not len(points):
        return np.nan, np.nan
    return float(points[:, 0].mean()), float(points[:, 1].mean())


def read_map_file(path, include_geometry=True):
    target = os.path.abspath(os.path.expanduser(path))
    extension = os.path.splitext(target)[1].lower()
    if extension in (".shp", ".dbf", ".shx"):
        import shapefile

        base = os.path.splitext(target)[0]
        projection = base + ".prj"
        if os.path.exists(projection):
            with open(projection, encoding="utf-8", errors="ignore") as fh:
                if "PROJCS" in fh.read().upper():
                    raise ValueError("This shapefile uses projected coordinates. Convert it to latitude and longitude (WGS 84) first.")
        reader = shapefile.Reader(base, encoding="utf-8", encodingErrors="replace")
        names = [f[0] for f in reader.fields[1:]]
        features = []
        for item in reader.shapeRecords():
            geometry = item.shape.__geo_interface__ if item.shape.shapeType != 0 else None
            features.append({"type": "Feature", "properties": dict(zip(names, list(item.record))), "geometry": geometry})
    else:
        with open(target, encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("type") == "FeatureCollection":
            features = data.get("features", [])
        elif data.get("type") == "Feature":
            features = [data]
        elif "coordinates" in data or data.get("type") == "GeometryCollection":
            features = [{"type": "Feature", "properties": {}, "geometry": data}]
        else:
            raise ValueError("This file is not GeoJSON")
    rows = []
    for feature in features:
        geometry = feature.get("geometry")
        pts = geometry_vertices(geometry)
        if pts:
            arr = np.asarray(pts, dtype="float64")
            if (np.abs(arr[:, 0]) > 180).any() or (np.abs(arr[:, 1]) > 90).any():
                raise ValueError("These coordinates are not latitude and longitude. Convert the file to WGS 84 first.")
        lon, lat = geometry_centroid(geometry)
        props = dict(feature.get("properties") or {})
        for extra in ("shape", "latitude", "longitude", "geometry"):
            if extra in props:
                props[extra + "_attr"] = props.pop(extra)
        row = {**props, "shape": geometry["type"] if geometry else None, "latitude": lat, "longitude": lon}
        if include_geometry:
            row["geometry"] = json.dumps(geometry, separators=(",", ":")) if geometry else None
        rows.append(row)
    return pd.DataFrame(rows)


def ring_contains(px, py, ring):
    pts = np.asarray(ring, dtype="float64")
    x1, y1, x2, y2 = pts[:-1, 0], pts[:-1, 1], pts[1:, 0], pts[1:, 1]
    slope = np.where(y2 == y1, 0.0, (x2 - x1) / np.where(y2 == y1, 1.0, y2 - y1))
    inside = np.zeros(len(px), dtype=bool)
    step = max(1, 2_000_000 // max(len(x1), 1))
    for start in range(0, len(px), step):
        x = px[start:start + step, None]
        y = py[start:start + step, None]
        crosses = ((y1 > y) != (y2 > y)) & (x < slope * (y - y1) + x1)
        inside[start:start + step] = crosses.sum(axis=1) % 2 == 1
    return inside


def parse_polygons(text):
    if not isinstance(text, str) or not text.strip():
        return []
    geometry = json.loads(text)
    kind, coords = geometry.get("type"), geometry.get("coordinates")
    if kind == "Polygon":
        polygons = [coords]
    elif kind == "MultiPolygon":
        polygons = coords
    else:
        return []
    out = []
    for rings in polygons:
        arrays = [np.asarray(r, dtype="float64")[:, :2] for r in rings]
        outer = arrays[0]
        out.append((outer[:, 0].min(), outer[:, 0].max(), outer[:, 1].min(), outer[:, 1].max(), arrays))
    return out


def find_region(points, regions, lat, lon, geometry="geometry", columns=None, keep_unmatched=True):
    a, o, ok = coordinate_arrays(points, lat, lon)
    found = np.full(len(points), -1, dtype="int64")
    for index, text in enumerate(regions[geometry]):
        for min_x, max_x, min_y, max_y, rings in parse_polygons(text):
            candidates = np.flatnonzero(ok & (found < 0) & (o >= min_x) & (o <= max_x) & (a >= min_y) & (a <= max_y))
            if not len(candidates):
                continue
            inside = ring_contains(o[candidates], a[candidates], rings[0])
            for hole in rings[1:]:
                inside &= ~ring_contains(o[candidates], a[candidates], hole)
            found[candidates[inside]] = index
    wanted = list(columns) if columns else [c for c in regions.columns if c != geometry]
    lookup = regions[wanted].reset_index(drop=True).assign(_r=np.arange(len(regions)))
    base = points.reset_index(drop=True).assign(_r=found)
    if not keep_unmatched:
        base = base[found >= 0]
    return base.merge(lookup, on="_r", how="left", suffixes=("", "_region")).drop(columns=["_r"]).reset_index(drop=True)


def region_ids(values, level):
    states = _state_lookup()
    out = []
    for v in values:
        if pd.isna(v):
            out.append(None)
            continue
        key = str(v).strip().lower()
        if key.endswith(".0"):
            key = key[:-2]
        if level == "states":
            hit = states.get(key)
            out.append(int(hit[2]) if hit else None)
        else:
            out.append(int(key) if key.isdigit() and 1000 <= int(key) <= 99999 else None)
    return out


def summarize_values(frame, agg):
    if agg == "count" or "value" not in frame:
        return frame.groupby("id", sort=False).size().rename("value").reset_index()
    func = {"sum": "sum", "mean": "mean", "median": "median", "min": "min", "max": "max", "first": "first"}[agg]
    return frame.groupby("id", sort=False)["value"].agg(func).reset_index()


def gaussian_blur(grid, sigma):
    if sigma <= 0:
        return grid
    radius = int(np.ceil(3 * sigma))
    total = np.exp(-0.5 * (np.arange(-radius, radius + 1) / sigma) ** 2).sum()

    def band(n):
        gap = np.arange(n)[:, None] - np.arange(n)[None, :]
        return np.where(np.abs(gap) <= radius, np.exp(-0.5 * (gap / sigma) ** 2), 0.0) / total

    return band(grid.shape[0]) @ grid @ band(grid.shape[1]).T


def density_cells(lat, lon, weight, agg, bins, smooth, basemap):
    ok = np.isfinite(lat) & np.isfinite(lon)
    if weight is not None and agg != "count":
        ok &= np.isfinite(weight)
    lat, lon = lat[ok], lon[ok]
    if len(lat) == 0:
        return []
    weight = weight[ok] if weight is not None and agg != "count" else None
    squeeze = np.cos(np.radians(37.5)) if basemap == "us" else 1.0
    step = (59.0 * squeeze if basemap == "us" else 360.0) / bins
    x, y = lon * squeeze, lat + 90.0
    gx = np.floor((x + 180.0 * squeeze) / step).astype(int)
    gy = np.floor(y / step).astype(int)
    pad = int(np.ceil(3 * smooth)) if smooth > 0 else 0
    cols = int(gx.max() - gx.min()) + 1 + 2 * pad
    rows = int(gy.max() - gy.min()) + 1 + 2 * pad
    if cols * rows > 160000:
        raise ValueError("These points cover too much of the map for this many cells. Use fewer cells across, pick the World background, or filter the points first.")
    ix = gx - gx.min() + pad
    iy = gy - gy.min() + pad
    counts = np.zeros((rows, cols))
    np.add.at(counts, (iy, ix), 1.0)
    if weight is None:
        shown = gaussian_blur(counts, smooth)
        keep = (np.abs(shown) > (np.abs(shown).max() * 1e-3 if smooth > 0 else 0.0)) | (counts > 0)
    else:
        sums = np.zeros((rows, cols))
        np.add.at(sums, (iy, ix), weight)
        if agg == "mean":
            support = gaussian_blur(counts, smooth)
            keep = support >= (0.05 if smooth > 0 else 0.5)
            shown = np.divide(gaussian_blur(sums, smooth), support, out=np.zeros_like(support), where=keep)
        else:
            shown = gaussian_blur(sums, smooth)
            keep = (np.abs(shown) > (np.abs(shown).max() * 1e-3 if smooth > 0 else 0.0)) | (counts > 0)
    cells = []
    for r, c in zip(*np.nonzero(keep)):
        west = (gx.min() - pad + c) * step / squeeze - 180.0
        south = (gy.min() - pad + r) * step - 90.0
        w, e = max(west, -180.0), min(west + step / squeeze, 180.0)
        s, n = max(south, -90.0), min(south + step, 90.0)
        if w < e and s < n:
            cells.append((round(w, 4), round(e, 4), round(s, 4), round(n, 4), float(shown[r, c]), int(counts[r, c])))
    return cells


def map_chart(df, kind="points", lat=None, lon=None, region=None, value=None, agg="sum", color=None, size=None, tooltip=None, geometry="geometry", title="", scheme="blues", basemap="us", max_rows=5000, bins=40, smooth=1.0, color_scale="linear"):
    def vl_type(col):
        s = df[col]
        if pd.api.types.is_datetime64_any_dtype(s):
            return "temporal"
        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            return "quantitative"
        return "nominal"

    layers, plotted, missed = [], 0, 0
    limit = int(max_rows)
    outline = {"mark": {"type": "geoshape", "fill": "#eceff3", "stroke": "#b9c0ca", "strokeWidth": 0.5}}
    if kind == "points":
        needed = list(dict.fromkeys(c for c in [lat, lon, color, size] + list(tooltip or []) if c))
        a, o, ok = coordinate_arrays(df, lat, lon)
        data = df.loc[ok, needed].head(limit)
        if color and vl_type(color) == "nominal":
            data = data.assign(**{color: data[color].astype("string").fillna("(blank)")})
        plotted, missed = len(data), int((~ok).sum())
        if basemap == "world":
            layers.append({"data": {"url": WORLD_BASEMAP, "format": {"type": "topojson", "feature": "countries"}}, **outline})
            projection = {"type": "equalEarth"}
        else:
            layers.append({"data": {"url": US_BASEMAP, "format": {"type": "topojson", "feature": "states"}}, **outline})
            projection = {"type": "albersUsa"}
        encoding = {"longitude": {"field": lon, "type": "quantitative"}, "latitude": {"field": lat, "type": "quantitative"}}
        if color:
            encoding["color"] = {"field": color, "type": vl_type(color), "title": color, **({"scale": {"scheme": scheme}} if vl_type(color) == "quantitative" else {})}
        if size:
            encoding["size"] = {"field": size, "type": "quantitative", "title": size, "scale": {"range": [20, 700]}}
        encoding["tooltip"] = [{"field": c, "type": vl_type(c)} for c in needed]
        layers.append({"data": {"values": json.loads(data.to_json(orient="records", date_format="iso"))}, "mark": {"type": "circle", "opacity": 0.75, "stroke": "#ffffff", "strokeWidth": 0.5, **({} if size else {"size": 60})}, "encoding": encoding})
        default_title = "Places"
    elif kind == "density":
        if not 5 <= bins <= 150:
            raise ValueError("Use between 5 and 150 cells across")
        if not 0 <= smooth <= 10:
            raise ValueError("Smooth by between 0 and 10 cells")
        a, o, ok = coordinate_arrays(df, lat, lon)
        weight = pd.to_numeric(df[value], errors="coerce").to_numpy(dtype="float64", na_value=np.nan) if value else None
        weighted = weight is not None and agg != "count"
        used = ok & np.isfinite(weight) if weighted else ok
        plotted, missed = int(used.sum()), int((~used).sum())
        cells = density_cells(a[used], o[used], weight[used] if weighted else None, agg, int(bins), float(smooth), basemap)
        features = [
            {"type": "Feature", "properties": {"value": float(f"{shown:.6g}"), "rows": rows}, "geometry": {"type": "Polygon", "coordinates": [[[w, s], [w, n], [e, n], [e, s], [w, s]]]}}
            for w, e, s, n, shown, rows in cells
        ]
        if basemap == "world":
            outline_source = {"url": WORLD_BASEMAP, "format": {"type": "topojson", "feature": "countries"}}
            projection = {"type": "equalEarth"}
        else:
            outline_source = {"url": US_BASEMAP, "format": {"type": "topojson", "feature": "states"}}
            projection = {"type": "albersUsa"}
        what = "rows" if not weighted else f"{'average' if agg == 'mean' else 'sum'} of {value}"
        legend = f"Smoothed {what}" if smooth > 0 else what.capitalize()
        scale = {"scheme": scheme}
        if color_scale == "sqrt" and all(f["properties"]["value"] >= 0 for f in features):
            scale["type"] = "sqrt"
        layers.append({"data": outline_source, **outline})
        if features:
            layers.append({
                "data": {"values": {"type": "FeatureCollection", "features": features}, "format": {"type": "json", "property": "features"}},
                "mark": {"type": "geoshape", "opacity": 0.85, "strokeWidth": 0},
                "encoding": {
                    "color": {"field": "properties.value", "type": "quantitative", "title": legend, "scale": scale},
                    "tooltip": [{"field": "properties.value", "type": "quantitative", "title": legend}, {"field": "properties.rows", "type": "quantitative", "title": "Rows in cell"}],
                },
            })
        layers.append({"data": outline_source, "mark": {"type": "geoshape", "fill": None, "stroke": "#7b8594", "strokeWidth": 0.5}})
        default_title = f"Heat map of {value}" if weighted else "Heat map of rows"
    elif kind in ("states", "counties"):
        ids = region_ids(df[region], kind)
        frame = pd.DataFrame({"id": ids, "label": df[region].astype("string")})
        if value:
            frame["value"] = pd.to_numeric(df[value], errors="coerce")
        valid = frame["id"].notna()
        missed = int((~valid).sum())
        frame = frame[valid]
        names = frame.groupby("id", sort=False)["label"].first()
        rows = summarize_values(frame.astype({"id": "int64"}), agg if value else "count")
        rows["name"] = rows["id"].map(names)
        rows = rows.where(rows.notna(), None)
        plotted = len(rows)
        feature = "states" if kind == "states" else "counties"
        layers.append({"data": {"url": US_BASEMAP, "format": {"type": "topojson", "feature": "states"}}, **outline})
        layers.append({
            "data": {"url": US_BASEMAP, "format": {"type": "topojson", "feature": feature}},
            "transform": [{"lookup": "id", "from": {"data": {"values": json.loads(rows.to_json(orient="records"))}, "key": "id", "fields": ["value", "name"]}}, {"filter": "isValid(datum.value)"}],
            "mark": {"type": "geoshape", "stroke": "#ffffff", "strokeWidth": 0.3},
            "encoding": {"color": {"field": "value", "type": "quantitative", "title": f"{agg} of {value}" if value else "Rows", "scale": {"scheme": scheme}}, "tooltip": [{"field": "name", "type": "nominal", "title": "Region"}, {"field": "value", "type": "quantitative", "title": "Value"}]},
        })
        projection = {"type": "albersUsa"}
        default_title = f"{value or 'Rows'} by {kind[:-1]}"
    else:
        extras = list(dict.fromkeys(c for c in [value] + list(tooltip or []) if c))
        features, vertices = [], 0
        subset = df.head(limit)
        records = json.loads(subset[extras].to_json(orient="records", date_format="iso")) if extras else [{} for _ in range(len(subset))]
        for position, text in enumerate(subset[geometry]):
            if not isinstance(text, str) or not text.strip():
                missed += 1
                continue
            shape = wind_clockwise(json.loads(text))
            vertices += len(geometry_vertices(shape))
            features.append({"type": "Feature", "properties": records[position], "geometry": shape})
        if vertices > 1_500_000:
            raise ValueError("These shapes have too many points to draw. Use a simpler map file or keep fewer rows.")
        plotted = len(features)
        encoding = {"tooltip": [{"field": f"properties.{c}", "type": vl_type(c), "title": c} for c in extras]}
        if value:
            encoding["color"] = {"field": f"properties.{value}", "type": "quantitative", "title": value, "scale": {"scheme": scheme}}
        layers.append({"data": {"values": {"type": "FeatureCollection", "features": features}, "format": {"type": "json", "property": "features"}}, "mark": {"type": "geoshape", "stroke": "#ffffff", "strokeWidth": 0.4, **({} if value else {"fill": "#cfd8e3"})}, "encoding": encoding})
        projection = {"type": "mercator"}
        default_title = f"{value} by region" if value else "Regions"
    spec = {"$schema": "https://vega.github.io/schema/vega-lite/v6.json", "title": title or default_title, "width": "container", "height": 420, "projection": projection, "layer": layers}
    return pd.DataFrame([{"Kind": kind, "Title": spec["title"], "Rows plotted": plotted, "Rows in data": len(df), "Rows not drawn": missed, "Vega-Lite": json.dumps(spec)}])
