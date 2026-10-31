from snek.tools.base import Port, Tool, ToolError, fld, lit, register, short

CATEGORY = "Predictive Grouping"


@register
class KMeans(Tool):
    type = "kmeans"
    label = "K-Means Clusters"
    category = CATEGORY
    description = "Group similar rows into K clusters. D = data with a Cluster column, C = cluster centers and sizes, M = model to assign new rows with Score."
    outputs = [Port("data", "D"), Port("centers", "C"), Port("model", "M")]
    fields = [
        fld("features", "Columns to cluster on", "columns", []),
        fld("k", "Number of clusters", "number", 3),
        fld("standardize", "Put columns on the same scale first", "bool", True, help="Recommended when columns use different units, like yards and points."),
        fld("seed", "Random seed", "number", 1),
    ]

    def code(self, cfg, ctx):
        feats = cfg["features"] or []
        ctx.require(feats, "Pick the columns to cluster on")
        ctx.require_columns(feats)
        k = int(cfg["k"] or 0)
        if k < 2:
            raise ToolError("Use at least 2 clusters")
        outs = ", ".join(ctx.out(p) for p in ("data", "centers", "model"))
        return f"{outs} = kmeans_cluster({ctx.var()}, {lit(feats)}, k={k}, standardize={bool(cfg['standardize'])}, seed={int(cfg['seed'] or 0)})"

    def summary(self, cfg):
        return f"{cfg['k']} clusters" if cfg["features"] else ""


@register
class PrincipalComponents(Tool):
    type = "pca"
    label = "Principal Components"
    category = CATEGORY
    description = "Squeeze many related columns into a few components. D = data with PC columns, L = loadings, V = variance explained, M = model for Score."
    outputs = [Port("data", "D"), Port("loadings", "L"), Port("variance", "V"), Port("model", "M")]
    fields = [
        fld("features", "Columns", "columns", []),
        fld("components", "Number of components", "number", 2),
        fld("standardize", "Put columns on the same scale first", "bool", True),
    ]

    def code(self, cfg, ctx):
        feats = cfg["features"] or []
        ctx.require(feats, "Pick at least two columns")
        ctx.require_columns(feats)
        n = int(cfg["components"] or 0)
        if n < 1:
            raise ToolError("Use at least 1 component")
        outs = ", ".join(ctx.out(p) for p in ("data", "loadings", "variance", "model"))
        return f"{outs} = principal_components({ctx.var()}, {lit(feats)}, components={n}, standardize={bool(cfg['standardize'])})"

    def summary(self, cfg):
        return short(f"{cfg['components']} from {len(cfg['features'] or [])} columns") if cfg["features"] else ""
