import os

from snek import runtime
from snek.tools.base import Port, Tool, ToolError, file_stamp, fld, is_numeric, opts, register, short

UNITS = opts(("mi", "Miles"), ("km", "Kilometers"), ("m", "Meters"), ("ft", "Feet"), ("yd", "Yards"), ("nmi", "Nautical miles"))
SCHEMES = opts(("blues", "Blues"), ("greens", "Greens"), ("oranges", "Oranges"), ("reds", "Reds"), ("purples", "Purples"), ("greys", "Greys"), ("viridis", "Viridis"), ("plasma", "Plasma"), ("turbo", "Turbo"), ("yelloworangered", "Yellow, orange, red"), ("redyellowblue", "Red, yellow, blue"))


def require_numeric(ctx, columns, port="in"):
    ctx.require_columns(columns, port)
    for c in columns:
        if not is_numeric(ctx.dtype(c, port)):
            raise ToolError(f"{c} must hold numbers")


@register
class MapValues(Tool):
    type = "map_values"
    label = "Map Values"
    category = "Clean"
    description = "Change the values in a column with a list you paste, one pair per line, such as TX = Texas. Values with no pair stay as they are, or become a default or blank. For a lookup table in another table, use Look Up Values."
    needs = "A table with the column to change."
    fields = [
        fld("column", "Column", "column", ""),
        fld("mapping", "Pairs (old = new)", "textarea", "", help="One pair per line. Separate old and new with =, a comma, -> or a tab, so a two-column paste from Excel works. Numbers match whole numbers, so 1 matches 1.0."),
        fld("unmatched", "Values with no pair", "select", "keep", options=opts(("keep", "Keep as they are"), ("default", "Use a default"), ("blank", "Make blank"))),
        fld("default", "Default", "text", "", show_if={"unmatched": ["default"]}),
        fld("ignore_case", "Ignore capital letters", "bool", False),
        fld("trim", "Ignore spaces at the ends", "bool", True),
        fld("output", "Write result to", "select", "replace", options=opts(("replace", "The same column"), ("new", "A new column"))),
        fld("new_name", "New column name", "text", "", show_if={"output": ["new"]}),
    ]

    def code(self, cfg, ctx):
        ctx.require(cfg["column"], "Pick the column to change")
        ctx.require(str(cfg["mapping"] or "").strip(), "Enter at least one pair, such as TX = Texas")
        ctx.require_columns([cfg["column"]])
        try:
            runtime.parse_mapping(cfg["mapping"])
        except ValueError as e:
            raise ToolError(str(e)) from None
        args = [ctx.var(), repr(cfg["column"]), repr(cfg["mapping"])]
        if cfg["unmatched"] != "keep":
            args.append(f"unmatched={cfg['unmatched']!r}")
        if cfg["unmatched"] == "default":
            args.append(f"default={str(cfg['default'] or '')!r}")
        if cfg["ignore_case"]:
            args.append("ignore_case=True")
        if not cfg["trim"]:
            args.append("trim=False")
        if cfg["output"] == "new":
            name = str(cfg["new_name"] or "").strip()
            ctx.require(name, "Enter a name for the new column")
            args.append(f"output={name!r}")
        return f"{ctx.out()} = map_values({', '.join(args)})"

    def summary(self, cfg):
        count = len(runtime.parse_mapping(cfg["mapping"])) if str(cfg["mapping"] or "").strip() else 0
        return short(f"{cfg['column']}: {count} pairs") if cfg["column"] and count else ""


@register
class MapChart(Tool):
    type = "map_chart"
    label = "Map Chart"
    category = "Maps"
    group = "Draw"
    description = "Draw points on a map, show where points bunch up as a heat map, or shade US states, US counties or the regions of a map file by a value. The map shows in the results panel; connect Save File with an .html path to save it."
    needs = "A table with latitude and longitude columns (points and heat map), a column of state names, codes or FIPS codes, or county FIPS codes (shaded maps), or a table from Read Map File (regions)."
    fields = [
        fld("kind", "Draw", "select", "points", options=opts(("points", "Points (latitude and longitude)"), ("density", "Heat map of points (where they bunch up)"), ("states", "Shaded US states"), ("counties", "Shaded US counties"), ("regions", "Shaded regions from a map file"))),
        fld("lat", "Latitude", "column", "", show_if={"kind": ["points", "density"]}),
        fld("lon", "Longitude", "column", "", show_if={"kind": ["points", "density"]}),
        fld("size", "Size by (optional)", "column", "", show_if={"kind": ["points"]}),
        fld("color", "Color by (optional)", "column", "", show_if={"kind": ["points"]}),
        fld("basemap", "Background", "select", "us", show_if={"kind": ["points", "density"]}, options=opts(("us", "United States"), ("world", "World"))),
        fld("weight", "Weight by (optional)", "column", "", show_if={"kind": ["density"]}, help="Leave blank to count rows. Pick a number column to add up or average it in each cell."),
        fld("cell_agg", "In each cell", "select", "sum", show_if={"kind": ["density"]}, options=opts(("sum", "Add the weights"), ("mean", "Average the weights"), ("count", "Count rows"))),
        fld("bins", "Detail (cells across)", "number", 40, show_if={"kind": ["density"]}, help="How many grid cells span the data. More cells show finer detail. Use 5 to 150."),
        fld("smooth", "Smoothing (cells)", "number", 1, show_if={"kind": ["density"]}, help="Spreads each point over nearby cells for a softer look. Use 0 for exact cell values, up to 10."),
        fld("color_scale", "Color scale", "select", "linear", show_if={"kind": ["density"]}, options=opts(("linear", "Linear"), ("sqrt", "Square root (shows light areas better)"))),
        fld("region", "Region column", "column", "", show_if={"kind": ["states", "counties"]}, help="States: a name, a two-letter code or a FIPS code. Counties: the five-digit FIPS code, such as 48453."),
        fld("geometry", "Shape column", "column", "geometry", show_if={"kind": ["regions"]}, help="The column Read Map File makes, named geometry."),
        fld("value", "Value to shade by", "column", "", show_if={"kind": ["states", "counties", "regions"]}, help="Leave blank on states or counties to shade by how many rows each has."),
        fld("agg", "When a region has several rows", "select", "sum", show_if={"kind": ["states", "counties"]}, options=opts(("sum", "Add them"), ("mean", "Average"), ("median", "Median"), ("min", "Smallest"), ("max", "Largest"), ("first", "First"), ("count", "Count rows"))),
        fld("tooltip", "Also show when hovering", "columns", [], show_if={"kind": ["points", "regions"]}),
        fld("scheme", "Colors", "select", "blues", options=SCHEMES),
        fld("title", "Title (optional)", "text", ""),
        fld("max_rows", "Draw at most this many rows", "number", 5000, show_if={"kind": ["points", "regions"]}),
    ]

    def code(self, cfg, ctx):
        kind = cfg["kind"]
        args = [ctx.var(), repr(kind)]
        if kind == "points":
            ctx.require(cfg["lat"], "Pick the latitude column")
            ctx.require(cfg["lon"], "Pick the longitude column")
            require_numeric(ctx, [cfg["lat"], cfg["lon"]])
            extras = [c for c in (cfg["size"], cfg["color"]) + tuple(cfg["tooltip"] or []) if c]
            ctx.require_columns(extras)
            if cfg["size"] and not is_numeric(ctx.dtype(cfg["size"])):
                raise ToolError(f"{cfg['size']} must hold numbers to set the size")
            args += [f"lat={cfg['lat']!r}", f"lon={cfg['lon']!r}"]
            for key in ("size", "color"):
                if cfg[key]:
                    args.append(f"{key}={cfg[key]!r}")
            if cfg["basemap"] != "us":
                args.append(f"basemap={cfg['basemap']!r}")
        elif kind == "density":
            ctx.require(cfg["lat"], "Pick the latitude column")
            ctx.require(cfg["lon"], "Pick the longitude column")
            require_numeric(ctx, [cfg["lat"], cfg["lon"]])
            args += [f"lat={cfg['lat']!r}", f"lon={cfg['lon']!r}"]
            if cfg["weight"] and cfg["cell_agg"] != "count":
                ctx.require_columns([cfg["weight"]])
                require_numeric(ctx, [cfg["weight"]])
                args.append(f"value={cfg['weight']!r}")
                if cfg["cell_agg"] != "sum":
                    args.append(f"agg={cfg['cell_agg']!r}")
            bins = int(cfg["bins"] or 40)
            if not 5 <= bins <= 150:
                raise ToolError("Use between 5 and 150 cells across")
            smooth = 1.0 if cfg["smooth"] in (None, "") else float(cfg["smooth"])
            if not 0 <= smooth <= 10:
                raise ToolError("Smooth by between 0 and 10 cells")
            if bins != 40:
                args.append(f"bins={bins}")
            if smooth != 1.0:
                args.append(f"smooth={smooth}")
            if cfg["color_scale"] != "linear":
                args.append(f"color_scale={cfg['color_scale']!r}")
            if cfg["basemap"] != "us":
                args.append(f"basemap={cfg['basemap']!r}")
        elif kind in ("states", "counties"):
            ctx.require(cfg["region"], "Pick the region column")
            ctx.require_columns([cfg["region"]])
            args.append(f"region={cfg['region']!r}")
            if cfg["value"]:
                require_numeric(ctx, [cfg["value"]])
                args.append(f"value={cfg['value']!r}")
                if cfg["agg"] != "sum":
                    args.append(f"agg={cfg['agg']!r}")
        else:
            ctx.require(cfg["geometry"], "Pick the shape column")
            ctx.require_columns([cfg["geometry"]] + [c for c in (cfg["value"],) + tuple(cfg["tooltip"] or []) if c])
            if cfg["value"]:
                require_numeric(ctx, [cfg["value"]])
                args.append(f"value={cfg['value']!r}")
            if cfg["geometry"] != "geometry":
                args.append(f"geometry={cfg['geometry']!r}")
        if kind in ("points", "regions"):
            tip = [c for c in cfg["tooltip"] or [] if c]
            if tip:
                ctx.require_columns(tip)
                args.append(f"tooltip={tip!r}")
            limit = int(cfg["max_rows"] or 5000)
            if not 1 <= limit <= 100000:
                raise ToolError("Draw between 1 and 100,000 rows")
            if limit != 5000:
                args.append(f"max_rows={limit}")
        if cfg["scheme"] != "blues":
            args.append(f"scheme={cfg['scheme']!r}")
        if cfg["title"]:
            args.append(f"title={cfg['title']!r}")
        return f"{ctx.out()} = map_chart({', '.join(args)})"

    def summary(self, cfg):
        if cfg["kind"] == "points":
            return short(f"points: {cfg['lat']}, {cfg['lon']}") if cfg["lat"] and cfg["lon"] else ""
        if cfg["kind"] == "density":
            return short(f"heat map: {cfg['weight'] or 'row count'}") if cfg["lat"] and cfg["lon"] else ""
        label = {"states": "states", "counties": "counties", "regions": "regions"}[cfg["kind"]]
        return short(f"{label}: {cfg['value'] or 'row count'}")


@register
class GeocodeAddresses(Tool):
    type = "geocode"
    label = "Geocode Addresses"
    category = "Maps"
    group = "Places"
    description = "Turn US street addresses into latitude and longitude with the US Census Bureau's free geocoder. The addresses are sent to geocoding.geo.census.gov."
    needs = "A table with an address column, or with street, city, state and ZIP columns. US addresses only."
    fields = [
        fld("mode", "Addresses are in", "select", "one", options=opts(("one", "One column (the whole address)"), ("parts", "Separate columns"))),
        fld("address", "Address", "column", "", show_if={"mode": ["one"]}, help="For example 1600 Pennsylvania Ave NW, Washington, DC 20500."),
        fld("street", "Street", "column", "", show_if={"mode": ["parts"]}),
        fld("city", "City (optional)", "column", "", show_if={"mode": ["parts"]}),
        fld("state", "State (optional)", "column", "", show_if={"mode": ["parts"]}),
        fld("zip_code", "ZIP code (optional)", "column", "", show_if={"mode": ["parts"]}),
    ]

    def code(self, cfg, ctx):
        if cfg["mode"] == "one":
            ctx.require(cfg["address"], "Pick the address column")
            ctx.require_columns([cfg["address"]])
            args = [ctx.var(), f"address={cfg['address']!r}"]
        else:
            ctx.require(cfg["street"], "Pick the street column")
            parts = {k: cfg[k] for k in ("street", "city", "state", "zip_code") if cfg[k]}
            ctx.require_columns(list(parts.values()))
            args = [ctx.var()] + [f"{k}={v!r}" for k, v in parts.items()]
        return f"{ctx.out()} = geocode_addresses({', '.join(args)})"

    def summary(self, cfg):
        return short(cfg["address"] if cfg["mode"] == "one" else cfg["street"] or "")


@register
class Distance(Tool):
    type = "distance"
    label = "Distance"
    category = "Maps"
    group = "Places"
    description = "Add the straight-line distance over the Earth between two points in each row, and optionally the compass direction from the first to the second."
    needs = "A table with latitude and longitude columns for two points."
    fields = [
        fld("lat1", "From latitude", "column", ""),
        fld("lon1", "From longitude", "column", ""),
        fld("lat2", "To latitude", "column", ""),
        fld("lon2", "To longitude", "column", ""),
        fld("unit", "Unit", "select", "mi", options=UNITS),
        fld("name", "Distance column", "text", "distance"),
        fld("bearing", "Also add the direction (degrees from north)", "bool", False),
        fld("bearing_name", "Direction column", "text", "bearing", show_if={"bearing": ["true"]}),
    ]

    def code(self, cfg, ctx):
        cols = [cfg["lat1"], cfg["lon1"], cfg["lat2"], cfg["lon2"]]
        if not all(cols):
            raise ToolError("Pick all four coordinate columns")
        require_numeric(ctx, cols)
        name = str(cfg["name"] or "").strip()
        ctx.require(name, "Enter a name for the distance column")
        args = [ctx.var()] + [repr(c) for c in cols] + [f"unit={cfg['unit']!r}", f"name={name!r}"]
        if cfg["bearing"]:
            direction = str(cfg["bearing_name"] or "").strip()
            ctx.require(direction, "Enter a name for the direction column")
            args.append(f"bearing={direction!r}")
        return f"{ctx.out()} = distance_between({', '.join(args)})"

    def summary(self, cfg):
        return short(f"{cfg['name']} in {cfg['unit']}") if cfg["lat1"] else ""


@register
class FindNearest(Tool):
    type = "find_nearest"
    label = "Find Nearest"
    category = "Maps"
    group = "Places"
    description = "For each row, find the nearest places in a second table, or every place within a distance. Gives one row per match with the distance and rank, plus columns from the place."
    needs = "targets: the rows to look from, with latitude and longitude. places: the table to look in, with latitude and longitude."
    inputs = [Port("in", "targets"), Port("places", "places")]
    fields = [
        fld("lat", "Target latitude", "column", "", port="in"),
        fld("lon", "Target longitude", "column", "", port="in"),
        fld("place_lat", "Place latitude", "column", "", port="places"),
        fld("place_lon", "Place longitude", "column", "", port="places"),
        fld("count", "How many nearest places", "number", 1, help="Use 0 to get every place within the distance below."),
        fld("max_distance", "Only within this distance (0 for no limit)", "number", 0),
        fld("unit", "Unit", "select", "mi", options=UNITS),
        fld("columns", "Columns to bring from the places", "columns", [], port="places", help="Blank brings every column."),
        fld("keep_unmatched", "Keep target rows that have no match", "bool", True),
        fld("rank_name", "Rank column", "text", "nearest_rank"),
        fld("distance_name", "Distance column", "text", "distance"),
    ]

    def code(self, cfg, ctx):
        ctx.require(cfg["lat"] and cfg["lon"], "Pick the target latitude and longitude columns")
        ctx.require(cfg["place_lat"] and cfg["place_lon"], "Pick the place latitude and longitude columns")
        require_numeric(ctx, [cfg["lat"], cfg["lon"]], "in")
        require_numeric(ctx, [cfg["place_lat"], cfg["place_lon"]], "places")
        count = int(cfg["count"] or 0)
        limit = float(cfg["max_distance"] or 0)
        if count < 0 or limit < 0:
            raise ToolError("The count and the distance cannot be negative")
        if count == 0 and limit == 0:
            raise ToolError("Set a distance when you ask for every place within it")
        names = [str(cfg["rank_name"] or "").strip(), str(cfg["distance_name"] or "").strip()]
        if not all(names):
            raise ToolError("Name the rank and distance columns")
        cols = list(cfg["columns"] or [])
        if cols:
            ctx.require_columns(cols, "places")
        args = [ctx.var("in"), ctx.var("places"), repr(cfg["lat"]), repr(cfg["lon"]), repr(cfg["place_lat"]), repr(cfg["place_lon"]), f"count={count}", f"max_distance={limit:g}", f"unit={cfg['unit']!r}", f"keep_unmatched={bool(cfg['keep_unmatched'])}"]
        if cols:
            args.append(f"columns={cols!r}")
        if names != ["nearest_rank", "distance"]:
            args += [f"rank_name={names[0]!r}", f"distance_name={names[1]!r}"]
        return f"{ctx.out()} = find_nearest({', '.join(args)})"

    def summary(self, cfg):
        count = int(cfg["count"] or 0)
        return short(f"nearest {count}" if count else f"all within {cfg['max_distance']} {cfg['unit']}") if cfg["lat"] else ""


@register
class ReadMapFile(Tool):
    type = "read_map"
    label = "Read Map File"
    category = "Maps"
    group = "Boundaries"
    description = "Read a shapefile (.shp with its .dbf) or a GeoJSON file. Each shape becomes a row with its attributes, a center point (latitude and longitude) and the shape itself in a geometry column."
    needs = "No input. A shapefile or GeoJSON file in latitude and longitude (WGS 84). Shapefiles in other projections must be converted first."
    inputs = []
    fields = [
        fld("path", "File", "file", "", help="A .shp file (its .dbf must sit beside it) or a .geojson or .json file."),
        fld("geometry", "Keep the shapes", "bool", True, help="Needed to draw regions or to use Find Region. Turn it off for a smaller table."),
    ]

    def code(self, cfg, ctx):
        ctx.require(str(cfg["path"] or "").strip(), "Pick a shapefile or GeoJSON file")
        extra = "" if cfg["geometry"] else ", include_geometry=False"
        return f"{ctx.out()} = read_map_file({cfg['path']!r}{extra})"

    def stamp(self, cfg, inputs=None):
        path = str(cfg["path"] or "")
        base = os.path.splitext(path)[0]
        return file_stamp(path) + ("|" + file_stamp(base + ".dbf") if path.lower().endswith(".shp") else "")

    def summary(self, cfg):
        return short(os.path.basename(cfg["path"] or ""))


@register
class FindRegion(Tool):
    type = "find_region"
    label = "Find Region"
    category = "Maps"
    group = "Boundaries"
    description = "For each point, find the region (shape) it falls in and add that region's columns. A point in two regions gets the first one."
    needs = "points: a table with latitude and longitude. regions: a table from Read Map File with the shapes kept."
    inputs = [Port("in", "points"), Port("regions", "regions")]
    fields = [
        fld("lat", "Latitude", "column", "", port="in"),
        fld("lon", "Longitude", "column", "", port="in"),
        fld("geometry", "Shape column", "column", "geometry", port="regions"),
        fld("columns", "Columns to add from the regions", "columns", [], port="regions", help="Blank adds every column except the shape."),
        fld("keep_unmatched", "Keep points that fall in no region", "bool", True),
    ]

    def code(self, cfg, ctx):
        ctx.require(cfg["lat"] and cfg["lon"], "Pick the latitude and longitude columns")
        require_numeric(ctx, [cfg["lat"], cfg["lon"]])
        ctx.require(cfg["geometry"], "Pick the shape column")
        ctx.require_columns([cfg["geometry"]], "regions")
        cols = list(cfg["columns"] or [])
        if cols:
            ctx.require_columns(cols, "regions")
        args = [ctx.var("in"), ctx.var("regions"), repr(cfg["lat"]), repr(cfg["lon"])]
        if cfg["geometry"] != "geometry":
            args.append(f"geometry={cfg['geometry']!r}")
        if cols:
            args.append(f"columns={cols!r}")
        if not cfg["keep_unmatched"]:
            args.append("keep_unmatched=False")
        return f"{ctx.out()} = find_region({', '.join(args)})"

    def summary(self, cfg):
        return short(f"{cfg['lat']}, {cfg['lon']}") if cfg["lat"] and cfg["lon"] else ""
