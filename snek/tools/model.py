from snek.tools.base import Port, Tool, ToolError, fld, is_numeric, lit, register, short


@register
class LinearRegression(Tool):
    type = "linear_regression"
    label = "Linear Regression"
    category = "Modeling"
    description = "Fit an ordinary least squares model. S = rows with predictions and residuals, C = coefficients with p-values, F = fit statistics."
    outputs = [Port("scored", "S"), Port("coef", "C"), Port("fit", "F")]
    fields = [
        fld("target", "Predict (target)", "column", ""),
        fld("predictors", "Using (predictors)", "columns", [], help="Numeric columns. Rows with a null in the target or any predictor are left out of the fit."),
        fld("intercept", "Include an intercept", "bool", True),
    ]

    def code(self, cfg, ctx):
        target = cfg["target"]
        preds = [p for p in cfg["predictors"] or [] if p != target]
        ctx.require(target, "Pick the column to predict")
        ctx.require(preds, "Pick at least one predictor")
        ctx.require_columns([target] + preds)
        bad = [c for c in [target] + preds if not is_numeric(ctx.dtype(c))]
        if bad:
            raise ToolError(f"Not numeric: {', '.join(bad)}. Use Auto Field or Select to convert them.")
        outs = ", ".join(ctx.out(p) for p in ("scored", "coef", "fit"))
        icpt = "" if cfg["intercept"] else ", intercept=False"
        return f"{outs} = linear_regression({ctx.var()}, {target!r}, {lit(preds)}{icpt})"

    def summary(self, cfg):
        return short(f"{cfg['target']} ~ {' + '.join(cfg['predictors'] or [])}") if cfg["target"] else ""
