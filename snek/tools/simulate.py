from snek import distributions
from snek.tools.base import Port, Tool, ToolError, fld, is_numeric, lit, opts, register, short

EXTRA_DISTRIBUTIONS = {
    "binomial": ("Binomial", ["trials", "chance of success"]),
    "integer_uniform": ("Whole-number uniform", ["min", "max"]),
    "constant": ("Constant", ["value"]),
}


def distribution_options(with_choice=False):
    items = [(key, f"{label} ({', '.join(names)})") for key, (label, names, _) in distributions.FAMILIES.items()]
    items += [(key, f"{label} ({', '.join(names)})") for key, (label, names) in EXTRA_DISTRIBUTIONS.items()]
    if with_choice:
        items.append(("choice", "Choice from a list (name:weight, ...)"))
    return opts(*items)


def parameter_names(dist):
    if dist in distributions.FAMILIES:
        return distributions.FAMILIES[dist][1]
    return EXTRA_DISTRIBUTIONS[dist][1]


def clean_columns(columns, label="Column"):
    cleaned = []
    seen = set()
    for i, spec in enumerate(columns or [], start=1):
        name = str(spec.get("name") or "").strip()
        dist = spec.get("dist") or ""
        if not name:
            raise ToolError(f"{label} {i} needs a name")
        if name in seen:
            raise ToolError(f"Two columns are named {name}")
        seen.add(name)
        entry = {"name": name, "dist": dist}
        if dist == "choice":
            try:
                distributions.parse_choices(spec.get("choices"))
            except ValueError as e:
                raise ToolError(f"{name}: {e}") from None
            entry["choices"] = str(spec.get("choices") or "")
        else:
            if dist not in distributions.FAMILIES and dist not in EXTRA_DISTRIBUTIONS:
                raise ToolError(f"Pick a distribution for {name}")
            names = parameter_names(dist)
            values = [spec.get(k) for k in ("p1", "p2", "p3")]
            numbers = []
            for label_, value in zip(names, values):
                if value in (None, ""):
                    raise ToolError(f"{name}: enter the {label_} in Number {len(numbers) + 1}")
                numbers.append(float(value))
            try:
                distributions.check_params(dist, numbers + [0.0] * (3 - len(numbers)))
            except ValueError as e:
                raise ToolError(f"{name}: {e}") from None
            for key, value in zip(("p1", "p2", "p3"), numbers):
                entry[key] = value
        cleaned.append(entry)
    return cleaned


@register
class RandomData(Tool):
    type = "random_data"
    label = "Random Data"
    category = "Simulate"
    group = "Random data"
    description = "Make a table of random numbers. Each column follows a distribution you choose: normal, exponential, Poisson, triangular and more, or a weighted choice from a list. Connect a Fit Distribution result to draw from the best fit instead."
    needs = "No input. Optionally, the fits table from Fit Distribution."
    inputs = [Port("fit", "fit", optional=True)]
    fields = [
        fld("rows", "Rows", "number", 1000),
        fld("seed", "Random seed", "number", 1, help="The same seed gives the same numbers every run."),
        fld("columns", "Columns", "list", [{"name": "value", "dist": "normal", "p1": 0, "p2": 1, "p3": "", "choices": ""}], fields=[
            fld("name", "Name", "text", ""),
            fld("dist", "Distribution", "select", "normal", options=distribution_options(True)),
            fld("p1", "Number 1", "number", None, help="The first number in the brackets of the distribution's name."),
            fld("p2", "Number 2", "number", None),
            fld("p3", "Number 3", "number", None),
            fld("choices", "Choices", "text", "", help="For Choice only. For example: small:0.5, medium:0.3, large:0.2"),
        ]),
        fld("fit_rank", "Which fit to use", "number", 1, help="Used only when a Fit Distribution result is connected. 1 is the best fit."),
        fld("fit_name", "Column name for the fit", "text", "value"),
    ]

    def code(self, cfg, ctx):
        rows = int(cfg["rows"] or 0)
        if rows < 0 or rows > 10_000_000:
            raise ToolError("Rows must be from 0 to 10,000,000")
        seed = int(cfg["seed"] or 0)
        fit = ctx.ins.get("fit") or []
        if fit:
            rank = int(cfg["fit_rank"] or 1)
            name = str(cfg["fit_name"] or "value").strip() or "value"
            return f"{ctx.out()} = random_data({rows}, [], seed={seed}, fit={fit[0]}, fit_rank={rank}, fit_name={name!r})"
        columns = clean_columns(cfg["columns"])
        if not columns:
            raise ToolError("Add a column")
        return f"{ctx.out()} = random_data({rows}, {lit(columns)}, seed={seed})"

    def summary(self, cfg):
        return short(f"{int(cfg['rows'] or 0):,} rows × {len(cfg['columns'] or [])}")


@register
class FitDistribution(Tool):
    type = "fit_distribution"
    label = "Fit Distribution"
    category = "Simulate"
    group = "Random data"
    description = "Find the distribution that fits a column best. Tries normal, lognormal, exponential, gamma, Weibull, uniform, triangular, logistic and beta for measurements, or Poisson, geometric and negative binomial for counts. Ranks them by AIC. Outputs: the ranked fits, and a chart of the data with the best fits drawn over it."
    needs = "A table with one numeric column of at least 8 values, such as service times."
    inputs = [Port("in")]
    outputs = [Port("fits", "fits"), Port("chart", "chart")]
    fields = [
        fld("column", "Column to fit", "column", ""),
        fld("kind", "Kind of data", "select", "auto", options=opts(("auto", "Detect"), ("continuous", "Measurements (any number)"), ("discrete", "Counts (whole numbers)"))),
        fld("top", "Fits to draw on the chart", "number", 3),
    ]

    def code(self, cfg, ctx):
        column = cfg["column"]
        ctx.require(column, "Pick the column to fit")
        ctx.require_columns([column])
        if not is_numeric(ctx.dtype(column)):
            raise ToolError(f"{column} is not numeric")
        top = int(cfg["top"] or 3)
        return f"{ctx.out('fits')}, {ctx.out('chart')} = fit_distribution({ctx.var()}, {column!r}, kind={cfg['kind']!r}, top={top})"

    def summary(self, cfg):
        return short(cfg["column"]) if cfg["column"] else ""


def clean_distribution(spec, label):
    dist = spec.get("dist") or ""
    if dist not in distributions.FAMILIES and dist not in EXTRA_DISTRIBUTIONS:
        raise ToolError(f"{label}: pick a distribution")
    names = parameter_names(dist)
    numbers = []
    for item, value in zip(names, [spec.get(k) for k in ("p1", "p2", "p3")]):
        if value in (None, ""):
            raise ToolError(f"{label}: enter the {item} in Number {len(numbers) + 1}")
        numbers.append(float(value))
    try:
        distributions.check_params(dist, numbers + [0.0] * (3 - len(numbers)))
    except ValueError as e:
        raise ToolError(f"{label}: {e}") from None
    return dist, numbers


def clean_stations(stations):
    from snek.simulation import build_stations

    cleaned = []
    for i, spec in enumerate(stations or [], start=1):
        name = str(spec.get("name") or "").strip()
        label = name or f"Station {i}"
        dist, numbers = clean_distribution(spec, label)
        entry = {"name": name, "servers": int(spec.get("servers") if spec.get("servers") not in (None, "") else 1), "dist": dist}
        for key, value in zip(("p1", "p2", "p3"), numbers):
            entry[key] = value
        if spec.get("capacity") not in (None, ""):
            entry["capacity"] = int(spec["capacity"])
        if str(spec.get("scale_by") or "").strip():
            entry["scale_by"] = str(spec["scale_by"]).strip()
        if spec.get("block"):
            entry["block"] = True
        if str(spec.get("next") or "").strip():
            entry["next"] = str(spec["next"]).strip()
        cleaned.append(entry)
    try:
        build_stations(cleaned)
    except ValueError as e:
        raise ToolError(str(e)) from None
    return cleaned


def gap_options():
    keep = ["exponential", "constant", "uniform", "triangular", "gamma", "lognormal", "weibull", "normal"]
    return [o for o in distribution_options() if o["value"] in keep]


ATTRIBUTE_FIELDS = [
    fld("name", "Name", "text", ""),
    fld("dist", "Distribution", "select", "choice", options=distribution_options(True)),
    fld("p1", "Number 1", "number", None),
    fld("p2", "Number 2", "number", None),
    fld("p3", "Number 3", "number", None),
    fld("choices", "Choices", "text", "", help="For Choice only. For example: small:0.5, medium:0.3, large:0.2"),
]


@register
class MakeArrivals(Tool):
    type = "make_arrivals"
    label = "Make Arrivals"
    category = "Simulate"
    group = "Process"
    description = "Make a table of arrival events: one row per entity (car, customer, order) with its arrival time, plus attributes such as order size. Arrivals come from a gap distribution (exponential gaps make a Poisson stream), or from a table of rates that changes through the day."
    needs = "No input. Optionally, a rates table with the columns start and mean_gap, for an arrival rate that changes over time. Note: when you connect this table to Simulate Process, every replication reuses these same arrivals. For fresh arrivals in each replication, leave Simulate Process unconnected and set the gap there."
    inputs = [Port("rates", "rates", optional=True)]
    fields = [
        fld("until", "Run length", "number", 3600, help="Arrivals are made from time 0 up to this time. Use one time unit throughout, such as seconds."),
        fld("gap_dist", "Time between arrivals", "select", "exponential", options=gap_options(), help="Ignored when a rates table is connected."),
        fld("gap_p1", "Number 1", "number", 40),
        fld("gap_p2", "Number 2", "number", None),
        fld("gap_p3", "Number 3", "number", None),
        fld("attributes", "Attributes of each arrival", "list", [], fields=ATTRIBUTE_FIELDS),
        fld("seed", "Random seed", "number", 1),
    ]

    def code(self, cfg, ctx):
        until = float(cfg["until"] or 0)
        if until <= 0:
            raise ToolError("Run length must be above 0")
        rates = ctx.ins.get("rates") or []
        gap = {"dist": cfg["gap_dist"], "params": [cfg["gap_p1"], cfg["gap_p2"], cfg["gap_p3"]]}
        if rates:
            if not {"start", "mean_gap"} <= set(ctx.columns("rates")):
                raise ToolError("The rates table needs the columns start and mean_gap")
        else:
            dist, numbers = clean_distribution({"dist": cfg["gap_dist"], "p1": cfg["gap_p1"], "p2": cfg["gap_p2"], "p3": cfg["gap_p3"]}, "Time between arrivals")
            gap = {"dist": dist, "params": numbers}
        attributes = clean_columns(cfg["attributes"], "Attribute")
        extra = f", rates={rates[0]}" if rates else ""
        return f"{ctx.out()} = make_arrivals({lit(gap)}, {until:g}, attributes={lit(attributes)}{extra}, seed={int(cfg['seed'] or 0)})"

    def summary(self, cfg):
        return short(f"to {cfg['until']} · gap {cfg['gap_dist']}")


@register
class SimulateProcess(Tool):
    type = "simulate_process"
    label = "Simulate Process"
    category = "Simulate"
    group = "Process"
    description = "Run a discrete-event simulation of customers or items moving through stations, such as a drive-thru lane. Each station has servers, a waiting line with a limit, a service-time distribution and a next station. Arrivals come from a table of events or from a gap distribution. Outputs: one row per entity, every visit to a station, station statistics, a summary across replications, and an optional event log."
    needs = "An arrivals table with a time column (such as from Make Arrivals), or no input and a gap distribution. Optionally a schedule table (station, time, servers) that changes the number of servers during the run."
    inputs = [Port("arrivals", "arrivals", optional=True), Port("schedule", "schedule", optional=True), Port("rates", "rates", optional=True)]
    outputs = [Port("entities", "entities"), Port("visits", "visits"), Port("stations", "stations"), Port("summary", "summary"), Port("log", "log")]
    fields = [
        fld("stations", "Stations, in order. The first one is where arrivals enter.", "list", [
            {"name": "Order", "servers": 1, "capacity": 6, "dist": "triangular", "p1": 20, "p2": 40, "p3": 90, "scale_by": "", "block": True, "next": "Window"},
            {"name": "Window", "servers": 1, "capacity": "", "dist": "gamma", "p1": 4, "p2": 10, "p3": "", "scale_by": "", "block": False, "next": "Exit"},
        ], fields=[
            fld("name", "Name", "text", ""),
            fld("servers", "Servers", "number", 1, help="How many can be served at the same time."),
            fld("capacity", "Waiting spaces", "number", None, help="How many can wait. Blank means no limit. An arrival that finds no space is lost."),
            fld("dist", "Service time", "select", "exponential", options=distribution_options()),
            fld("p1", "Number 1", "number", None),
            fld("p2", "Number 2", "number", None),
            fld("p3", "Number 3", "number", None),
            fld("scale_by", "Multiply time by column", "text", "", help="Optional. A numeric attribute of the entity, such as items in the order."),
            fld("block", "Hold the server until the next station has room", "bool", False, help="On: a finished entity stays at this station, keeping the server busy, until the next station can take it. Off: it is lost if the next station is full."),
            fld("next", "Next station", "text", "", help="A station name, or Exit. Several, with weights: Pay:0.7, Exit:0.3. Blank means Exit."),
        ]),
        fld("gap_dist", "Time between arrivals (no arrivals table)", "select", "exponential", options=gap_options()),
        fld("gap_p1", "Number 1", "number", 40),
        fld("gap_p2", "Number 2", "number", None),
        fld("gap_p3", "Number 3", "number", None),
        fld("attributes", "Attributes of each arrival (no arrivals table)", "list", [], fields=ATTRIBUTE_FIELDS),
        fld("until", "Run length", "number", 3600, help="The clock stops here. Entities still in the system are marked unfinished. Blank runs until the system empties (arrivals table only)."),
        fld("warmup", "Warm-up", "number", 0, help="Results ignore entities that arrive before this time, so the start-up empty system does not bias them."),
        fld("replications", "Replications", "number", 1, help="Independent runs with different random numbers. The summary gives the mean and a 95% interval across them."),
        fld("seed", "Random seed", "number", 1),
        fld("time_column", "Time column in the arrivals table", "text", "arrival_time"),
        fld("id_column", "ID column in the arrivals table (blank numbers them)", "text", ""),
        fld("keep_log", "Keep an event log", "bool", False, help="One row per event. Handy for checking a small run. Large runs make large logs."),
        fld("max_log", "Most log rows per replication", "number", 200000, show_if={"keep_log": ["true"]}),
    ]

    def code(self, cfg, ctx):
        stations = clean_stations(cfg["stations"])
        has = {p: bool(ctx.ins.get(p)) for p in ("arrivals", "schedule", "rates")}
        until = None if cfg["until"] in (None, "") else float(cfg["until"])
        if until is not None and until <= 0:
            raise ToolError("Run length must be above 0")
        if until is None and not has["arrivals"]:
            raise ToolError("Set the run length when there is no arrivals table")
        warmup = float(cfg["warmup"] or 0)
        if warmup < 0 or (until is not None and warmup >= until):
            raise ToolError("Warm-up must be 0 or more, and shorter than the run length")
        reps = 1 if cfg["replications"] in (None, "") else int(cfg["replications"])
        if reps < 1 or reps > 1000:
            raise ToolError("Replications must be from 1 to 1000")
        time_column = str(cfg["time_column"] or "arrival_time").strip()
        id_column = str(cfg["id_column"] or "").strip()
        if has["arrivals"]:
            ctx.require_columns([time_column], "arrivals")
            if id_column:
                ctx.require_columns([id_column], "arrivals")
        if has["schedule"] and not {"station", "time", "servers"} <= set(ctx.columns("schedule")):
            raise ToolError("The schedule table needs the columns station, time and servers")
        if has["rates"] and not {"start", "mean_gap"} <= set(ctx.columns("rates")):
            raise ToolError("The rates table needs the columns start and mean_gap")
        args = [ctx.ins["arrivals"][0] if has["arrivals"] else "None", lit(stations)]
        if has["schedule"]:
            args.append(f"schedule={ctx.ins['schedule'][0]}")
        if has["rates"]:
            args.append(f"rates={ctx.ins['rates'][0]}")
        if not has["arrivals"]:
            attributes = clean_columns(cfg["attributes"], "Attribute")
            if not has["rates"]:
                dist, numbers = clean_distribution({"dist": cfg["gap_dist"], "p1": cfg["gap_p1"], "p2": cfg["gap_p2"], "p3": cfg["gap_p3"]}, "Time between arrivals")
                args.append(f"gap={lit({'dist': dist, 'params': numbers})}")
            if attributes:
                args.append(f"attributes={lit(attributes)}")
        if until is not None:
            args.append(f"until={until:g}")
        if warmup:
            args.append(f"warmup={warmup:g}")
        args.append(f"replications={reps}")
        args.append(f"seed={int(cfg['seed'] or 0)}")
        if cfg["keep_log"]:
            args.append("keep_log=True")
            args.append(f"max_log={int(cfg['max_log'] or 200000)}")
        if has["arrivals"]:
            if time_column != "arrival_time":
                args.append(f"time_column={time_column!r}")
            if id_column:
                args.append(f"id_column={id_column!r}")
        outs = ", ".join(ctx.out(p.name) for p in self.outputs)
        return f"{outs} = simulate_process({', '.join(args)})"

    def summary(self, cfg):
        return short(f"{len(cfg['stations'] or [])} stations · {int(cfg['replications'] or 1)} runs")
