from snek.tools.base import Port, Tool, ToolError, fld, lit, register, short


@register
class KMeans(Tool):
    type = "kmeans"
    label = "K-Means Groups"
    category = "Segment"
    description = "Group similar rows into K clusters. Outputs: data with a Cluster column, cluster centers and sizes, and a model that Predict uses to assign new rows."
    needs = "One row per item to group (team, player, game) with numeric feature columns."
    outputs = [Port("data", "data"), Port("centers", "centers"), Port("model", "model")]
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
    category = "Segment"
    description = "Squeeze many related columns into a few components. Outputs: data with PC columns, loadings, variance explained, and a model for Predict."
    needs = "One row per item with several related numeric columns."
    outputs = [Port("data", "data"), Port("loadings", "loadings"), Port("variance", "variance"), Port("model", "model")]
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


@register
class ClusterDiagnostics(Tool):
    type = "cluster_diagnostics"
    label = "Choose Number of Groups"
    category = "Segment"
    description = "Try a range of K for K-Means and score each: within-cluster spread (look for the elbow) and silhouette (higher is better)."
    needs = "One row per item with numeric feature columns."
    fields = [
        fld("features", "Columns to cluster on", "columns", []),
        fld("k_min", "Smallest K", "number", 2),
        fld("k_max", "Largest K", "number", 8),
        fld("standardize", "Put columns on the same scale first", "bool", True),
        fld("seed", "Random seed", "number", 1),
    ]

    def code(self, cfg, ctx):
        feats = cfg["features"] or []
        ctx.require(feats, "Pick the columns to cluster on")
        ctx.require_columns(feats)
        lo, hi = int(cfg["k_min"] or 0), int(cfg["k_max"] or 0)
        if lo < 2 or hi < lo:
            raise ToolError("Smallest K must be at least 2 and no larger than Largest K")
        return f"{ctx.out()} = cluster_diagnostics({ctx.var()}, {lit(feats)}, k_min={lo}, k_max={hi}, standardize={bool(cfg['standardize'])}, seed={int(cfg['seed'] or 0)})"

    def summary(self, cfg):
        return f"K {cfg['k_min']}–{cfg['k_max']}" if cfg["features"] else ""


@register
class HierarchicalClustering(Tool):
    type = "hierarchical"
    label = "Hierarchical Groups"
    category = "Segment"
    description = "Merge the most similar rows step by step, then cut into K clusters. Outputs: data with a Cluster column, and cluster sizes and averages."
    needs = "One row per item with numeric feature columns."
    outputs = [Port("data", "data"), Port("summary", "summary")]
    fields = [
        fld("features", "Columns", "columns", []),
        fld("k", "Number of clusters", "number", 3),
        fld("linkage", "Linkage", "select", "ward", options=[{"value": v, "label": l} for v, l in (("ward", "Ward (compact clusters)"), ("complete", "Complete"), ("average", "Average"), ("single", "Single"))]),
        fld("standardize", "Put columns on the same scale first", "bool", True),
    ]

    def code(self, cfg, ctx):
        feats = cfg["features"] or []
        ctx.require(feats, "Pick the columns")
        ctx.require_columns(feats)
        k = int(cfg["k"] or 0)
        if k < 2:
            raise ToolError("Use at least 2 clusters")
        return f"{ctx.out('data')}, {ctx.out('summary')} = hierarchical_cluster({ctx.var()}, {lit(feats)}, k={k}, linkage={cfg['linkage']!r}, standardize={bool(cfg['standardize'])})"

    def summary(self, cfg):
        return f"{cfg['k']} clusters, {cfg['linkage']}" if cfg["features"] else ""


@register
class FindNearestNeighbors(Tool):
    type = "nearest_neighbors"
    label = "Most Similar Rows"
    category = "Segment"
    description = "For each row, list the K most similar other rows, such as the teams whose stat profile is closest to Nebraska's."
    needs = "One row per item with an ID column (such as team) and numeric feature columns."
    fields = [
        fld("id", "Label column", "column", "", help="What to call each row, like team."),
        fld("features", "Compare on", "columns", []),
        fld("k", "Neighbors per row", "number", 5),
        fld("standardize", "Put columns on the same scale first", "bool", True),
    ]

    def code(self, cfg, ctx):
        feats = cfg["features"] or []
        ctx.require(cfg["id"], "Pick the label column")
        ctx.require(feats, "Pick the columns to compare on")
        ctx.require_columns([cfg["id"]] + feats)
        k = int(cfg["k"] or 0)
        if k < 1:
            raise ToolError("Use at least 1 neighbor")
        return f"{ctx.out()} = nearest_neighbors({ctx.var()}, {cfg['id']!r}, {lit(feats)}, k={k}, standardize={bool(cfg['standardize'])})"

    def summary(self, cfg):
        return short(f"{cfg['k']} nearest by {len(cfg['features'] or [])} columns") if cfg["features"] else ""
