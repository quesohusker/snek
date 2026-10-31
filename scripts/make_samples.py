import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PENGUINS = "examples/data/penguins"
NYC = "examples/data/nycflights13"
OUT = "output"


def build(name, nodes, edges):
    wf = {
        "version": 1,
        "name": name,
        "nodes": [{"id": str(i), "type": t, "label": label, "position": {"x": x * 170, "y": y * 130}, "config": cfg} for i, t, label, x, y, cfg in nodes],
        "edges": [
            {"id": f"e{s}.{sh}-{t}.{th}", "source": str(s), "sourceHandle": sh, "target": str(t), "targetHandle": th}
            for s, sh, t, th in edges
        ],
    }
    path = ROOT / "workflows" / f"{name}.flow.json"
    path.write_text(json.dumps(wf, indent=2))
    print(path)


def chain(*ids):
    return [(a, "out", b, "in") for a, b in zip(ids, ids[1:])]


def main():
    build(
        "Penguins - body mass by species",
        [
            (1, "input", "Penguins", 0, 0, {"path": f"{PENGUINS}/penguins.csv"}),
            (2, "filter", "Sex recorded", 1, 0, {"mode": "basic", "column": "sex", "operator": "notna"}),
            (3, "summarize", "", 2, 0, {"group_by": ["species", "sex"], "aggs": [
                {"column": "species", "func": "size", "name": "birds"},
                {"column": "body_mass_g", "func": "mean", "name": "avg_mass_g"},
                {"column": "flipper_length_mm", "func": "mean", "name": "avg_flipper_mm"},
            ]}),
            (4, "formula", "Round", 3, 0, {"formulas": [
                {"column": "avg_mass_g", "expression": "[avg_mass_g].round(0)", "dtype": ""},
                {"column": "avg_flipper_mm", "expression": "[avg_flipper_mm].round(1)", "dtype": ""},
            ]}),
            (5, "sort", "", 4, 0, {"keys": [{"column": "species", "order": "asc"}, {"column": "avg_mass_g", "order": "desc"}], "nulls": "last"}),
            (6, "browse", "", 5, 0, {}),
        ],
        [(1, "out", 2, "in"), (2, "true", 3, "in")] + chain(3, 4, 5, 6),
    )

    raw_fields = [
        ("Species", "species", ""),
        ("Island", "island", ""),
        ("Individual ID", "individual_id", ""),
        ("Date Egg", "date_egg", "datetime"),
        ("Culmen Length (mm)", "bill_length_mm", ""),
        ("Culmen Depth (mm)", "bill_depth_mm", ""),
        ("Flipper Length (mm)", "flipper_length_mm", ""),
        ("Body Mass (g)", "body_mass_g", ""),
        ("Sex", "sex", ""),
    ]
    build(
        "Penguins - clean the raw file",
        [
            (1, "input", "Raw field data", 0, 0, {"path": f"{PENGUINS}/penguins_raw.csv"}),
            (2, "select", "Rename and type", 1, 0, {"fields": [{"name": n, "keep": True, "rename": r, "dtype": d} for n, r, d in raw_fields], "keep_new": False}),
            (3, "cleanse", "Lowercase sex", 2, 0, {"columns": ["sex"], "trim": True, "case": "lower"}),
            (4, "formula", "Short species, egg year", 3, 0, {"formulas": [
                {"column": "species", "expression": "[species].str.split(' ').str[0]", "dtype": ""},
                {"column": "egg_year", "expression": "[date_egg].dt.year", "dtype": "Int64"},
            ]}),
            (5, "filter", "Known sex", 4, 0, {"mode": "basic", "column": "sex", "operator": "in", "value": "male, female"}),
            (6, "summarize", "", 5, 0, {"group_by": ["species", "egg_year"], "aggs": [
                {"column": "individual_id", "func": "nunique", "name": "birds"},
                {"column": "body_mass_g", "func": "mean", "name": "avg_mass_g"},
            ]}),
            (7, "browse", "", 6, 0, {}),
        ],
        chain(1, 2, 3, 4, 5) + [(5, "true", 6, "in"), (6, "out", 7, "in")],
    )

    build(
        "Flights - Q1 delays by airline",
        [
            (1, "input", "Q1 flights", 0, 0, {"path": f"{NYC}/flights_2013_*.csv.gz", "filename_col": "file"}),
            (2, "filter", "Departed", 1, 0, {"mode": "basic", "column": "dep_delay", "operator": "notna"}),
            (3, "formula", "Late flag", 2, 0, {"formulas": [{"column": "late_15", "expression": "iif([dep_delay] > 15, 1, 0)", "dtype": "Int64"}]}),
            (4, "input", "Airlines", 2, 1.3, {"path": f"{NYC}/airlines.csv"}),
            (5, "join", "", 3, 0.4, {"keys": [{"left": "carrier", "right": "carrier"}], "suffix": "_right"}),
            (6, "summarize", "By airline", 4, 0.4, {"group_by": ["name"], "aggs": [
                {"column": "carrier", "func": "size", "name": "flights"},
                {"column": "dep_delay", "func": "mean", "name": "avg_dep_delay"},
                {"column": "arr_delay", "func": "mean", "name": "avg_arr_delay"},
                {"column": "late_15", "func": "mean", "name": "share_late_15"},
            ]}),
            (7, "formula", "Round", 5, 0.4, {"formulas": [
                {"column": "avg_dep_delay", "expression": "[avg_dep_delay].round(1)", "dtype": ""},
                {"column": "avg_arr_delay", "expression": "[avg_arr_delay].round(1)", "dtype": ""},
                {"column": "share_late_15", "expression": "[share_late_15].round(3)", "dtype": ""},
            ]}),
            (8, "sort", "", 6, 0.4, {"keys": [{"column": "avg_dep_delay", "order": "desc"}], "nulls": "last"}),
            (9, "output", "", 7, 0.4, {"path": f"{OUT}/airline_delays_2013_q1.csv", "format": "auto"}),
        ],
        [(1, "out", 2, "in"), (2, "true", 3, "in"), (3, "out", 5, "left"), (4, "out", 5, "right"), (5, "join", 6, "in")] + chain(6, 7, 8, 9),
    )

    build(
        "Flights - weather at departure",
        [
            (1, "input", "Q1 flights", 0, 0, {"path": f"{NYC}/flights_2013_*.csv.gz"}),
            (2, "input", "Hourly weather", 0, 1.3, {"path": f"{NYC}/weather_2013_q1.csv"}),
            (3, "join", "Same airport and hour", 1, 0.6, {"keys": [{"left": k, "right": k} for k in ("origin", "year", "month", "day", "hour")], "suffix": "_wx"}),
            (4, "formula", "Rain and late flags", 2, 0.6, {"formulas": [
                {"column": "conditions", "expression": "iif([precip] > 0, 'rain', 'dry')", "dtype": ""},
                {"column": "late_15", "expression": "iif([dep_delay] > 15, 1, 0)", "dtype": "Int64"},
            ]}),
            (5, "summarize", "", 3, 0.6, {"group_by": ["origin", "conditions"], "aggs": [
                {"column": "origin", "func": "size", "name": "flights"},
                {"column": "dep_delay", "func": "mean", "name": "avg_dep_delay"},
                {"column": "late_15", "func": "mean", "name": "share_late_15"},
            ]}),
            (6, "sort", "", 4, 0.6, {"keys": [{"column": "origin", "order": "asc"}, {"column": "conditions", "order": "asc"}], "nulls": "last"}),
            (7, "browse", "", 5, 0.6, {}),
        ],
        [(1, "out", 3, "left"), (2, "out", 3, "right"), (3, "join", 4, "in")] + chain(4, 5, 6, 7),
    )

    build(
        "Flights - fleets from nested JSON",
        [
            (1, "input", "Carriers with fleets", 0, 0, {"path": f"{NYC}/carriers.json"}),
            (2, "explode", "One row per plane", 1, 0, {"column": "fleet"}),
            (3, "unnest", "Plane fields", 2, 0, {"column": "fleet", "prefix": False}),
            (4, "filter", "Known planes", 3, 0, {"mode": "basic", "column": "tailnum", "operator": "notna"}),
            (5, "summarize", "", 4, 0, {"group_by": ["name"], "aggs": [
                {"column": "tailnum", "func": "count", "name": "planes"},
                {"column": "seats", "func": "mean", "name": "avg_seats"},
                {"column": "year", "func": "median", "name": "median_build_year"},
                {"column": "manufacturer", "func": "nunique", "name": "manufacturers"},
            ]}),
            (6, "sort", "", 5, 0, {"keys": [{"column": "planes", "order": "desc"}], "nulls": "last"}),
            (7, "browse", "", 6, 0, {}),
        ],
        chain(1, 2, 3, 4) + [(4, "true", 5, "in")] + chain(5, 6, 7),
    )

    build(
        "Flights - daily delay trend",
        [
            (1, "input", "Q1 flights", 0, 0, {"path": f"{NYC}/flights_2013_*.csv.gz"}),
            (2, "datetime", "Parse departure hour", 1, 0, {"mode": "parse", "column": "time_hour", "utc": True}),
            (3, "formula", "New York time", 2, 0, {"formulas": [{"column": "time_hour", "expression": "[time_hour].dt.tz_convert('America/New_York')", "dtype": ""}]}),
            (4, "datetime", "Day of flight", 3, 0, {"mode": "extract", "column": "time_hour", "part": "date", "name": "day"}),
            (5, "summarize", "Per day", 4, 0, {"group_by": ["day"], "aggs": [
                {"column": "carrier", "func": "size", "name": "flights"},
                {"column": "dep_delay", "func": "mean", "name": "avg_delay"},
            ]}),
            (6, "sort", "", 5, 0, {"keys": [{"column": "day", "order": "asc"}], "nulls": "last"}),
            (7, "multirow", "Change vs prior day", 0, 1.4, {"column": "delay_change", "expression": "[avg_delay] - [Row-1:avg_delay]"}),
            (8, "running_total", "Flights to date", 1, 1.4, {"columns": ["flights"]}),
            (9, "rank", "Worst days", 2, 1.4, {"column": "avg_delay", "order": "desc", "method": "min", "name": "delay_rank"}),
            (10, "tile", "Delay quartile", 3, 1.4, {"column": "avg_delay", "mode": "count", "tiles": 4, "name": "quartile"}),
            (11, "browse", "", 4, 1.4, {}),
        ],
        chain(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11),
    )

    build(
        "Penguins - predict body mass",
        [
            (1, "input", "Penguins", 0, 0.7, {"path": f"{PENGUINS}/penguins.csv"}),
            (2, "field_summary", "Profile", 1, 0, {}),
            (3, "correlation", "Measurements", 1, 1.4, {"columns": ["bill_length_mm", "bill_depth_mm", "flipper_length_mm", "body_mass_g"]}),
            (4, "linear_regression", "Body mass model", 2, 0.7, {"target": "body_mass_g", "predictors": ["flipper_length_mm", "bill_length_mm", "bill_depth_mm"]}),
            (5, "browse", "Coefficients", 3, 0.7, {}),
        ],
        [(1, "out", 2, "in"), (1, "out", 3, "in"), (1, "out", 4, "in"), (4, "coef", 5, "in")],
    )

    build(
        "Penguins - classify species",
        [
            (1, "input", "Penguins", 0, 0.7, {"path": f"{PENGUINS}/penguins.csv"}),
            (2, "create_samples", "70 / 30 split", 1, 0.7, {"estimation": 70, "validation": 30, "seed": 1}),
            (3, "decision_tree", "Tree", 2, 0, {"target": "species", "predictors": ["bill_length_mm", "bill_depth_mm", "flipper_length_mm", "island"], "max_depth": 4}),
            (4, "random_forest", "Forest", 2, 1.4, {"target": "species", "predictors": ["bill_length_mm", "bill_depth_mm", "flipper_length_mm", "island"], "trees": 200}),
            (5, "model_comparison", "Accuracy on unseen birds", 3, 0.7, {}),
            (6, "score", "Score validation birds", 4, 1.4, {}),
            (7, "browse", "", 5, 1.4, {}),
        ],
        [(1, "out", 2, "in"), (2, "estimation", 3, "in"), (2, "estimation", 4, "in"), (3, "model", 5, "model"), (4, "model", 5, "model"), (2, "validation", 5, "data"), (4, "model", 6, "model"), (2, "validation", 6, "data"), (6, "out", 7, "in")],
    )

    build(
        "Flights - forecast daily departures",
        [
            (1, "input", "Q1 flights", 0, 0, {"path": f"{NYC}/flights_2013_*.csv.gz"}),
            (2, "formula", "Flight date", 1, 0, {"formulas": [{"column": "date", "expression": "pd.to_datetime(dict(year=[year], month=[month], day=[day]))", "dtype": ""}]}),
            (3, "summarize", "Departures per day", 2, 0, {"group_by": ["date"], "aggs": [{"column": "carrier", "func": "size", "name": "departures"}]}),
            (4, "ts_filler", "Every day present", 3, 0, {"date": "date", "freq": "D", "method": "zero"}),
            (5, "ets", "ETS, weekly pattern", 4, -0.7, {"date": "date", "value": "departures", "freq": "D", "periods": 14, "seasonal": "add", "seasonal_periods": 7}),
            (6, "arima", "ARIMA, auto order", 4, 0.7, {"date": "date", "value": "departures", "freq": "D", "periods": 14, "seasonal": True, "season_length": 7}),
            (7, "browse", "ETS forecast", 5, -0.7, {}),
            (8, "browse", "ARIMA forecast", 5, 0.7, {}),
        ],
        chain(1, 2, 3, 4) + [(4, "out", 5, "in"), (4, "out", 6, "in"), (5, "forecast", 7, "in"), (6, "forecast", 8, "in")],
    )

    build(
        "Demo - league ratings (made-up teams)",
        [
            (1, "text_input", "Made-up league", 0, 0.7, {"data": "week,home,away,home_pts,away_pts,neutral\n1,Prairie Dogs,Ridge Hawks,31,17,false\n1,Lake Pike,Canyon Wrens,24,27,false\n1,Iron Owls,Delta Herons,20,13,false\n2,Ridge Hawks,Iron Owls,28,24,false\n2,Canyon Wrens,Prairie Dogs,14,35,false\n2,Delta Herons,Lake Pike,21,10,false\n3,Prairie Dogs,Iron Owls,27,20,false\n3,Lake Pike,Ridge Hawks,17,30,false\n3,Canyon Wrens,Delta Herons,23,20,false\n4,Iron Owls,Lake Pike,34,6,false\n4,Ridge Hawks,Delta Herons,24,21,false\n4,Prairie Dogs,Lake Pike,42,14,false\n5,Delta Herons,Prairie Dogs,17,20,true\n5,Canyon Wrens,Iron Owls,10,31,true\n5,Ridge Hawks,Canyon Wrens,38,21,true", "delimiter": ","}),
            (2, "team_ratings", "SRS ratings", 1, 0, {"home": "home", "away": "away", "home_points": "home_pts", "away_points": "away_pts", "neutral": "neutral", "cap": 28}),
            (3, "elo", "Elo ratings", 1, 1.4, {"home": "home", "away": "away", "home_points": "home_pts", "away_points": "away_pts", "neutral": "neutral", "order": "week"}),
            (4, "join", "Side by side", 2, 0.7, {"keys": [{"left": "Team", "right": "Team"}], "suffix": "_elo"}),
            (5, "browse", "", 3, 0.7, {}),
        ],
        [(1, "out", 2, "in"), (1, "out", 3, "in"), (2, "ratings", 4, "left"), (3, "ratings", 4, "right"), (4, "join", 5, "in")],
    )

    build(
        "Penguins - model bake-off",
        [
            (1, "input", "Penguins", 0, 1.5, {"path": f"{PENGUINS}/penguins.csv"}),
            (2, "naive_bayes", "Naive Bayes", 1, 0, {"target": "species", "predictors": ["bill_length_mm", "bill_depth_mm", "flipper_length_mm", "body_mass_g"]}),
            (3, "knn", "KNN", 1, 0.75, {"target": "species", "predictors": ["bill_length_mm", "bill_depth_mm", "flipper_length_mm", "body_mass_g"], "k": 5}),
            (4, "svm", "SVM", 1, 1.5, {"target": "species", "predictors": ["bill_length_mm", "bill_depth_mm", "flipper_length_mm", "body_mass_g"]}),
            (5, "neural_network", "Neural net", 1, 2.25, {"target": "species", "predictors": ["bill_length_mm", "bill_depth_mm", "flipper_length_mm", "body_mass_g"], "hidden": "32"}),
            (6, "random_forest", "Forest", 1, 3, {"target": "species", "predictors": ["bill_length_mm", "bill_depth_mm", "flipper_length_mm", "body_mass_g"], "trees": 100}),
            (7, "cross_validation", "5-fold scores", 2, 1.5, {"folds": 5}),
            (8, "browse", "", 3, 1.5, {}),
        ],
        [(1, "out", n, "in") for n in (2, 3, 4, 5, 6)] + [(n, "model", 7, "model") for n in (2, 3, 4, 5, 6)] + [(1, "out", 7, "data"), (7, "summary", 8, "in")],
    )

    build(
        "Flights - forecast accuracy check",
        [
            (1, "input", "Q1 flights", 0, 0.7, {"path": f"{NYC}/flights_2013_*.csv.gz"}),
            (2, "formula", "Flight date", 1, 0.7, {"formulas": [{"column": "date", "expression": "pd.to_datetime(dict(year=[year], month=[month], day=[day]))", "dtype": ""}]}),
            (3, "summarize", "Departures per day", 2, 0.7, {"group_by": ["date"], "aggs": [{"column": "carrier", "func": "size", "name": "departures"}]}),
            (4, "filter", "Before March 18", 3, 0.7, {"mode": "expression", "expression": "[date] < '2013-03-18'"}),
            (5, "ets", "Forecast last 14 days", 4, 0, {"date": "date", "value": "departures", "freq": "D", "periods": 14, "seasonal": "add", "seasonal_periods": 7}),
            (6, "ts_compare", "Forecast vs actual", 5, 0.7, {"date": "date", "actual_date": "date", "actual_value": "departures"}),
            (7, "stl", "Trend and weekly pattern", 3, 2.1, {"date": "date", "value": "departures", "freq": "D", "period": 7}),
            (8, "browse", "", 6, 0.7, {}),
        ],
        chain(1, 2, 3, 4) + [(4, "true", 5, "in"), (5, "forecast", 6, "forecast"), (4, "false", 6, "actual"), (6, "metrics", 8, "in"), (3, "out", 7, "in")],
    )

    build(
        "Demo - no files needed",
        [
            (1, "text_input", "Scores", 0, 0, {"data": "team,opp,pts,opp_pts\nNebraska,Iowa,24,20\nIowa,Nebraska,20,24\nNebraska,Akron,68,0\nAkron,Nebraska,0,68\nIowa,Akron,31,7\nAkron,Iowa,7,31", "delimiter": ","}),
            (2, "formula", "Win flag", 1, 0, {"formulas": [{"column": "win", "expression": "iif([pts] > [opp_pts], 1, 0)", "dtype": "Int64"}]}),
            (3, "summarize", "Record", 2, 0, {"group_by": ["team"], "aggs": [{"column": "win", "func": "sum", "name": "wins"}, {"column": "pts", "func": "mean", "name": "ppg"}]}),
            (4, "sort", "", 3, 0, {"keys": [{"column": "wins", "order": "desc"}], "nulls": "last"}),
            (5, "browse", "", 4, 0, {}),
        ],
        chain(1, 2, 3, 4, 5),
    )


if __name__ == "__main__":
    main()
