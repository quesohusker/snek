from snek.tools.base import Port, Tool, ToolError, fld, is_numeric, lit, opts, register, short

TASKS = opts(("auto", "Decide from the target"), ("classification", "Classification (categories)"), ("regression", "Regression (numbers)"))


def target_fields(numeric_only=False):
    help_text = "Numeric columns." if numeric_only else "Text columns become yes/no indicator columns automatically."
    return [
        fld("target", "Predict (target)", "column", ""),
        fld("predictors", "Using (predictors)", "columns", [], help=f"{help_text} Rows with a null in the target or any predictor are left out of the fit."),
    ]


def check_target(cfg, ctx, numeric_only=False):
    target = cfg["target"]
    preds = [p for p in cfg["predictors"] or [] if p != target]
    ctx.require(target, "Pick the column to predict")
    ctx.require(preds, "Pick at least one predictor")
    ctx.require_columns([target] + preds)
    if numeric_only:
        bad = [c for c in [target] + preds if not is_numeric(ctx.dtype(c))]
        if bad:
            raise ToolError(f"Not numeric: {', '.join(bad)}. Use Auto Field or Select to convert them.")
    return target, preds


def num(value, cast=int):
    return None if value in (None, "", 0) else cast(value)


@register
class LinearRegression(Tool):
    type = "linear_regression"
    label = "Linear Regression"
    category = "Modeling"
    description = "Fit an ordinary least squares model. S = rows with predictions, C = coefficients with p-values, F = fit statistics, M = model for Score."
    outputs = [Port("scored", "S"), Port("coef", "C"), Port("fit", "F"), Port("model", "M")]
    fields = target_fields(numeric_only=True) + [fld("intercept", "Include an intercept", "bool", True)]

    def code(self, cfg, ctx):
        target, preds = check_target(cfg, ctx, numeric_only=True)
        outs = ", ".join(ctx.out(p) for p in ("scored", "coef", "fit"))
        icpt = "" if cfg["intercept"] else ", intercept=False"
        return "\n".join([
            f"{outs} = linear_regression({ctx.var()}, {target!r}, {lit(preds)}{icpt})",
            f"{ctx.out('model')} = linear_model_row({ctx.var()}, {target!r}, {lit(preds)}, {ctx.out('coef')}{icpt})",
        ])

    def summary(self, cfg):
        return short(f"{cfg['target']} ~ {' + '.join(cfg['predictors'] or [])}") if cfg["target"] else ""


@register
class LogisticRegression(Tool):
    type = "logistic_regression"
    label = "Logistic Regression"
    category = "Modeling"
    description = "Predict a yes/no outcome, such as win or loss. M = model for Score, C = coefficients with odds ratios and p-values, F = fit statistics."
    outputs = [Port("model", "M"), Port("coef", "C"), Port("fit", "F")]
    fields = target_fields() + [fld("positive", "Positive outcome", "text", "", placeholder="auto: the last value alphabetically", help="The value the model gives a probability for, e.g. W or 1.")]

    def code(self, cfg, ctx):
        target, preds = check_target(cfg, ctx)
        pos = f", positive={cfg['positive']!r}" if cfg["positive"] else ""
        outs = ", ".join(ctx.out(p) for p in ("model", "coef", "fit"))
        return f"{outs} = fit_logistic({ctx.var()}, {target!r}, {lit(preds)}{pos})"

    def summary(self, cfg):
        return short(f"{cfg['target']} ~ {' + '.join(cfg['predictors'] or [])}") if cfg["target"] else ""


class TreeModel(Tool):
    algorithm = ""
    category = "Modeling"
    outputs = [Port("model", "M"), Port("importance", "I")]

    def params(self, cfg):
        return {}

    def code(self, cfg, ctx):
        target, preds = check_target(cfg, ctx)
        params = {k: v for k, v in self.params(cfg).items() if v is not None}
        args = [ctx.var(), repr(target), lit(preds), repr(self.algorithm), f"task={cfg['task']!r}", f"seed={int(cfg['seed'] or 0)}"]
        args += [f"{k}={v!r}" for k, v in params.items()]
        outs = ", ".join(ctx.out(p.name) for p in self.outputs)
        return f"{outs} = fit_supervised({', '.join(args)})"

    def summary(self, cfg):
        return short(f"{cfg['target']} ~ {len(cfg['predictors'] or [])} predictors") if cfg["target"] else ""


@register
class DecisionTree(TreeModel):
    type = "decision_tree"
    label = "Decision Tree"
    algorithm = "tree"
    description = "A tree of if-then splits you can read. M = model for Score, I = which predictors matter most, R = the rules as text."
    outputs = [Port("model", "M"), Port("importance", "I"), Port("rules", "R")]
    fields = target_fields() + [
        fld("task", "Type", "select", "auto", options=TASKS),
        fld("max_depth", "Maximum depth (0 = no limit)", "number", 4),
        fld("min_samples_leaf", "Minimum rows per leaf", "number", 5),
        fld("seed", "Random seed", "number", 1),
    ]

    def params(self, cfg):
        return {"max_depth": num(cfg["max_depth"]), "min_samples_leaf": num(cfg["min_samples_leaf"]) or 1}


@register
class RandomForest(TreeModel):
    type = "random_forest"
    label = "Random Forest"
    algorithm = "forest"
    description = "Many decision trees voting together. Accurate and hard to overfit. M = model for Score, I = predictor importance."
    fields = target_fields() + [
        fld("task", "Type", "select", "auto", options=TASKS),
        fld("trees", "Number of trees", "number", 200),
        fld("max_depth", "Maximum depth (0 = no limit)", "number", 0),
        fld("seed", "Random seed", "number", 1),
    ]

    def params(self, cfg):
        return {"n_estimators": num(cfg["trees"]) or 100, "max_depth": num(cfg["max_depth"])}


@register
class BoostedModel(TreeModel):
    type = "boosted_model"
    label = "Boosted Model"
    algorithm = "boosted"
    description = "Gradient boosting: trees built one after another, each fixing the last one's errors. M = model for Score, I = predictor importance."
    fields = target_fields() + [
        fld("task", "Type", "select", "auto", options=TASKS),
        fld("trees", "Number of trees", "number", 100),
        fld("learning_rate", "Learning rate", "number", 0.1),
        fld("max_depth", "Depth of each tree", "number", 3),
        fld("seed", "Random seed", "number", 1),
    ]

    def params(self, cfg):
        return {"n_estimators": num(cfg["trees"]) or 100, "learning_rate": num(cfg["learning_rate"], float) or 0.1, "max_depth": num(cfg["max_depth"]) or 3}


@register
class Score(Tool):
    type = "score"
    label = "Score"
    category = "Modeling"
    description = "Apply a fitted model to new rows. Connect a model's M output to M and the data to score to D."
    inputs = [Port("model", "M"), Port("data", "D")]
    fields = []

    def code(self, cfg, ctx):
        return f"{ctx.out()} = score_model({ctx.var('model')}, {ctx.var('data')})"


@register
class ModelComparison(Tool):
    type = "model_comparison"
    label = "Model Comparison"
    category = "Modeling"
    description = "Score one or more models on data they did not see, usually the validation sample. E = accuracy measures per model, C = confusion matrix."
    inputs = [Port("model", "M", multi=True), Port("data", "D")]
    outputs = [Port("metrics", "E"), Port("confusion", "C")]
    fields = []

    def code(self, cfg, ctx):
        outs = f"{ctx.out('metrics')}, {ctx.out('confusion')}"
        return f"{outs} = compare_models([{', '.join(ctx.vars('model'))}], {ctx.var('data')})"


@register
class CreateSamples(Tool):
    type = "create_samples"
    label = "Create Samples"
    category = "Modeling"
    description = "Split rows at random into estimation (E), validation (V) and holdout (H) sets, so you can test a model on data it never saw."
    outputs = [Port("estimation", "E"), Port("validation", "V"), Port("holdout", "H")]
    fields = [
        fld("estimation", "Estimation %", "number", 70),
        fld("validation", "Validation %", "number", 30),
        fld("seed", "Random seed", "number", 1),
    ]

    def code(self, cfg, ctx):
        e, v = float(cfg["estimation"] or 0), float(cfg["validation"] or 0)
        if e < 0 or v < 0 or e + v > 100:
            raise ToolError("Estimation and validation must be 0 to 100 and add up to 100 or less. The rest goes to holdout.")
        outs = ", ".join(ctx.out(p) for p in ("estimation", "validation", "holdout"))
        return f"{outs} = split_samples({ctx.var()}, {e:g}, {v:g}, seed={int(cfg['seed'] or 0)})"

    def summary(self, cfg):
        e, v = float(cfg["estimation"] or 0), float(cfg["validation"] or 0)
        return f"{e:g} / {v:g} / {max(100 - e - v, 0):g}"
