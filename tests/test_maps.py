import io
import json
import math
import subprocess
import sys
import urllib.request

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics.pairwise import haversine_distances

from snek import fx, geo, runtime
from snek.codegen import export_script
from snek.engine import Engine
from tests.test_tools import chain, err, out, run, workflow

R = 6371.0088

CITIES = pd.DataFrame({
    "city": ["Omaha", "Lincoln", "Des Moines", "Kansas City", "Denver"],
    "lat": [41.2565, 40.8136, 41.5868, 39.0997, 39.7392],
    "lon": [-95.9345, -96.7026, -93.6250, -94.5786, -104.9903],
    "pop": [486, 292, 214, 509, 716],
})
STORES = pd.DataFrame({"store": ["A", "B", "C"], "lat": [41.0, 39.5, 45.0], "lon": [-96.0, -95.0, -100.0]})


def csv_text(df):
    return df.to_csv(index=False)


def pairwise_km(a, b):
    return haversine_distances(np.radians(a), np.radians(b)) * R


def test_map_values_pairs_and_separators():
    assert runtime.parse_mapping("TX = Texas\nIA, Iowa\nNE\tNebraska\n1 -> one\n\n") == [("TX", "Texas"), ("IA", "Iowa"), ("NE", "Nebraska"), ("1", "one")]
    assert runtime.parse_mapping("a,b = x") == [("a,b", "x")]
    assert runtime.parse_mapping("a, b, c") == [("a", "b, c")]
    with pytest.raises(ValueError, match="Line 2"):
        runtime.parse_mapping("a = b\nnothing here")


def test_map_values_modes():
    df = pd.DataFrame({"code": ["TX", " ia ", "NE", "XX", None], "n": [1, 2.0, 3, 4, 5]})
    out_df = runtime.map_values(df, "code", "TX = Texas\nIA = Iowa\nNE = Nebraska", ignore_case=True)
    assert out_df["code"].tolist()[:4] == ["Texas", "Iowa", "Nebraska", "XX"]
    assert pd.isna(out_df["code"].iloc[4])
    assert df["code"].tolist()[1] == " ia "
    assert runtime.map_values(df, "code", "TX = Texas", unmatched="default", default="Other", ignore_case=True)["code"].tolist()[:4] == ["Texas", "Other", "Other", "Other"]
    assert runtime.map_values(df, "code", "TX = Texas", unmatched="blank")["code"].isna().tolist() == [False, True, True, True, True]
    assert runtime.map_values(df, "code", "TX = Texas", trim=False, ignore_case=True)["code"].tolist()[1] == " ia "
    added = runtime.map_values(df, "code", "TX = Texas", output="long")
    assert added["code"].tolist()[0] == "TX" and added["long"].tolist()[0] == "Texas"


def test_map_values_numbers_match_whole_numbers_and_results_become_numbers():
    df = pd.DataFrame({"n": [1.0, 2.0, 3.5, 7]})
    result = runtime.map_values(df, "n", "1 = 10\n2 = 20\n3.5 = 35", unmatched="default", default="0")
    assert result["n"].tolist() == [10, 20, 35, 0]
    assert pd.api.types.is_numeric_dtype(result["n"])
    names = runtime.map_values(df, "n", "1 = one\n2 = two")
    assert names["n"].astype(str).tolist() == ["one", "two", "3.5", "7.0"]


def test_map_values_first_pair_wins():
    df = pd.DataFrame({"c": ["a"]})
    assert runtime.map_values(df, "c", "a = first\na = second")["c"].tolist() == ["first"]


def test_state_table_is_complete_and_unique():
    table = fx._state_table()
    assert len(table) == 57
    assert len({t[0] for t in table}) == 57 and len({t[1] for t in table}) == 57 and len({t[2] for t in table}) == 57
    lookup = {t[0]: t for t in table}
    assert lookup["DC"][1:] == ("District of Columbia", "11") and lookup["PR"][2] == "72" and lookup["TX"][2] == "48" and lookup["CA"][2] == "06"


def test_distance_matches_an_independent_haversine_in_every_unit():
    df = pd.DataFrame({"a": CITIES["lat"], "b": CITIES["lon"], "c": CITIES["lat"].iloc[::-1].to_numpy(), "d": CITIES["lon"].iloc[::-1].to_numpy()})
    want = np.diag(pairwise_km(df[["a", "b"]].to_numpy(), df[["c", "d"]].to_numpy()))
    for unit, per_km in (("km", 1), ("mi", 1 / 1.609344), ("m", 1000), ("nmi", 1 / 1.852), ("ft", 1000 / 0.3048), ("yd", 1000 / 0.9144)):
        got = geo.distance_between(df, "a", "b", "c", "d", unit=unit)["distance"].to_numpy()
        assert got == pytest.approx(want * per_km, rel=1e-9)
    with pytest.raises(ValueError):
        geo.distance_between(df, "a", "b", "c", "d", unit="parsec")


def test_distance_gives_blanks_for_bad_coordinates_and_adds_a_bearing():
    df = pd.DataFrame({"a": [0, 95, np.nan, 10], "b": [0, 0, 0, 0], "c": [0, 0, 0, 0], "d": [90, 0, 0, 0]})
    result = geo.distance_between(df, "a", "b", "c", "d", unit="km", name="km", bearing="dir")
    assert result["km"].isna().tolist() == [False, True, True, False]
    assert result["dir"].round(6).tolist()[0] == 90.0 and result["dir"].round(6).tolist()[3] == 180.0
    assert "km" not in df.columns


def test_distance_agrees_with_the_function():
    assert fx.DISTANCE(41.2565, -95.9345, 39.0997, -94.5786, "mi") == pytest.approx(geo.distance_between(pd.DataFrame({"a": [41.2565], "b": [-95.9345], "c": [39.0997], "d": [-94.5786]}), "a", "b", "c", "d")["distance"].iloc[0])


def brute_nearest(targets, places, count):
    d = pairwise_km(targets[["lat", "lon"]].to_numpy(), places[["lat", "lon"]].to_numpy()) / 1.609344
    return [list(np.argsort(row, kind="stable")[:count]) for row in d], d


def test_find_nearest_matches_a_brute_force_search():
    rng = np.random.default_rng(4)
    targets = pd.DataFrame({"id": range(40), "lat": rng.uniform(30, 48, 40), "lon": rng.uniform(-120, -75, 40)})
    places = pd.DataFrame({"name": [f"p{i}" for i in range(25)], "lat": rng.uniform(30, 48, 25), "lon": rng.uniform(-120, -75, 25)})
    result = geo.find_nearest(targets, places, "lat", "lon", "lat", "lon", count=3)
    order, d = brute_nearest(targets, places, 3)
    assert len(result) == 120
    for i in range(40):
        rows = result[result["id"] == i].sort_values("nearest_rank")
        assert rows["name"].tolist() == [f"p{j}" for j in order[i]]
        assert rows["distance"].tolist() == pytest.approx([d[i][j] for j in order[i]], rel=1e-9)
        assert rows["nearest_rank"].tolist() == [1, 2, 3]
    assert {"lat", "lon", "lat_place", "lon_place"} <= set(result.columns)


def test_find_nearest_limits_and_unmatched_rows():
    near = geo.find_nearest(STORES, CITIES, "lat", "lon", "lat", "lon", count=1, max_distance=100, unit="mi")
    assert near["store"].tolist() == ["A", "B", "C"]
    assert near["city"].tolist()[0] == "Omaha" and pd.isna(near["city"].iloc[2]) and pd.isna(near["distance"].iloc[2]) and pd.isna(near["nearest_rank"].iloc[2])
    only = geo.find_nearest(STORES, CITIES, "lat", "lon", "lat", "lon", count=1, max_distance=100, keep_unmatched=False)
    assert only["store"].tolist() == ["A", "B"]
    assert len(geo.find_nearest(STORES, CITIES, "lat", "lon", "lat", "lon", count=10)) == 15
    within = geo.find_nearest(STORES, CITIES, "lat", "lon", "lat", "lon", count=0, max_distance=150, unit="mi")
    miles = pairwise_km(STORES[["lat", "lon"]].to_numpy(), CITIES[["lat", "lon"]].to_numpy()) / 1.609344
    for i, store in enumerate(STORES["store"]):
        expected = [CITIES["city"][j] for j in np.argsort(miles[i]) if miles[i][j] <= 150]
        got = within[within["store"] == store]["city"].tolist()
        assert got == (expected or [None]) or (not expected and pd.isna(got[0]))
    with pytest.raises(ValueError):
        geo.find_nearest(STORES, CITIES, "lat", "lon", "lat", "lon", count=0, max_distance=0)


def test_find_nearest_everything_within_a_distance_is_sorted_and_complete():
    result = geo.find_nearest(STORES.head(1), CITIES, "lat", "lon", "lat", "lon", count=0, max_distance=200, unit="mi", columns=["city"])
    d = pairwise_km(STORES[["lat", "lon"]].head(1).to_numpy(), CITIES[["lat", "lon"]].to_numpy())[0] / 1.609344
    expected = [CITIES["city"][i] for i in np.argsort(d) if d[i] <= 200]
    assert result["city"].tolist() == expected
    assert result["nearest_rank"].tolist() == list(range(1, len(expected) + 1))
    assert list(result.columns) == ["store", "lat", "lon", "nearest_rank", "distance", "city"]


def test_find_nearest_skips_bad_coordinates_without_failing():
    targets = pd.DataFrame({"lat": [41.0, np.nan, 200.0], "lon": [-96.0, -96.0, 0.0]})
    result = geo.find_nearest(targets, CITIES, "lat", "lon", "lat", "lon", count=1)
    assert len(result) == 3 and result["city"].isna().tolist() == [False, True, True]
    assert len(geo.find_nearest(targets, CITIES, "lat", "lon", "lat", "lon", count=1, keep_unmatched=False)) == 1


class FakeResponse:
    def __init__(self, text):
        self.data = text.encode()

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def census_reply(request):
    body = request.data.decode()
    rows = [line for line in body.split("\r\n") if line and not line.startswith("--") and not line.startswith("Content") and line != "Public_AR_Current"]
    lines = []
    for record in __import__("csv").reader(io.StringIO("\n".join(rows))):
        ident, street = record[0], record[1]
        if "Pennsylvania" in street:
            lines.append(f'"{ident}","{street}","Match","Exact","1600 PENNSYLVANIA AVE NW, WASHINGTON, DC, 20500","-77.035189204737,38.898702605246","76225813","L"')
        elif "Tie" in street:
            lines.append(f'"{ident}","{street}","Tie"')
        else:
            lines.append(f'"{ident}","{street}","No_Match"')
    return "\n".join(lines) + "\n"


@pytest.fixture
def census(monkeypatch):
    seen = []

    def fake(request, timeout=0):
        seen.append(request)
        return FakeResponse(census_reply(request))

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    monkeypatch.setattr(geo.time, "sleep", lambda s: None)
    return seen


def test_geocode_one_column_parts_and_blank_rows(census):
    df = pd.DataFrame({"addr": ["1600 Pennsylvania Ave NW, Washington, DC 20500", "1 Nowhere Lane, Atlantis", None, "Tie Road"], "who": list("abcd")})
    result = geo.geocode_addresses(df, address="addr")
    assert result["latitude"].round(6).tolist()[0] == 38.898703 and result["longitude"].round(6).tolist()[0] == -77.035189
    assert result["geocode_status"].tolist() == ["Match", "No_Match", "Blank", "Tie"]
    assert result["matched_address"].tolist()[0].startswith("1600 PENNSYLVANIA") and pd.isna(result["matched_address"].iloc[1])
    assert result["match_type"].tolist()[0] == "Exact"
    assert result["latitude"].isna().tolist() == [False, True, True, True]
    assert len(census) == 1
    body = census[0].data.decode()
    assert 'name="benchmark"' in body and "Public_AR_Current" in body and "multipart/form-data" in census[0].headers["Content-type"]
    assert "1 Nowhere Lane, Atlantis" in body
    parts = pd.DataFrame({"s": ["1600 Pennsylvania Ave NW"], "c": ["Washington"], "st": ["DC"], "z": [20500]})
    result = geo.geocode_addresses(parts, street="s", city="c", state="st", zip_code="z")
    assert result["geocode_status"].tolist() == ["Match"]
    assert "Washington" in census[1].data.decode() and "20500" in census[1].data.decode()


def test_geocode_sends_batches_and_keeps_existing_columns(census):
    df = pd.DataFrame({"addr": ["1600 Pennsylvania Ave NW"] * 5, "latitude": range(5)})
    result = geo.geocode_addresses(df, address="addr", batch_size=2)
    assert len(census) == 3
    assert "latitude" in result.columns and "latitude_new" in result.columns and result["latitude"].tolist() == [0, 1, 2, 3, 4]
    assert result["geocode_status"].tolist() == ["Match"] * 5


def test_geocode_reports_a_service_that_does_not_answer(monkeypatch):
    def broken(request, timeout=0):
        raise urllib.error.URLError("offline")

    import urllib.error

    monkeypatch.setattr(urllib.request, "urlopen", broken)
    monkeypatch.setattr(geo.time, "sleep", lambda s: None)
    with pytest.raises(ConnectionError, match="Census geocoder"):
        geo.geocode_addresses(pd.DataFrame({"a": ["1 Main St"]}), address="a")


SQUARE = {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]}
DONUT = {"type": "Polygon", "coordinates": [[[20, 0], [40, 0], [40, 20], [20, 20], [20, 0]], [[25, 5], [35, 5], [35, 15], [25, 15], [25, 5]]]}
ISLANDS = {"type": "MultiPolygon", "coordinates": [[[[50, 0], [55, 0], [55, 5], [50, 5], [50, 0]]], [[[60, 0], [65, 0], [65, 5], [60, 5], [60, 0]]]]}
BIG = {"type": "Polygon", "coordinates": [[[-5, -5], [12, -5], [12, 12], [-5, 12], [-5, -5]]]}


def collection(*features):
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": p, "geometry": g} for p, g in features]}


def write_geojson(path, data):
    path.write_text(json.dumps(data))
    return str(path)


def test_read_geojson_feature_collection(tmp_path):
    path = write_geojson(tmp_path / "r.geojson", collection(({"name": "Square", "pop": 5}, SQUARE), ({"name": "Donut", "geometry": "clash", "latitude": 1}, DONUT), ({"name": "Nothing"}, None)))
    df = geo.read_map_file(path)
    assert df["name"].tolist() == ["Square", "Donut", "Nothing"]
    assert df["shape"].iloc[:2].tolist() == ["Polygon", "Polygon"] and pd.isna(df["shape"].iloc[2])
    assert df["latitude"].iloc[0] == pytest.approx(5.0) and df["longitude"].iloc[0] == pytest.approx(5.0)
    assert df["longitude"].iloc[1] == pytest.approx(30.0) and df["latitude"].iloc[1] == pytest.approx(10.0)
    assert pd.isna(df["latitude"].iloc[2]) and pd.isna(df["geometry"].iloc[2])
    assert df["geometry_attr"].iloc[1] == "clash" and df["latitude_attr"].iloc[1] == 1
    assert json.loads(df["geometry"].iloc[0])["type"] == "Polygon"
    assert "geometry" not in geo.read_map_file(path, include_geometry=False).columns


def test_read_geojson_single_feature_bare_geometry_and_points(tmp_path):
    assert len(geo.read_map_file(write_geojson(tmp_path / "f.json", {"type": "Feature", "properties": {"a": 1}, "geometry": SQUARE}))) == 1
    assert geo.read_map_file(write_geojson(tmp_path / "g.json", SQUARE))["shape"].tolist() == ["Polygon"]
    points = geo.read_map_file(write_geojson(tmp_path / "p.json", collection(({"n": "a"}, {"type": "Point", "coordinates": [-96.0, 41.0]}), ({"n": "b"}, {"type": "MultiPoint", "coordinates": [[0, 0], [2, 4]]}), ({"n": "c"}, {"type": "LineString", "coordinates": [[0, 0], [4, 2]]}))))
    assert points["longitude"].tolist() == [-96.0, 1.0, 2.0] and points["latitude"].tolist() == [41.0, 2.0, 1.0]
    with pytest.raises(ValueError, match="not GeoJSON"):
        geo.read_map_file(write_geojson(tmp_path / "x.json", {"hello": 1}))


def test_read_map_file_rejects_projected_coordinates(tmp_path):
    big = {"type": "Polygon", "coordinates": [[[500000, 4000000], [510000, 4000000], [510000, 4010000], [500000, 4000000]]]}
    with pytest.raises(ValueError, match="latitude and longitude"):
        geo.read_map_file(write_geojson(tmp_path / "utm.geojson", collection(({}, big))))


def write_shapefile(tmp_path, name="regions", prj=None):
    import shapefile

    base = str(tmp_path / name)
    with shapefile.Writer(base, shapeType=shapefile.POLYGON) as w:
        w.field("NAME", "C", size=30)
        w.field("POP", "N", decimal=0)
        w.poly([[[0, 0], [0, 10], [10, 10], [10, 0], [0, 0]]])
        w.record("Square", 5)
        w.poly([[[20, 0], [20, 20], [40, 20], [40, 0], [20, 0]], [[25, 5], [35, 5], [35, 15], [25, 15], [25, 5]]])
        w.record("Donut", 7)
    if prj:
        (tmp_path / f"{name}.prj").write_text(prj)
    return base + ".shp"


def test_read_shapefile_with_attributes_and_geometry(tmp_path):
    df = geo.read_map_file(write_shapefile(tmp_path))
    assert df["NAME"].tolist() == ["Square", "Donut"] and df["POP"].tolist() == [5, 7]
    assert df["shape"].tolist() == ["Polygon", "Polygon"]
    assert df["longitude"].iloc[0] == pytest.approx(5.0)
    inside = geo.find_region(pd.DataFrame({"lat": [5, 10, 10], "lon": [5, 30, 22]}), df, "lat", "lon")
    assert inside["NAME"].isna().tolist() == [False, True, False] and inside["NAME"].iloc[0] == "Square" and inside["NAME"].iloc[2] == "Donut" and inside["POP"].iloc[2] == 7


def test_read_shapefile_warns_about_a_projected_prj(tmp_path):
    path = write_shapefile(tmp_path, "proj", 'PROJCS["NAD_1983_UTM_Zone_14N",GEOGCS["GCS_North_American_1983"]]')
    with pytest.raises(ValueError, match="projected"):
        geo.read_map_file(path)
    ok = write_shapefile(tmp_path, "geo", 'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984"]]')
    assert len(geo.read_map_file(ok)) == 2


def winding_contains(poly, x, y):
    wn = 0
    n = len(poly) - 1
    for i in range(n):
        x1, y1, x2, y2 = poly[i][0], poly[i][1], poly[i + 1][0], poly[i + 1][1]
        cross = (x2 - x1) * (y - y1) - (x - x1) * (y2 - y1)
        if y1 <= y < y2 and cross > 0:
            wn += 1
        elif y2 <= y < y1 and cross < 0:
            wn -= 1
    return wn != 0


def test_ring_contains_matches_a_winding_number_check_on_a_concave_shape():
    star = [[0, 0], [8, 3], [10, 10], [4, 6], [-3, 9], [1, 3], [0, 0]]
    rng = np.random.default_rng(11)
    px, py = rng.uniform(-5, 12, 600), rng.uniform(-2, 12, 600)
    got = geo.ring_contains(px, py, star)
    want = np.array([winding_contains(star, x, y) for x, y in zip(px, py)])
    assert (got == want).all() and got.any() and not got.all()


def test_find_region_holes_islands_overlaps_and_misses():
    frame = pd.DataFrame({
        "name": ["Big", "Square", "Donut", "Islands", "Empty", "Point"],
        "geometry": [json.dumps(BIG), json.dumps(SQUARE), json.dumps(DONUT), json.dumps(ISLANDS), None, json.dumps({"type": "Point", "coordinates": [1, 1]})],
        "rank": [1, 2, 3, 4, 5, 6],
    })
    points = pd.DataFrame({"id": range(9), "lat": [5, 11, 10, 10, 2, 2, 50, np.nan, 2], "lon": [5, 11, 22, 30, 52, 62, 50, 5, 57]})
    result = geo.find_region(points, frame, "lat", "lon")
    assert result["name"].iloc[:3].tolist() == ["Big", "Big", "Donut"] and result["name"].iloc[4:6].tolist() == ["Islands", "Islands"]
    assert result["name"].isna().tolist() == [False, False, False, True, False, False, True, True, True]
    assert result["rank"].tolist()[:3] == [1, 1, 3]
    assert list(result.columns) == ["id", "lat", "lon", "name", "rank"]
    assert len(geo.find_region(points, frame, "lat", "lon", keep_unmatched=False)) == 5
    narrowed = geo.find_region(points, frame, "lat", "lon", columns=["rank"])
    assert list(narrowed.columns) == ["id", "lat", "lon", "rank"]
    clash = geo.find_region(points.rename(columns={"id": "name"}), frame, "lat", "lon")
    assert "name_region" in clash.columns and clash["name"].tolist() == list(range(9))


def test_find_region_with_many_points_agrees_with_the_winding_check():
    ring = [[0, 0], [30, 5], [28, 20], [15, 12], [5, 25], [-4, 14], [0, 0]]
    frame = pd.DataFrame({"geometry": [json.dumps({"type": "Polygon", "coordinates": [ring]})], "tag": ["in"]})
    rng = np.random.default_rng(2)
    points = pd.DataFrame({"lat": rng.uniform(-5, 30, 800), "lon": rng.uniform(-6, 32, 800)})
    result = geo.find_region(points, frame, "lat", "lon")
    want = [winding_contains(ring, lon, lat) for lat, lon in zip(points["lat"], points["lon"])]
    assert result["tag"].notna().tolist() == want


def test_map_chart_points():
    result = geo.map_chart(CITIES.assign(bad=1), "points", lat="lat", lon="lon", color="pop", size="pop", tooltip=["city"], title="Cities")
    row = result.iloc[0]
    assert row["Kind"] == "points" and row["Rows plotted"] == 5 and row["Rows not drawn"] == 0
    spec = json.loads(row["Vega-Lite"])
    assert spec["title"] == "Cities" and spec["projection"]["type"] == "albersUsa" and len(spec["layer"]) == 2
    assert spec["layer"][0]["data"]["format"] == {"type": "topojson", "feature": "states"} and "vega-datasets@2.11.0/data/us-10m.json" in spec["layer"][0]["data"]["url"]
    layer = spec["layer"][1]
    assert layer["encoding"]["longitude"]["field"] == "lon" and layer["encoding"]["size"]["field"] == "pop" and layer["encoding"]["color"]["scale"] == {"scheme": "blues"}
    assert [t["field"] for t in layer["encoding"]["tooltip"]] == ["lat", "lon", "pop", "city"]
    assert len(layer["data"]["values"]) == 5 and "bad" not in layer["data"]["values"][0]
    world = json.loads(geo.map_chart(CITIES, "points", lat="lat", lon="lon", basemap="world").iloc[0]["Vega-Lite"])
    assert world["projection"]["type"] == "equalEarth" and world["layer"][0]["data"]["format"]["feature"] == "countries"


def test_map_chart_points_label_blank_categories():
    df = pd.DataFrame({"lat": [40.0, 41.0, 42.0], "lon": [-96.0, -95.0, -94.0], "zone": ["A", None, "B"]})
    values = json.loads(geo.map_chart(df, "points", lat="lat", lon="lon", color="zone").iloc[0]["Vega-Lite"])["layer"][1]["data"]["values"]
    assert [v["zone"] for v in values] == ["A", "(blank)", "B"]


def test_map_chart_points_skips_bad_rows_and_respects_the_row_limit():
    df = pd.DataFrame({"a": [10.0, 200.0, np.nan, 30.0, 40.0], "b": [1.0, 1.0, 1.0, 1.0, 1.0]})
    row = geo.map_chart(df, "points", lat="a", lon="b", max_rows=2).iloc[0]
    assert row["Rows plotted"] == 2 and row["Rows not drawn"] == 2 and row["Rows in data"] == 5


def test_map_chart_states_accepts_names_codes_and_fips_and_combines_rows():
    df = pd.DataFrame({"st": ["TX", "Texas", "48", "nebraska", "NE", "ZZ", None, 31], "v": [1, 2, 3, 10, 20, 99, 5, 1]})
    row = geo.map_chart(df, "states", region="st", value="v").iloc[0]
    spec = json.loads(row["Vega-Lite"])
    shaded = spec["layer"][1]
    rows = {r["id"]: r for r in shaded["transform"][0]["from"]["data"]["values"]}
    assert rows[48]["value"] == 6 and rows[31]["value"] == 31 and rows[48]["name"] == "TX"
    assert row["Rows plotted"] == 2 and row["Rows not drawn"] == 2
    assert shaded["transform"][1] == {"filter": "isValid(datum.value)"} and shaded["data"]["format"]["feature"] == "states"
    mean = json.loads(geo.map_chart(df, "states", region="st", value="v", agg="mean").iloc[0]["Vega-Lite"])["layer"][1]["transform"][0]["from"]["data"]["values"]
    assert {r["id"]: r["value"] for r in mean}[48] == 2
    counted = json.loads(geo.map_chart(df, "states", region="st").iloc[0]["Vega-Lite"])["layer"][1]["transform"][0]["from"]["data"]["values"]
    assert {r["id"]: r["value"] for r in counted}[48] == 3


def test_map_chart_counties_use_five_digit_codes():
    df = pd.DataFrame({"fips": ["48453", 31055, "1001", "999", "abc", None], "v": [1, 2, 3, 4, 5, 6]})
    row = geo.map_chart(df, "counties", region="fips", value="v").iloc[0]
    shaded = json.loads(row["Vega-Lite"])["layer"][1]
    assert shaded["data"]["format"]["feature"] == "counties"
    assert {r["id"] for r in shaded["transform"][0]["from"]["data"]["values"]} == {48453, 31055, 1001}
    assert row["Rows plotted"] == 3 and row["Rows not drawn"] == 3


def test_map_chart_regions_from_a_map_file(tmp_path):
    regions = geo.read_map_file(write_geojson(tmp_path / "r.geojson", collection(({"name": "Square", "score": 3.5}, SQUARE), ({"name": "Donut", "score": 8.0}, DONUT), ({"name": "Gap", "score": 1.0}, None))))
    row = geo.map_chart(regions, "regions", value="score", tooltip=["name"]).iloc[0]
    spec = json.loads(row["Vega-Lite"])
    layer = spec["layer"][0]
    assert spec["projection"] == {"type": "mercator"} and layer["data"]["format"] == {"type": "json", "property": "features"}
    features = layer["data"]["values"]["features"]
    assert [f["properties"]["name"] for f in features] == ["Square", "Donut"] and features[1]["properties"]["score"] == 8.0
    assert row["Rows plotted"] == 2 and row["Rows not drawn"] == 1
    assert layer["encoding"]["color"]["field"] == "properties.score"
    plain = json.loads(geo.map_chart(regions, "regions").iloc[0]["Vega-Lite"])["layer"][0]
    assert plain["mark"]["fill"] == "#cfd8e3" and "color" not in plain["encoding"]


def test_map_chart_regions_wind_outer_rings_clockwise_and_holes_counterclockwise():
    ccw_outer = {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]], [[3, 3], [3, 7], [7, 7], [7, 3], [3, 3]]]}
    cw_outer = {"type": "Polygon", "coordinates": [[[0, 0], [0, 10], [10, 10], [10, 0], [0, 0]], [[3, 3], [7, 3], [7, 7], [3, 7], [3, 3]]]}
    islands = {"type": "MultiPolygon", "coordinates": [ISLANDS["coordinates"][0], [[[60, 0], [60, 5], [65, 5], [65, 0], [60, 0]]]]}
    frame = pd.DataFrame({"geometry": [json.dumps(g) for g in (ccw_outer, cw_outer, islands, {"type": "Point", "coordinates": [1, 1]})], "v": [1, 2, 3, 4]})
    features = json.loads(geo.map_chart(frame, "regions", value="v").iloc[0]["Vega-Lite"])["layer"][0]["data"]["values"]["features"]
    assert len(features) == 4
    for feature in features[:3]:
        geometry = feature["geometry"]
        polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        for rings in polygons:
            assert geo.ring_area(rings[0]) < 0
            assert all(geo.ring_area(hole) > 0 for hole in rings[1:])
    assert features[3]["geometry"] == {"type": "Point", "coordinates": [1, 1]}
    assert geo.ring_area(json.loads(frame["geometry"].iloc[0])["coordinates"][0]) > 0


def test_map_chart_refuses_shapes_that_are_too_detailed():
    ring = [[i / 1000, (i % 7) / 1000] for i in range(2000)] + [[0, 0]]
    frame = pd.DataFrame({"geometry": [json.dumps({"type": "Polygon", "coordinates": [ring]})] * 800, "v": 1.0})
    with pytest.raises(ValueError, match="too many points"):
        geo.map_chart(frame, "regions", value="v", max_rows=800)


STORES_CSV = csv_text(STORES)
CITIES_CSV = csv_text(CITIES)


def two_inputs(left, right, tool, config):
    nodes = [(1, "text_input", {"data": left}), (2, "text_input", {"data": right}), (3, tool, config)]
    return workflow(nodes, [(1, "out", 3, "in"), (2, "out", 3, tool_port(tool))])


def tool_port(tool):
    return {"find_nearest": "places", "find_region": "regions"}[tool]


def test_map_values_tool():
    steps = [("map_values", {"column": "team", "mapping": "NEB = Nebraska\nIA = Iowa", "unmatched": "default", "default": "Other", "ignore_case": True})]
    ev = run(chain(*steps, data="team,pts\nneb,24\nIA,20\nOSU,42\n"))
    assert out(ev, 2)["team"].tolist() == ["Nebraska", "Iowa", "Other"]
    ev = run(chain(("map_values", {"column": "pts", "mapping": "24 = win\n20 = loss", "output": "new", "new_name": "result"}), data="team,pts\nneb,24\nIA,20\nOSU,42\n"))
    assert out(ev, 2)["result"].astype(str).tolist() == ["win", "loss", "42"]
    assert err(run(chain(("map_values", {"column": "team", "mapping": ""}))), 2) == "Enter at least one pair, such as TX = Texas"
    assert "no separator" in err(run(chain(("map_values", {"column": "team", "mapping": "NEB"}))), 2)
    assert err(run(chain(("map_values", {"column": "", "mapping": "a=b"}))), 2) == "Pick the column to change"
    assert "Enter a name" in err(run(chain(("map_values", {"column": "team", "mapping": "a=b", "output": "new"}))), 2)


def test_distance_tool():
    data = "a,b,c,d\n41.2565,-95.9345,39.0997,-94.5786\n0,0,0,90\n"
    ev = run(chain(("distance", {"lat1": "a", "lon1": "b", "lat2": "c", "lon2": "d", "unit": "km", "name": "km", "bearing": True, "bearing_name": "dir"}), data=data))
    df = out(ev, 2)
    assert df["km"].tolist()[1] == pytest.approx(R * math.pi / 2, rel=1e-9)
    assert df["dir"].tolist()[1] == pytest.approx(90.0)
    assert err(run(chain(("distance", {"lat1": "a", "lon1": "b", "lat2": "c", "lon2": ""}), data=data)), 2) == "Pick all four coordinate columns"
    assert "must hold numbers" in err(run(chain(("distance", {"lat1": "a", "lon1": "b", "lat2": "c", "lon2": "d"}), data="a,b,c,d\nx,1,2,3\n")), 2)


def test_find_nearest_tool_with_two_inputs():
    config = {"lat": "lat", "lon": "lon", "place_lat": "lat", "place_lon": "lon", "count": 2, "unit": "mi", "columns": ["city"], "keep_unmatched": True}
    ev = run(two_inputs(STORES_CSV, CITIES_CSV, "find_nearest", config))
    df = out(ev, 3)
    assert df["store"].tolist() == ["A", "A", "B", "B", "C", "C"]
    assert df["city"].tolist()[:2] == ["Omaha", "Lincoln"] and df["nearest_rank"].tolist() == [1, 2] * 3
    assert err(run(two_inputs(STORES_CSV, CITIES_CSV, "find_nearest", {**config, "count": 0, "max_distance": 0})), 3) == "Set a distance when you ask for every place within it"
    assert "Missing column" in err(run(two_inputs(STORES_CSV, CITIES_CSV, "find_nearest", {**config, "columns": ["nope"]})), 3)


def test_map_chart_tool_makes_a_chart_frame():
    ev = run(chain(("map_chart", {"kind": "states", "region": "st", "value": "v", "scheme": "greens", "title": "Test"}), data="st,v\nTX,5\nNE,7\n"))
    df = out(ev, 2)
    spec = json.loads(df["Vega-Lite"].iloc[0])
    assert list(df.columns)[-1] == "Vega-Lite" and spec["title"] == "Test" and spec["layer"][1]["encoding"]["color"]["scale"] == {"scheme": "greens"}
    ev = run(chain(("map_chart", {"kind": "points", "lat": "lat", "lon": "lon", "tooltip": ["city"]}), data=CITIES_CSV))
    assert json.loads(out(ev, 2)["Vega-Lite"].iloc[0])["layer"][1]["encoding"]["tooltip"][-1]["field"] == "city"
    assert err(run(chain(("map_chart", {"kind": "points", "lat": "", "lon": "lon"}), data=CITIES_CSV)), 2) == "Pick the latitude column"
    assert err(run(chain(("map_chart", {"kind": "states", "region": ""}), data="st\nTX\n")), 2) == "Pick the region column"
    assert "must hold numbers" in err(run(chain(("map_chart", {"kind": "states", "region": "st", "value": "st"}), data="st\nTX\n")), 2)


def test_read_map_and_find_region_pipeline_and_chart(tmp_path):
    path = write_geojson(tmp_path / "zones.geojson", collection(({"zone": "Core", "weight": 2}, SQUARE), ({"zone": "Ring", "weight": 9}, DONUT)))
    nodes = [
        (1, "read_map", {"path": path}),
        (2, "text_input", {"data": "pid,lat,lon\n1,5,5\n2,10,22\n3,10,30\n4,50,50\n"}),
        (3, "find_region", {"lat": "lat", "lon": "lon", "columns": ["zone", "weight"]}),
        (4, "map_chart", {"kind": "regions", "value": "weight", "tooltip": ["zone"]}),
    ]
    wf = workflow(nodes, [(2, "out", 3, "in"), (1, "out", 3, "regions"), (1, "out", 4, "in")])
    ev = run(wf)
    found = out(ev, 3)
    assert found["zone"].tolist()[:2] == ["Core", "Ring"] and found["zone"].isna().tolist() == [False, False, True, True]
    assert out(ev, 1)["zone"].tolist() == ["Core", "Ring"]
    assert json.loads(out(ev, 4)["Vega-Lite"].iloc[0])["layer"][0]["data"]["values"]["features"][1]["properties"]["weight"] == 9


def test_read_map_tool_errors_and_cache_stamp(tmp_path):
    assert err(run(workflow([(1, "read_map", {"path": ""})], [])), 1) == "Pick a shapefile or GeoJSON file"
    ev = run(workflow([(1, "read_map", {"path": str(tmp_path / "missing.geojson")})], []))
    assert ev.results["1"].status == "error"
    path = write_geojson(tmp_path / "a.geojson", collection(({"n": 1}, SQUARE)))
    engine = Engine()
    first = engine.evaluate(workflow([(1, "read_map", {"path": path})], []), run_side_effects=True)
    assert len(first.frames[("1", "out")]) == 1
    write_geojson(tmp_path / "a.geojson", collection(({"n": 1}, SQUARE), ({"n": 2}, DONUT)))
    second = engine.evaluate(workflow([(1, "read_map", {"path": path})], []), run_side_effects=True)
    assert len(second.frames[("1", "out")]) == 2


def test_geocode_tool(census):
    ev = run(chain(("geocode", {"mode": "one", "address": "addr"}), data='addr,who\n"1600 Pennsylvania Ave NW, Washington, DC 20500",a\n"nowhere",b\n'))
    df = out(ev, 2)
    assert df["geocode_status"].tolist() == ["Match", "No_Match"] and df["latitude"].round(3).tolist()[0] == 38.899
    ev = run(chain(("geocode", {"mode": "parts", "street": "s", "city": "c", "state": "t", "zip_code": ""}), data="s,c,t\n1600 Pennsylvania Ave NW,Washington,DC\n"))
    assert out(ev, 2)["geocode_status"].tolist() == ["Match"]
    assert err(run(chain(("geocode", {"mode": "one", "address": ""}), data="a\nx\n")), 2) == "Pick the address column"
    assert err(run(chain(("geocode", {"mode": "parts", "street": ""}), data="a\nx\n")), 2) == "Pick the street column"


def test_find_region_tool_errors(tmp_path):
    path = write_geojson(tmp_path / "z.geojson", collection(({"zone": "Core"}, SQUARE)))
    nodes = [(1, "read_map", {"path": path, "geometry": False}), (2, "text_input", {"data": "lat,lon\n1,1\n"}), (3, "find_region", {"lat": "lat", "lon": "lon"})]
    ev = run(workflow(nodes, [(2, "out", 3, "in"), (1, "out", 3, "regions")]))
    assert "Missing column" in err(ev, 3)


def exported_matches_engine(tmp_path, nodes, edges, node, frames_only=None):
    ev = Engine().evaluate(workflow(nodes, edges), run_side_effects=True)
    assert all(r.status == "ok" for r in ev.results.values()), [r.error for r in ev.results.values()]
    code = export_script(ev, "maps")
    script = tmp_path / "exported.py"
    script.write_text(code)
    ns = {}
    exec(compile(code, str(script), "exec"), ns)
    return ev, code, ns


def test_exports_run_and_match_the_canvas(tmp_path):
    path = write_geojson(tmp_path / "zones.geojson", collection(({"zone": "Core", "weight": 2}, SQUARE), ({"zone": "Ring", "weight": 9}, DONUT)))
    nodes = [
        (1, "text_input", {"data": STORES_CSV}),
        (2, "text_input", {"data": CITIES_CSV}),
        (3, "find_nearest", {"lat": "lat", "lon": "lon", "place_lat": "lat", "place_lon": "lon", "count": 2, "unit": "km", "columns": ["city", "lat", "lon"]}),
        (4, "distance", {"lat1": "lat", "lon1": "lon", "lat2": "lat_place", "lon2": "lon_place", "unit": "mi", "name": "check", "bearing": True}),
        (5, "map_values", {"column": "store", "mapping": "A = Alpha\nB = Beta", "ignore_case": True}),
        (6, "read_map", {"path": path}),
        (7, "text_input", {"data": "pid,lat,lon\n1,5,5\n2,10,22\n"}),
        (8, "find_region", {"lat": "lat", "lon": "lon"}),
        (9, "map_chart", {"kind": "regions", "value": "weight", "tooltip": ["zone"]}),
        (10, "map_chart", {"kind": "points", "lat": "lat", "lon": "lon", "color": "pop"}),
        (11, "map_chart", {"kind": "states", "region": "st", "value": "v"}),
        (12, "text_input", {"data": "st,v\nTX,1\nNE,2\n"}),
    ]
    edges = [(1, "out", 3, "in"), (2, "out", 3, "places"), (3, "out", 4, "in"), (4, "out", 5, "in"), (7, "out", 8, "in"), (6, "out", 8, "regions"), (6, "out", 9, "in"), (2, "out", 10, "in"), (12, "out", 11, "in")]
    ev, code, ns = exported_matches_engine(tmp_path, nodes, edges, None)
    for helper in ("def find_nearest", "def distance_between", "def map_values", "def read_map_file", "def find_region", "def map_chart", "def _haversine", "def ring_contains", "def _state_lookup"):
        assert helper in code
    assert "Requires pandas, numpy, scikit-learn, pyshp." in code
    pd.testing.assert_frame_equal(ns["find_nearest_3"], out(ev, 3))
    pd.testing.assert_frame_equal(ns["distance_4"], out(ev, 4))
    pd.testing.assert_frame_equal(ns["map_values_5"], out(ev, 5))
    pd.testing.assert_frame_equal(ns["find_region_8"], out(ev, 8))
    for name, node in (("map_chart_9", 9), ("map_chart_10", 10), ("map_chart_11", 11)):
        pd.testing.assert_frame_equal(ns[name], out(ev, node))
    proc = subprocess.run([sys.executable, "-I", str(tmp_path / "exported.py")], capture_output=True, text=True, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr


def test_geocode_export_carries_the_network_helpers(census):
    ev = run(chain(("geocode", {"mode": "one", "address": "addr"}), data="addr\n1600 Pennsylvania Ave NW\n"))
    code = export_script(ev, "g")
    assert "def census_batch" in code and "def geocode_addresses" in code and "CENSUS_BATCH = 'https://geocoding.geo.census.gov" in code
    for module in ("import csv", "import time", "import uuid", "import urllib.request"):
        assert module in code
    compile(code, "g", "exec")


def test_maps_category_and_tools_are_listed():
    from fastapi.testclient import TestClient

    from snek.server import app

    data = TestClient(app, base_url="http://127.0.0.1:8765").get("/api/tools").json()
    assert "Maps" in data["categories"] and data["categories"].index("Maps") < data["categories"].index("Sports")
    maps = {t["type"]: t for t in data["tools"] if t["category"] == "Maps"}
    assert set(maps) == {"map_chart", "geocode", "distance", "find_nearest", "read_map", "find_region"}
    assert {t["group"] for t in maps.values()} == {"Draw", "Places", "Boundaries"}
    assert all(t["needs"] and t["description"] for t in maps.values())


def test_a_map_saves_as_a_web_page(tmp_path):
    frame = geo.map_chart(pd.DataFrame({"st": ["TX", "NE"], "v": [1, 2]}), "states", region="st", value="v", title="Saved")
    target = runtime.write_any(frame, str(tmp_path / "map.html"))
    page = open(target, encoding="utf-8").read()
    assert "vega-datasets@2.11.0/data/us-10m.json" in page and "albersUsa" in page and "<title>Saved</title>" in page
