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
    category = "Model"
    description = "Fit an ordinary least squares model. Outputs: rows with predictions, coefficients with p-values, fit statistics, and a model for Predict."
    needs = "One row per observation with a numeric target column and one or more predictor columns."
    outputs = [Port("scored", "scored"), Port("coef", "coefficients"), Port("fit", "fit"), Port("model", "model")]
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
    category = "Model"
    description = "Predict a yes/no outcome, such as win or loss. Outputs: a model for Predict, coefficients with odds ratios and p-values, and fit statistics."
    needs = "One row per observation with a yes/no target column (two values) and predictor columns."
    outputs = [Port("model", "model"), Port("coef", "coefficients"), Port("fit", "fit")]
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
    category = "Model"
    outputs = [Port("model", "model"), Port("importance", "importance")]

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
    description = "A tree of if-then splits you can read. Outputs: a model for Predict, which predictors matter most, and the rules as text."
    needs = "One row per observation with a target column (category or number) and predictor columns."
    outputs = [Port("model", "model"), Port("importance", "importance"), Port("rules", "rules")]
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
    description = "Many decision trees voting together. Accurate and hard to overfit. Outputs: a model for Predict, and predictor importance."
    needs = "One row per observation with a target column (category or number) and predictor columns."
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
    label = "Gradient Boosting"
    algorithm = "boosted"
    description = "Gradient boosting: trees built one after another, each fixing the last one's errors. Outputs: a model for Predict, and predictor importance."
    needs = "One row per observation with a target column (category or number) and predictor columns."
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
    label = "Predict"
    category = "Model"
    description = "Apply a fitted model to new rows. Connect a model output to the model input, and the rows to predict to the data input."
    needs = "model: the model output of any model tool. data: rows with the same predictor columns."
    inputs = [Port("model", "model"), Port("data", "data")]
    fields = []

    def code(self, cfg, ctx):
        return f"{ctx.out()} = score_model({ctx.var('model')}, {ctx.var('data')})"


@register
class ModelComparison(Tool):
    type = "model_comparison"
    label = "Compare Models"
    category = "Model"
    description = "Grade one or more models on data they did not see, usually the validation sample. Outputs: accuracy measures per model, and a confusion matrix."
    needs = "model: one or more model outputs. data: rows the models did not train on, with the target column."
    inputs = [Port("model", "model", multi=True), Port("data", "data")]
    outputs = [Port("metrics", "metrics"), Port("confusion", "confusion")]
    fields = []

    def code(self, cfg, ctx):
        outs = f"{ctx.out('metrics')}, {ctx.out('confusion')}"
        return f"{outs} = compare_models([{', '.join(ctx.vars('model'))}], {ctx.var('data')})"


@register
class CreateSamples(Tool):
    type = "create_samples"
    label = "Train and Test Split"
    category = "Model"
    description = "Split rows at random into train, validation and holdout sets, so you can test a model on data it never saw."
    needs = "Any table to split."
    outputs = [Port("estimation", "train"), Port("validation", "validation"), Port("holdout", "holdout")]
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


@register
class RegularizedRegression(Tool):
    type = "regularized"
    label = "Ridge and Lasso"
    category = "Model"
    description = "Ridge, Lasso or Elastic Net: linear regression that shrinks weak predictors. Lasso drops them to zero. Outputs: model, coefficients, and fit."
    needs = "One row per observation with a numeric target column and predictor columns."
    outputs = [Port("model", "model"), Port("coef", "coefficients"), Port("fit", "fit")]
    fields = target_fields() + [
        fld("method", "Method", "select", "lasso", options=opts(("ridge", "Ridge"), ("lasso", "Lasso"), ("elasticnet", "Elastic Net"))),
        fld("alpha", "Strength (0 = choose by cross-validation)", "number", 0),
        fld("l1_ratio", "Lasso share (Elastic Net)", "number", 0.5, show_if={"method": ["elasticnet"]}),
        fld("seed", "Random seed", "number", 1),
    ]

    def code(self, cfg, ctx):
        target, preds = check_target(cfg, ctx)
        if not is_numeric(ctx.dtype(target)):
            raise ToolError(f"{target} must be numeric")
        args = [ctx.var(), repr(target), lit(preds), f"method={cfg['method']!r}"]
        if cfg["alpha"]:
            args.append(f"alpha={float(cfg['alpha'])!r}")
        if cfg["method"] == "elasticnet":
            ratio = float(cfg["l1_ratio"] or 0.5)
            if not 0 < ratio <= 1:
                raise ToolError("Lasso share must be above 0 and at most 1")
            args.append(f"l1_ratio={ratio!r}")
        args.append(f"seed={int(cfg['seed'] or 0)}")
        outs = ", ".join(ctx.out(p) for p in ("model", "coef", "fit"))
        return f"{outs} = fit_regularized({', '.join(args)})"

    def summary(self, cfg):
        return short(f"{cfg['method']}: {cfg['target']}") if cfg["target"] else ""


class GLMTool(Tool):
    category = "Model"
    outputs = [Port("model", "model"), Port("coef", "coefficients"), Port("fit", "fit")]

    def family(self, cfg):
        return "poisson"

    def code(self, cfg, ctx):
        target, preds = check_target(cfg, ctx)
        if not is_numeric(ctx.dtype(target)):
            raise ToolError(f"{target} must be numeric")
        outs = ", ".join(ctx.out(p) for p in ("model", "coef", "fit"))
        return f"{outs} = fit_glm({ctx.var()}, {target!r}, {lit(preds)}, family={self.family(cfg)!r})"

    def summary(self, cfg):
        return short(f"{cfg['target']} ~ {' + '.join(cfg['predictors'] or [])}") if cfg["target"] else ""


@register
class CountRegression(GLMTool):
    type = "count_regression"
    label = "Count Regression"
    description = "Model counts like touchdowns or turnovers. Poisson, or negative binomial when counts vary more than Poisson allows. Ratio = multiplier per unit."
    needs = "One row per observation with a count target (0, 1, 2...) and predictor columns."
    fields = target_fields() + [fld("family", "Model", "select", "poisson", options=opts(("poisson", "Poisson"), ("negbin", "Negative binomial")))]

    def family(self, cfg):
        return cfg["family"]


@register
class GammaRegression(GLMTool):
    type = "gamma_regression"
    label = "Gamma Regression"
    description = "Model positive, right-skewed amounts like yards per drive or game duration. Uses a log link, so Ratio = multiplier per unit."
    needs = "One row per observation with a positive numeric target and predictor columns."
    fields = target_fields()

    def family(self, cfg):
        return "gamma"


class EstimatorTool(Tool):
    algorithm = ""
    category = "Model"
    outputs = [Port("model", "model"), Port("importance", "importance"), Port("fit", "fit")]

    def extra(self, cfg):
        return {}

    def code(self, cfg, ctx):
        target, preds = check_target(cfg, ctx)
        args = [ctx.var(), repr(target), lit(preds), repr(self.algorithm), f"task={cfg.get('task', 'auto')!r}", f"seed={int(cfg.get('seed') or 1)}"]
        args += [f"{k}={v!r}" for k, v in self.extra(cfg).items()]
        outs = ", ".join(ctx.out(p) for p in ("model", "importance", "fit"))
        return f"{outs} = fit_estimator({', '.join(args)})"

    def summary(self, cfg):
        return short(f"{cfg['target']} ~ {len(cfg['predictors'] or [])} predictors") if cfg["target"] else ""


@register
class NaiveBayes(EstimatorTool):
    type = "naive_bayes"
    label = "Naive Bayes"
    algorithm = "naive_bayes"
    description = "A fast, simple classifier that is a good baseline to beat. Outputs: model, importance (score drop when a column is shuffled), and fit."
    needs = "One row per observation with a category target column and predictor columns."
    fields = target_fields() + [fld("seed", "Random seed", "number", 1)]


@register
class KNearestNeighbors(EstimatorTool):
    type = "knn"
    label = "Nearest-Neighbor Model"
    algorithm = "knn"
    description = "Predict from the K most similar rows. Columns are scaled first. Outputs: model, importance, and fit."
    needs = "One row per observation with a target column and numeric predictor columns."
    fields = target_fields() + [
        fld("task", "Type", "select", "auto", options=TASKS),
        fld("k", "Neighbors (K)", "number", 5),
        fld("seed", "Random seed", "number", 1),
    ]

    def extra(self, cfg):
        k = int(cfg["k"] or 0)
        if k < 1:
            raise ToolError("K must be at least 1")
        return {"k": k}


@register
class SupportVectorMachine(EstimatorTool):
    type = "svm"
    label = "Support Vector Machine"
    algorithm = "svm"
    description = "Find the boundary with the widest margin between classes, or a tube around the target for numbers. Columns are scaled first."
    needs = "One row per observation with a target column and numeric predictor columns."
    fields = target_fields() + [
        fld("task", "Type", "select", "auto", options=TASKS),
        fld("kernel", "Kernel", "select", "rbf", options=opts(("rbf", "Radial (curved)"), ("linear", "Linear"), ("poly", "Polynomial"))),
        fld("c", "Penalty (C)", "number", 1),
        fld("seed", "Random seed", "number", 1),
    ]

    def extra(self, cfg):
        return {"kernel": cfg["kernel"], "c": float(cfg["c"] or 1)}


@register
class NeuralNetwork(EstimatorTool):
    type = "neural_network"
    label = "Neural Network"
    algorithm = "mlp"
    description = "A multi-layer perceptron for classification or regression. Columns are scaled first. Set the hidden layer sizes, such as 50 or 64, 32."
    needs = "One row per observation with a target column and numeric predictor columns."
    fields = target_fields() + [
        fld("task", "Type", "select", "auto", options=TASKS),
        fld("hidden", "Hidden layers", "text", "50", help="Neurons per layer, separated by commas. 64, 32 means two layers."),
        fld("seed", "Random seed", "number", 1),
    ]

    def extra(self, cfg):
        text = str(cfg["hidden"] or "50").replace(" ", "")
        if not all(p.isdigit() and int(p) > 0 for p in text.split(",")):
            raise ToolError("Hidden layers must be positive whole numbers separated by commas")
        return {"hidden": text}


@register
class CrossValidation(Tool):
    type = "cross_validation"
    label = "Cross-Validation"
    category = "Model"
    description = "Refit each connected model on K slices of the data and score it on the slice it did not see. Outputs: average and spread per model, and every fold."
    needs = "model: one or more model outputs. data: the table to slice, with the target and predictor columns."
    inputs = [Port("model", "model", multi=True), Port("data", "data")]
    outputs = [Port("summary", "summary"), Port("folds", "folds")]
    fields = [fld("folds", "Folds (K)", "number", 5), fld("seed", "Random seed", "number", 1)]

    def code(self, cfg, ctx):
        k = int(cfg["folds"] or 0)
        if k < 2:
            raise ToolError("Use at least 2 folds")
        outs = f"{ctx.out('summary')}, {ctx.out('folds')}"
        return f"{outs} = cross_validate([{', '.join(ctx.vars('model'))}], {ctx.var('data')}, folds={k}, seed={int(cfg['seed'] or 0)})"

    def summary(self, cfg):
        return f"{cfg['folds']} folds"


@register
class VarianceInflation(Tool):
    type = "vif"
    label = "Check Overlap (VIF)"
    category = "Model"
    description = "Spot predictors that largely repeat each other. A VIF above 5 is worth a look; above 10 usually means drop or combine one."
    needs = "A table with two or more numeric predictor columns."
    fields = [fld("predictors", "Predictors", "columns", [])]

    def code(self, cfg, ctx):
        preds = cfg["predictors"] or []
        ctx.require(preds, "Pick at least two predictors")
        ctx.require_columns(preds)
        return f"{ctx.out()} = vif_table({ctx.var()}, {lit(preds)})"

    def summary(self, cfg):
        return short(", ".join(cfg["predictors"] or []))
