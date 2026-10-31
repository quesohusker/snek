from snek.tools.base import Port, Tool, ToolError, fld, lit, opts, register, short


@register
class Join(Tool):
    type = "join"
    label = "Join"
    category = "Join"
    description = "Match two inputs on key columns. L = left only, J = matched, R = right only."
    inputs = [Port("left", "L"), Port("right", "R")]
    outputs = [Port("left", "L"), Port("join", "J"), Port("right", "R")]
    fields = [
        fld("keys", "Join on", "list", [{"left": "", "right": ""}], fields=[
            fld("left", "Left column", "column", "", port="left"),
            fld("right", "Right column", "column", "", port="right"),
        ]),
        fld("suffix", "Suffix for duplicate right columns", "text", "_right"),
    ]

    def code(self, cfg, ctx):
        left = ctx.var("left")
        right = ctx.var("right")
        keys = [k for k in cfg["keys"] or [] if k.get("left") or k.get("right")]
        if not keys or any(not k.get("left") or not k.get("right") for k in keys):
            raise ToolError("Pick a left and right column for every key")
        lk = [k["left"] for k in keys]
        rk = [k["right"] for k in keys]
        ctx.require_columns(lk, "left")
        ctx.require_columns(rk, "right")
        outs = ", ".join(ctx.out(p) for p in ("left", "join", "right"))
        return f"{outs} = join_lrj({left}, {right}, {lit(lk)}, {lit(rk)}, suffix={lit(cfg['suffix'] or '_right')})"

    def summary(self, cfg):
        keys = [k for k in cfg["keys"] or [] if k.get("left")]
        return short(", ".join(k["left"] if k["left"] == k.get("right") else f"{k['left']}={k.get('right', '')}" for k in keys))


@register
class Union(Tool):
    type = "union"
    label = "Union"
    category = "Join"
    description = "Stack any number of inputs. Connect them in the order you want."
    inputs = [Port("in", "", multi=True)]
    fields = [
        fld("mode", "Match columns by", "select", "name", options=opts(("name", "Name, keep all columns"), ("common", "Name, common columns only"), ("position", "Position"))),
    ]

    def code(self, cfg, ctx):
        names = ctx.vars()
        out = ctx.out()
        if cfg["mode"] == "position":
            first = names[0]
            parts = [first] + [f"{n}.set_axis({first}.columns, axis=1)" for n in names[1:]]
            return f"{out} = pd.concat([{', '.join(parts)}], ignore_index=True)"
        join = ", join='inner'" if cfg["mode"] == "common" else ""
        return f"{out} = pd.concat([{', '.join(names)}], ignore_index=True{join})"

    def summary(self, cfg):
        return {"name": "by name", "common": "common columns", "position": "by position"}[cfg["mode"]]


@register
class AppendFields(Tool):
    type = "append"
    label = "Append Fields"
    category = "Join"
    description = "Cross join: add every source row to every target row."
    inputs = [Port("target", "T"), Port("source", "S")]
    fields = [fld("suffix", "Suffix for duplicate source columns", "text", "_source")]

    def code(self, cfg, ctx):
        return f"{ctx.out()} = {ctx.var('target')}.merge({ctx.var('source')}, how='cross', suffixes=('', {lit(cfg['suffix'] or '_source')}))"
