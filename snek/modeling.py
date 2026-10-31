import numpy as np
import pandas as pd


def design_matrix(df, features, columns=None, drop_first=False):
    X = pd.get_dummies(df[list(features)], drop_first=drop_first, dtype=float)
    X = X.apply(pd.to_numeric, errors="coerce").astype(float)
    if columns is not None:
        X = X.reindex(columns=list(columns), fill_value=0.0)
    return X


def model_row(model, algorithm, task, target, features, columns, rows, **extra):
    return pd.DataFrame([{"Model": model, "Algorithm": algorithm, "Task": task, "Target": target, "Features": list(features), "Columns": list(columns), "Rows used": int(rows), **extra}])


def guess_task(y):
    numeric = pd.api.types.is_numeric_dtype(y) and not pd.api.types.is_bool_dtype(y)
    return "regression" if numeric and y.nunique() > 10 else "classification"


def fit_supervised(df, target, features, algorithm, task="auto", seed=1, **params):
    from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor, RandomForestClassifier, RandomForestRegressor
    from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor, export_text

    estimators = {
        ("tree", "classification"): DecisionTreeClassifier,
        ("tree", "regression"): DecisionTreeRegressor,
        ("forest", "classification"): RandomForestClassifier,
        ("forest", "regression"): RandomForestRegressor,
        ("boosted", "classification"): GradientBoostingClassifier,
        ("boosted", "regression"): GradientBoostingRegressor,
    }
    features = [f for f in features if f != target]
    data = df[[target] + features].dropna()
    if data.empty:
        raise ValueError("No rows have a value in the target and every predictor")
    task = guess_task(data[target]) if task == "auto" else task
    X = design_matrix(data, features)
    y = data[target].astype(str) if task == "classification" else pd.to_numeric(data[target], errors="coerce")
    if task == "classification" and y.nunique() < 2:
        raise ValueError("The target needs at least two different values")
    model = estimators[(algorithm, task)](random_state=seed, **{k: v for k, v in params.items() if v is not None}).fit(X, y)
    importance = pd.DataFrame({"Feature": X.columns, "Importance": model.feature_importances_}).sort_values("Importance", ascending=False, ignore_index=True)
    info = model_row(model, algorithm, task, target, features, X.columns, len(data))
    if algorithm == "tree":
        rules = pd.DataFrame({"Rule": export_text(model, feature_names=list(X.columns), max_depth=6).splitlines()})
        return info, importance, rules
    return info, importance


def fit_logistic(df, target, features, positive=None):
    import warnings

    import statsmodels.api as sm

    features = [f for f in features if f != target]
    data = df[[target] + features].dropna()
    classes = sorted(data[target].astype(str).unique())
    if len(classes) != 2:
        raise ValueError(f"Logistic Regression needs a target with exactly two values; found {len(classes)}")
    positive = str(positive) if positive not in (None, "") else classes[-1]
    if positive not in classes:
        raise ValueError(f"{positive!r} is not a value of {target}; values are {classes}")
    negative = [c for c in classes if c != positive][0]
    X = design_matrix(data, features, drop_first=True)
    y = (data[target].astype(str) == positive).astype(float)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = sm.Logit(y, sm.add_constant(X, has_constant="add")).fit(disp=0, maxiter=200)
    if not result.mle_retvals.get("converged", True) or not np.isfinite(result.params).all():
        raise ValueError("The model did not converge. One predictor may separate the two classes perfectly, or there are too few rows.")
    coef = pd.DataFrame({
        "Term": ["(Intercept)" if t == "const" else t for t in result.params.index],
        "Coefficient": result.params.to_numpy(),
        "Odds Ratio": np.exp(result.params.to_numpy()),
        "Std Error": result.bse.to_numpy(),
        "z": result.tvalues.to_numpy(),
        "p-value": result.pvalues.to_numpy(),
    })
    accuracy = float(((result.predict() >= 0.5) == (y.to_numpy() == 1)).mean())
    fit = pd.DataFrame({"Measure": ["Rows used", "Positive class", "Pseudo R squared", "Log likelihood", "AIC", "Accuracy at 0.5"], "Value": [str(len(data)), positive, f"{result.prsquared:.4f}", f"{result.llf:.4f}", f"{result.aic:.4f}", f"{accuracy:.4f}"]})
    info = model_row(result, "logistic", "classification", target, features, X.columns, len(data), Positive=positive, Negative=negative)
    return info, coef, fit


def linear_model_row(df, target, predictors, coef, intercept=True):
    beta = coef["Coefficient"].to_numpy()
    rows = int(df[[target] + list(predictors)].apply(pd.to_numeric, errors="coerce").dropna().shape[0])
    return model_row({"beta": beta, "intercept": intercept}, "linear", "regression", target, predictors, predictors, rows)


def score_model(model, df):
    info = model.iloc[0]
    est, algorithm, task, target = info["Model"], info["Algorithm"], info["Task"], info["Target"]
    out = df.copy()
    if algorithm == "linear":
        X = df[info["Features"]].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float, na_value=np.nan)
        beta = np.asarray(est["beta"], dtype=float)
        out[f"{target}_predicted"] = X @ beta[1:] + beta[0] if est["intercept"] else X @ beta
        return out
    if algorithm == "kmeans":
        X = design_matrix(df, info["Features"], info["Columns"])
        ok = X.notna().all(axis=1).to_numpy()
        labels = np.full(len(df), np.nan)
        if ok.any():
            labels[ok] = est["kmeans"].predict(est["scaler"].transform(X[ok]) if est["scaler"] is not None else X[ok]) + 1
        out["Cluster"] = pd.array(labels, dtype="Float64").astype("Int64")
        return out
    if algorithm == "pca":
        X = design_matrix(df, info["Features"], info["Columns"])
        ok = X.notna().all(axis=1).to_numpy()
        scores = np.full((len(df), est["pca"].n_components_), np.nan)
        if ok.any():
            scores[ok] = est["pca"].transform(est["scaler"].transform(X[ok]) if est["scaler"] is not None else X[ok])
        for i in range(scores.shape[1]):
            out[f"PC{i + 1}"] = scores[:, i]
        return out
    drop_first = algorithm in ("logistic", "glm")
    X = design_matrix(df, info["Features"], info["Columns"], drop_first=drop_first)
    ok = X.notna().all(axis=1).to_numpy()
    if algorithm == "glm":
        import statsmodels.api as sm

        pred = np.full(len(df), np.nan)
        if ok.any():
            pred[ok] = np.asarray(est.predict(sm.add_constant(X[ok], has_constant="add")), dtype=float)
        out[f"{target}_predicted"] = pred
        return out
    if algorithm == "logistic":
        import statsmodels.api as sm

        p = np.full(len(df), np.nan)
        if ok.any():
            p[ok] = est.predict(sm.add_constant(X[ok], has_constant="add"))
        out[f"P_{info['Positive']}"] = p
        out[f"{target}_predicted"] = pd.Series(np.where(p >= 0.5, info["Positive"], info["Negative"]), index=df.index).where(ok)
        return out
    predicted = pd.Series(np.nan, index=df.index, dtype=object if task == "classification" else float)
    if ok.any():
        predicted[ok] = est.predict(X[ok])
    out[f"{target}_predicted"] = predicted
    if task == "classification" and ok.any():
        proba = est.predict_proba(X[ok])
        for i, cls in enumerate(est.classes_):
            col = np.full(len(df), np.nan)
            col[ok] = proba[:, i]
            out[f"P_{cls}"] = col
    return out


def compare_models(models, df):
    from sklearn import metrics

    rows, confusion = [], []
    for model in models:
        info = model.iloc[0]
        target, task = info["Target"], info["Task"]
        name = f"{info['Algorithm']} ({target})"
        scored = score_model(model, df)
        pred_col = f"{target}_predicted"
        if task not in ("regression", "classification"):
            raise ValueError(f"{name} is not a prediction model")
        valid = scored[pred_col].notna() & scored[target].notna()
        actual, predicted = scored.loc[valid, target], scored.loc[valid, pred_col]
        row = {"Model": name, "Rows": int(valid.sum())}
        if task == "regression":
            a, p = pd.to_numeric(actual).astype(float), pd.to_numeric(predicted).astype(float)
            row.update({"R squared": metrics.r2_score(a, p), "RMSE": metrics.root_mean_squared_error(a, p), "MAE": metrics.mean_absolute_error(a, p)})
        else:
            a, p = actual.astype(str), predicted.astype(str)
            classes = sorted(set(a) | set(p))
            positive = info.get("Positive") if isinstance(info.get("Positive"), str) else classes[-1]
            average = "binary" if len(classes) == 2 else "macro"
            kw = {"pos_label": positive} if average == "binary" else {}
            row.update({
                "Accuracy": metrics.accuracy_score(a, p),
                "Precision": metrics.precision_score(a, p, average=average, zero_division=0, **kw),
                "Recall": metrics.recall_score(a, p, average=average, zero_division=0, **kw),
                "F1": metrics.f1_score(a, p, average=average, zero_division=0, **kw),
            })
            prob_col = f"P_{positive}"
            if average == "binary" and prob_col in scored and a.nunique() == 2:
                row["AUC"] = metrics.roc_auc_score((a == positive).astype(int), scored.loc[valid, prob_col].astype(float))
            counts = pd.crosstab(a.rename("Actual"), p.rename("Predicted")).stack().rename("Count").reset_index()
            confusion.append(counts.assign(Model=name)[["Model", "Actual", "Predicted", "Count"]])
        rows.append(row)
    matrix = pd.concat(confusion, ignore_index=True) if confusion else pd.DataFrame(columns=["Model", "Actual", "Predicted", "Count"])
    return pd.DataFrame(rows), matrix


def split_samples(df, estimation=60, validation=20, seed=1):
    if estimation < 0 or validation < 0 or estimation + validation > 100:
        raise ValueError("Percentages must be between 0 and 100 and add up to 100 or less")
    order = np.random.default_rng(seed).permutation(len(df))
    a = int(round(len(df) * estimation / 100))
    b = a + int(round(len(df) * validation / 100))
    parts = [np.sort(order[:a]), np.sort(order[a:b]), np.sort(order[b:])]
    return tuple(df.iloc[p].reset_index(drop=True) for p in parts)


def kmeans_cluster(df, features, k=3, standardize=True, seed=1):
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler

    X = design_matrix(df, features)
    complete = X.dropna()
    if len(complete) < k:
        raise ValueError(f"Need at least {k} complete rows for {k} clusters")
    scaler = StandardScaler().fit(complete) if standardize else None
    km = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(scaler.transform(complete) if scaler else complete)
    model = model_row({"kmeans": km, "scaler": scaler}, "kmeans", "cluster", None, features, X.columns, len(complete))
    scored = score_model(model, df)
    centers = km.cluster_centers_ if scaler is None else scaler.inverse_transform(km.cluster_centers_)
    sizes = pd.Series(km.labels_ + 1).value_counts()
    table = pd.DataFrame(centers, columns=X.columns)
    table.insert(0, "Rows", [int(sizes.get(i + 1, 0)) for i in range(k)])
    table.insert(0, "Cluster", range(1, k + 1))
    return scored, table, model


def principal_components(df, features, components=2, standardize=True):
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    X = design_matrix(df, features)
    complete = X.dropna()
    components = min(int(components), X.shape[1], len(complete))
    if components < 1:
        raise ValueError("Need at least one complete row and one feature")
    scaler = StandardScaler().fit(complete) if standardize else None
    pca = PCA(n_components=components).fit(scaler.transform(complete) if scaler else complete)
    model = model_row({"pca": pca, "scaler": scaler}, "pca", "dimension", None, features, X.columns, len(complete))
    scored = score_model(model, df)
    names = [f"PC{i + 1}" for i in range(components)]
    loadings = pd.DataFrame(pca.components_.T, columns=names)
    loadings.insert(0, "Feature", list(X.columns))
    variance = pd.DataFrame({"Component": names, "Explained variance %": 100 * pca.explained_variance_ratio_, "Cumulative %": 100 * np.cumsum(pca.explained_variance_ratio_)})
    return scored, loadings, variance, model


def fill_periods(df, date_col, freq="D", group_by=(), method="none"):
    group_by = list(group_by)
    work = df.assign(**{date_col: pd.to_datetime(df[date_col], errors="coerce").dt.to_period(freq)})
    if work[date_col].isna().any():
        raise ValueError(f"Some {date_col} values are not dates")
    parts = []
    groups = work.groupby(group_by, dropna=False, sort=False) if group_by else [((), work)]
    for key, g in groups:
        if g[date_col].duplicated().any():
            label = f" in group {key}" if group_by else ""
            raise ValueError(f"{date_col} has more than one row per period{label}. Use Group and Total first.")
        full = pd.period_range(g[date_col].min(), g[date_col].max(), freq=freq)
        out = g.set_index(date_col).reindex(full).rename_axis(date_col).reset_index()
        out["Filled"] = ~out[date_col].isin(g[date_col])
        for col, value in zip(group_by, key if isinstance(key, tuple) else (key,)):
            out[col] = value
        parts.append(out)
    result = pd.concat(parts, ignore_index=True)
    values = [c for c in result.columns if c not in group_by + [date_col, "Filled"]]
    if method == "previous":
        result[values] = result.groupby(group_by, sort=False)[values].ffill() if group_by else result[values].ffill()
    elif method == "zero":
        numeric = [c for c in values if pd.api.types.is_numeric_dtype(result[c])]
        result[numeric] = result[numeric].fillna(0)
    result[date_col] = result[date_col].dt.to_timestamp()
    return result[group_by + [date_col] + values + ["Filled"]] if group_by else result[[date_col] + values + ["Filled"]]


def series_groups(df, date_col, value_col, freq, group_by):
    group_by = list(group_by)
    work = df.assign(**{date_col: pd.to_datetime(df[date_col], errors="coerce").dt.to_period(freq)})
    groups = work.groupby(group_by, dropna=False, sort=False) if group_by else [((), work)]
    for key, g in groups:
        g = g.dropna(subset=[date_col])
        if g[date_col].duplicated().any():
            raise ValueError(f"{date_col} has more than one row per period{f' in group {key}' if group_by else ''}. Use Group and Total first.")
        y = pd.to_numeric(g.set_index(date_col)[value_col], errors="coerce").sort_index()
        y = y.reindex(pd.period_range(y.index.min(), y.index.max(), freq=freq))
        if y.isna().any():
            raise ValueError(f"{value_col} has gaps or nulls{f' in group {key}' if group_by else ''}. Use Fill Missing Dates first.")
        yield dict(zip(group_by, key if isinstance(key, tuple) else (key,))), y


def forecast_frames(keys, y, fitted, frame, date_col, value_col):
    history = pd.DataFrame({date_col: y.index.to_timestamp(), value_col: y.to_numpy(), "Fitted": np.asarray(fitted, dtype=float)})
    history["Residual"] = history[value_col] - history["Fitted"]
    future = pd.DataFrame({date_col: frame.index.to_timestamp(), "Forecast": frame.iloc[:, 0].to_numpy(), "Lower": frame.iloc[:, 1].to_numpy(), "Upper": frame.iloc[:, 2].to_numpy()})
    for k, v in reversed(list(keys.items())):
        history.insert(0, k, v)
        future.insert(0, k, v)
    return future, history


def ets_forecast(df, date_col, value_col, freq="M", periods=12, trend=None, seasonal=None, seasonal_periods=None, damped=False, confidence=95, group_by=()):
    import warnings

    from statsmodels.tsa.exponential_smoothing.ets import ETSModel

    futures, histories = [], []
    for keys, y in series_groups(df, date_col, value_col, freq, group_by):
        if seasonal and (not seasonal_periods or len(y) < 2 * seasonal_periods):
            raise ValueError(f"Seasonal ETS needs at least two full seasons ({2 * (seasonal_periods or 0)} periods); found {len(y)}")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = ETSModel(y.astype(float), error="add", trend=trend, seasonal=seasonal, seasonal_periods=seasonal_periods if seasonal else None, damped_trend=bool(damped and trend)).fit(disp=False)
            frame = res.get_prediction(start=len(y), end=len(y) + int(periods) - 1).summary_frame(alpha=1 - confidence / 100)[["mean", "pi_lower", "pi_upper"]]
        future, history = forecast_frames(keys, y, res.fittedvalues, frame, date_col, value_col)
        futures.append(future)
        histories.append(history)
    return pd.concat(futures, ignore_index=True), pd.concat(histories, ignore_index=True)


def arima_forecast(df, date_col, value_col, freq="M", periods=12, order="auto", seasonal_order=None, confidence=95, group_by=()):
    import itertools
    import warnings

    from statsmodels.tsa.arima.model import ARIMA

    futures, histories, summaries = [], [], []
    for keys, y in series_groups(df, date_col, value_col, freq, group_by):
        y = y.astype(float)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if order == "auto":
                best = None
                for p, d, q in itertools.product(range(3), range(2), range(3)):
                    try:
                        res = ARIMA(y, order=(p, d, q), seasonal_order=seasonal_order or (0, 0, 0, 0)).fit()
                    except Exception:
                        continue
                    if best is None or res.aic < best.aic:
                        best = res
                if best is None:
                    raise ValueError(f"No ARIMA model could be fit{f' for {keys}' if keys else ''}")
                res = best
            else:
                res = ARIMA(y, order=tuple(order), seasonal_order=seasonal_order or (0, 0, 0, 0)).fit()
            frame = res.get_forecast(int(periods)).summary_frame(alpha=1 - confidence / 100)[["mean", "mean_ci_lower", "mean_ci_upper"]]
        future, history = forecast_frames(keys, y, res.fittedvalues, frame, date_col, value_col)
        futures.append(future)
        histories.append(history)
        summary = pd.DataFrame({"Measure": ["Order (p, d, q)", "Seasonal order", "AIC", "BIC"] + [f"Coefficient: {n}" for n in res.params.index], "Value": [str(res.model.order), str(res.model.seasonal_order), f"{res.aic:.4f}", f"{res.bic:.4f}"] + [f"{v:.6g}" for v in res.params.to_numpy()]})
        for k, v in reversed(list(keys.items())):
            summary.insert(0, k, v)
        summaries.append(summary)
    return pd.concat(futures, ignore_index=True), pd.concat(histories, ignore_index=True), pd.concat(summaries, ignore_index=True)


def fit_estimator(df, target, features, algorithm, task="auto", seed=1, **params):
    from sklearn.inspection import permutation_importance
    from sklearn.naive_bayes import GaussianNB
    from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
    from sklearn.neural_network import MLPClassifier, MLPRegressor
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVC, SVR

    features = [f for f in features if f != target]
    data = df[[target] + features].dropna()
    if data.empty:
        raise ValueError("No rows have a value in the target and every predictor")
    task = guess_task(data[target]) if task == "auto" else task
    if algorithm == "naive_bayes" and task != "classification":
        raise ValueError("Naive Bayes only predicts categories. Pick a category target or set Type to classification.")
    X = design_matrix(data, features)
    y = data[target].astype(str) if task == "classification" else pd.to_numeric(data[target], errors="coerce")
    if task == "classification" and y.nunique() < 2:
        raise ValueError("The target needs at least two different values")
    hidden = tuple(int(h) for h in str(params.get("hidden") or "50").replace(" ", "").split(",") if h)
    builders = {
        ("naive_bayes", "classification"): lambda: GaussianNB(),
        ("knn", "classification"): lambda: KNeighborsClassifier(n_neighbors=int(params.get("k") or 5)),
        ("knn", "regression"): lambda: KNeighborsRegressor(n_neighbors=int(params.get("k") or 5)),
        ("svm", "classification"): lambda: SVC(C=float(params.get("c") or 1.0), kernel=params.get("kernel") or "rbf", probability=True, random_state=seed),
        ("svm", "regression"): lambda: SVR(C=float(params.get("c") or 1.0), kernel=params.get("kernel") or "rbf"),
        ("mlp", "classification"): lambda: MLPClassifier(hidden_layer_sizes=hidden, max_iter=2000, random_state=seed),
        ("mlp", "regression"): lambda: MLPRegressor(hidden_layer_sizes=hidden, max_iter=4000, random_state=seed),
    }
    est = builders[(algorithm, task)]()
    model = est if algorithm == "naive_bayes" else make_pipeline(StandardScaler(), est)
    model.fit(X, y)
    imp = permutation_importance(model, X, y, n_repeats=5, random_state=seed)
    importance = pd.DataFrame({"Feature": X.columns, "Importance": imp.importances_mean}).sort_values("Importance", ascending=False, ignore_index=True)
    score = model.score(X, y)
    fit = pd.DataFrame({"Measure": ["Rows used", "Type", "Training accuracy" if task == "classification" else "Training R squared"], "Value": [str(len(data)), task, f"{score:.4f}"]})
    return model_row(model, algorithm, task, target, features, X.columns, len(data)), importance, fit


def fit_regularized(df, target, features, method="ridge", alpha=None, l1_ratio=0.5, seed=1):
    from sklearn.linear_model import ElasticNet, ElasticNetCV, Lasso, LassoCV, Ridge, RidgeCV
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    features = [f for f in features if f != target]
    data = df[[target] + features].dropna()
    y = pd.to_numeric(data[target], errors="coerce")
    if y.isna().any():
        raise ValueError(f"{target} must be numeric")
    X = design_matrix(data, features)
    if alpha in (None, "", 0):
        est = {"ridge": RidgeCV(alphas=np.logspace(-3, 3, 61)), "lasso": LassoCV(cv=5, random_state=seed, max_iter=20000), "elasticnet": ElasticNetCV(l1_ratio=l1_ratio, cv=5, random_state=seed, max_iter=20000)}[method]
    else:
        est = {"ridge": Ridge(alpha=float(alpha)), "lasso": Lasso(alpha=float(alpha), max_iter=20000, random_state=seed), "elasticnet": ElasticNet(alpha=float(alpha), l1_ratio=l1_ratio, max_iter=20000, random_state=seed)}[method]
    model = make_pipeline(StandardScaler(), est).fit(X, y)
    scaler, reg = model[0], model[-1]
    raw = reg.coef_ / scaler.scale_
    intercept = reg.intercept_ - float((raw * scaler.mean_).sum())
    coef = pd.DataFrame({"Term": ["(Intercept)"] + list(X.columns), "Coefficient": [intercept] + list(raw), "Standardized": [np.nan] + list(reg.coef_), "Kept": [True] + [bool(abs(c) > 1e-12) for c in reg.coef_]})
    chosen = getattr(reg, "alpha_", alpha)
    fit = pd.DataFrame({"Measure": ["Rows used", "Method", "Alpha", "Training R squared", "Predictors kept"], "Value": [str(len(data)), method, f"{float(chosen):.6g}", f"{model.score(X, y):.4f}", f"{int(coef['Kept'].iloc[1:].sum())} of {len(raw)}"]})
    return model_row(model, method, "regression", target, features, X.columns, len(data)), coef, fit


def fit_glm(df, target, features, family="poisson"):
    import warnings

    import statsmodels.api as sm

    features = [f for f in features if f != target]
    data = df[[target] + features].dropna()
    y = pd.to_numeric(data[target], errors="coerce").astype(float)
    if family in ("poisson", "negbin") and (y < 0).any():
        raise ValueError(f"Count models need a target of 0 or more; {target} has negative values")
    if family == "gamma" and (y <= 0).any():
        raise ValueError(f"Gamma models need a target above 0; {target} has zeros or negatives")
    X = design_matrix(data, features, drop_first=True)
    Xc = sm.add_constant(X, has_constant="add")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if family == "negbin":
            res = sm.NegativeBinomial(y, Xc).fit(disp=0, maxiter=300)
        else:
            fam = sm.families.Poisson() if family == "poisson" else sm.families.Gamma(sm.families.links.Log())
            res = sm.GLM(y, Xc, family=fam).fit()
    params = res.params.drop("alpha", errors="ignore")
    coef = pd.DataFrame({
        "Term": ["(Intercept)" if t == "const" else t for t in params.index],
        "Coefficient": params.to_numpy(),
        "Ratio": np.exp(params.to_numpy()),
        "Std Error": res.bse[params.index].to_numpy(),
        "z": res.tvalues[params.index].to_numpy(),
        "p-value": res.pvalues[params.index].to_numpy(),
    })
    names = {"poisson": "Poisson", "negbin": "Negative binomial", "gamma": "Gamma (log link)"}
    measures = [("Rows used", str(len(data))), ("Family", names[family]), ("AIC", f"{res.aic:.4f}"), ("Log likelihood", f"{res.llf:.4f}")]
    if family == "negbin":
        measures.append(("Dispersion (alpha)", f"{float(res.params['alpha']):.4f}"))
    else:
        measures.append(("Deviance", f"{res.deviance:.4f}"))
    fit = pd.DataFrame(measures, columns=["Measure", "Value"])
    return model_row(res, "glm", "regression", target, features, X.columns, len(data), Family=family), coef, fit


def refit_model(model, df):
    from sklearn.base import clone

    info = model.iloc[0]
    algorithm, task, target, features = info["Algorithm"], info["Task"], info["Target"], list(info["Features"])
    if algorithm == "linear":
        data = df[[target] + features].apply(pd.to_numeric, errors="coerce").dropna()
        X = data[features].to_numpy(dtype=float)
        if info["Model"]["intercept"]:
            X = np.column_stack([np.ones(len(X)), X])
        beta, *_ = np.linalg.lstsq(X, data[target].to_numpy(dtype=float), rcond=None)
        return model_row({"beta": beta, "intercept": info["Model"]["intercept"]}, "linear", "regression", target, features, features, len(data))
    if algorithm == "logistic":
        return fit_logistic(df, target, features, positive=info["Positive"])[0]
    if algorithm == "glm":
        return fit_glm(df, target, features, family=info["Family"])[0]
    if task not in ("regression", "classification"):
        raise ValueError(f"Cross-validation works with prediction models, not {algorithm}")
    data = df[[target] + features].dropna()
    X = design_matrix(data, features, info["Columns"])
    y = data[target].astype(str) if task == "classification" else pd.to_numeric(data[target], errors="coerce")
    est = clone(info["Model"]).fit(X, y)
    return model_row(est, algorithm, task, target, features, info["Columns"], len(data))


def cross_validate(models, df, folds=5, seed=1):
    folds = int(folds)
    if folds < 2 or folds > len(df):
        raise ValueError(f"Use between 2 and {len(df)} folds")
    assignment = np.random.default_rng(seed).permutation(len(df)) % folds
    detail = []
    for model in models:
        for f in range(folds):
            train, test = df.iloc[assignment != f], df.iloc[assignment == f]
            try:
                refit = refit_model(model, train)
            except ValueError as e:
                raise ValueError(f"Fold {f + 1}: {e}") from None
            metrics, _ = compare_models([refit], test)
            detail.append({"Fold": f + 1, **metrics.iloc[0].to_dict()})
    detail = pd.DataFrame(detail)
    measures = [c for c in detail.columns if c not in ("Fold", "Model", "Rows")]
    grouped = detail.groupby("Model", sort=False)[measures]
    summary = grouped.mean().add_suffix(" (mean)").join(grouped.std().add_suffix(" (std)"))
    summary = summary[[c for m in measures for c in (f"{m} (mean)", f"{m} (std)")]].reset_index()
    summary.insert(1, "Folds", folds)
    return summary, detail[["Model", "Fold", "Rows"] + measures]


def vif_table(df, features):
    import statsmodels.api as sm
    from statsmodels.stats.outliers_influence import variance_inflation_factor

    X = design_matrix(df, features, drop_first=True).dropna()
    if X.shape[1] < 2:
        raise ValueError("Pick at least two predictors")
    Xc = sm.add_constant(X, has_constant="add")
    values = Xc.to_numpy()
    rows = []
    for i, col in enumerate(Xc.columns):
        if col == "const":
            continue
        with np.errstate(divide="ignore"):
            v = float(variance_inflation_factor(values, i))
        rows.append({"Predictor": col, "VIF": v, "Concern": "high" if v > 10 else "moderate" if v > 5 else "low"})
    return pd.DataFrame(rows).sort_values("VIF", ascending=False, ignore_index=True)


def test_of_means(df, value, group, equal_var=False):
    from scipy import stats

    data = df[[value, group]].dropna()
    data = data.assign(**{value: pd.to_numeric(data[value], errors="coerce")}).dropna()
    groups = [(name, g[value].astype(float)) for name, g in data.groupby(group, sort=True)]
    if len(groups) < 2:
        raise ValueError(f"{group} needs at least two groups with values")
    summary = pd.DataFrame({group: [n for n, _ in groups], "Rows": [len(v) for _, v in groups], "Mean": [v.mean() for _, v in groups], "Std": [v.std() for _, v in groups], "Std Error": [v.std() / np.sqrt(len(v)) for _, v in groups]})
    if len(groups) == 2:
        (na, a), (nb, b) = groups
        t = stats.ttest_ind(a, b, equal_var=equal_var)
        result = [("Test", "Student t-test" if equal_var else "Welch t-test"), ("Statistic (t)", f"{t.statistic:.6g}"), ("p-value", f"{t.pvalue:.6g}"), ("Degrees of freedom", f"{float(t.df):.4g}"), ("Difference in means", f"{a.mean() - b.mean():.6g} ({na} minus {nb})")]
    else:
        f = stats.f_oneway(*[v for _, v in groups])
        n, k = sum(len(v) for _, v in groups), len(groups)
        result = [("Test", "One-way ANOVA"), ("Statistic (F)", f"{f.statistic:.6g}"), ("p-value", f"{f.pvalue:.6g}"), ("Degrees of freedom", f"{k - 1}, {n - k}")]
    result.append(("Rows", str(len(data))))
    return summary, pd.DataFrame(result, columns=["Measure", "Value"])


def chi_square_test(df, row, col):
    from scipy import stats

    table = pd.crosstab(df[row], df[col])
    if min(table.shape) < 2:
        raise ValueError("Both columns need at least two different values")
    chi2, p, dof, expected = stats.chi2_contingency(table)
    n = float(table.to_numpy().sum())
    v = float(np.sqrt(chi2 / (n * (min(table.shape) - 1))))
    result = pd.DataFrame([("Chi-square", f"{chi2:.6g}"), ("Degrees of freedom", str(dof)), ("p-value", f"{p:.6g}"), ("Cramér's V", f"{v:.4f}"), ("Rows", str(int(n))), ("Smallest expected count", f"{expected.min():.3g}" + (" (below 5: treat the p-value with care)" if expected.min() < 5 else ""))], columns=["Measure", "Value"])
    exp = pd.DataFrame(expected, index=table.index, columns=table.columns)
    long = table.stack().rename("Observed").to_frame().join(exp.stack().rename("Expected")).reset_index()
    long.columns = [str(c) for c in long.columns]
    return result, long


def seasonal_decompose(df, date_col, value_col, freq="M", period=12, robust=False, group_by=()):
    from statsmodels.tsa.seasonal import STL

    parts = []
    for keys, y in series_groups(df, date_col, value_col, freq, group_by):
        if len(y) < 2 * int(period):
            raise ValueError(f"Need at least two full seasons ({2 * int(period)} periods); found {len(y)}")
        res = STL(y.astype(float), period=int(period), robust=bool(robust)).fit()
        out = pd.DataFrame({date_col: y.index.to_timestamp(), value_col: y.to_numpy(), "Trend": res.trend.to_numpy(), "Seasonal": res.seasonal.to_numpy(), "Remainder": res.resid.to_numpy()})
        for k, v in reversed(list(keys.items())):
            out.insert(0, k, v)
        parts.append(out)
    return pd.concat(parts, ignore_index=True)


def compare_forecast(forecast, actual, date_col, actual_date, actual_value, group_by=()):
    group_by = list(group_by)
    f = forecast.assign(_date=pd.to_datetime(forecast[date_col]).dt.normalize())
    a = actual.assign(_date=pd.to_datetime(actual[actual_date]).dt.normalize(), _actual=pd.to_numeric(actual[actual_value], errors="coerce"))[group_by + ["_date", "_actual"]]
    joined = f.merge(a, on=group_by + ["_date"], how="inner").dropna(subset=["_actual", "Forecast"])
    if joined.empty:
        raise ValueError("No forecast dates match dates in the actuals")
    joined["Actual"] = joined.pop("_actual")
    joined["Error"] = joined["Actual"] - joined["Forecast"]
    joined["Abs % error"] = (joined["Error"].abs() / joined["Actual"].abs()).where(joined["Actual"] != 0) * 100
    has_band = {"Lower", "Upper"} <= set(joined.columns)

    def summarize(g):
        row = {"Rows": len(g), "MAE": g["Error"].abs().mean(), "RMSE": float(np.sqrt((g["Error"] ** 2).mean())), "MAPE %": g["Abs % error"].mean(), "Bias": -g["Error"].mean()}
        if has_band:
            row["Inside interval %"] = 100 * ((g["Actual"] >= g["Lower"]) & (g["Actual"] <= g["Upper"])).mean()
        return pd.Series(row)

    if group_by:
        metrics = pd.DataFrame([{**dict(zip(group_by, k if isinstance(k, tuple) else (k,))), **summarize(g)} for k, g in joined.groupby(group_by, sort=False)])
    else:
        metrics = summarize(joined).to_frame().T
    return metrics, joined.drop(columns=["_date"])


def cluster_diagnostics(df, features, k_min=2, k_max=8, standardize=True, seed=1):
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    X = design_matrix(df, features).dropna()
    k_max = min(int(k_max), len(X) - 1)
    if k_max < int(k_min):
        raise ValueError("Not enough complete rows for that range of K")
    Xs = StandardScaler().fit_transform(X) if standardize else X.to_numpy()
    rows = []
    for k in range(int(k_min), k_max + 1):
        km = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(Xs)
        rows.append({"K": k, "Within-cluster SS": km.inertia_, "Silhouette": silhouette_score(Xs, km.labels_)})
    out = pd.DataFrame(rows)
    out["Best by silhouette"] = out["Silhouette"] == out["Silhouette"].max()
    return out


def hierarchical_cluster(df, features, k=3, linkage="ward", standardize=True):
    from sklearn.cluster import AgglomerativeClustering
    from sklearn.preprocessing import StandardScaler

    X = design_matrix(df, features)
    complete = X.dropna()
    if len(complete) < int(k):
        raise ValueError(f"Need at least {k} complete rows")
    Xs = StandardScaler().fit_transform(complete) if standardize else complete.to_numpy()
    labels = AgglomerativeClustering(n_clusters=int(k), linkage=linkage).fit_predict(Xs) + 1
    out = df.copy()
    out["Cluster"] = pd.Series(labels, index=complete.index).reindex(df.index).astype("Int64")
    summary = complete.assign(Cluster=labels).groupby("Cluster").mean()
    summary.insert(0, "Rows", pd.Series(labels).value_counts().sort_index().to_numpy())
    return out, summary.reset_index()


def nearest_neighbors(df, id_col, features, k=5, standardize=True):
    from sklearn.neighbors import NearestNeighbors
    from sklearn.preprocessing import StandardScaler

    X = design_matrix(df, features)
    complete = X.dropna()
    if len(complete) < 2:
        raise ValueError("Need at least two complete rows")
    Xs = StandardScaler().fit_transform(complete) if standardize else complete.to_numpy()
    k = min(int(k), len(complete) - 1)
    dist, idx = NearestNeighbors(n_neighbors=k + 1).fit(Xs).kneighbors(Xs)
    ids = df.loc[complete.index, id_col].to_numpy()
    rows = []
    for i in range(len(complete)):
        found = [(j, d) for j, d in zip(idx[i], dist[i]) if j != i][:k]
        rows += [{id_col: ids[i], "Rank": r + 1, "Neighbor": ids[j], "Distance": float(d)} for r, (j, d) in enumerate(found)]
    return pd.DataFrame(rows)


def is_true(series):
    return series.map(lambda v: v is True or str(v).strip().lower() in ("true", "1", "yes", "y", "t"))


def team_ratings(df, home, away, home_points, away_points, neutral=None, home_field=True, cap=None):
    cols = [home, away, home_points, away_points] + ([neutral] if neutral else [])
    games = df[cols].dropna(subset=[home, away, home_points, away_points]).copy()
    games[home], games[away] = games[home].astype(str), games[away].astype(str)
    if games.empty:
        raise ValueError("No completed games: every game needs both teams and both scores")
    teams = sorted(set(games[home]) | set(games[away]))
    index = {t: i for i, t in enumerate(teams)}
    n, m = len(games), len(teams)
    margin = (pd.to_numeric(games[home_points]) - pd.to_numeric(games[away_points])).astype(float).to_numpy()
    if cap:
        margin = np.clip(margin, -float(cap), float(cap))
    at_home = ~is_true(games[neutral]).to_numpy() if neutral else np.ones(n, dtype=bool)
    A = np.zeros((n + 1, m + (1 if home_field else 0)))
    A[np.arange(n), games[home].map(index).to_numpy()] = 1
    A[np.arange(n), games[away].map(index).to_numpy()] = -1
    if home_field:
        A[:n, m] = at_home
    A[n, :m] = 1
    solution, *_ = np.linalg.lstsq(A, np.append(margin, 0.0), rcond=None)
    rating = dict(zip(teams, solution[:m]))
    hfa = float(solution[m]) if home_field else 0.0
    long = pd.concat([
        pd.DataFrame({"Team": games[home], "Opponent": games[away], "Margin": margin}),
        pd.DataFrame({"Team": games[away], "Opponent": games[home], "Margin": -margin}),
    ])
    long["Opponent rating"] = long["Opponent"].map(rating)
    table = long.groupby("Team").agg(Games=("Margin", "size"), **{"Avg margin": ("Margin", "mean"), "Schedule strength": ("Opponent rating", "mean")}).reset_index()
    table["Rating"] = table["Team"].map(rating)
    table = table.sort_values("Rating", ascending=False, ignore_index=True)
    table.insert(0, "Rank", table["Rating"].rank(ascending=False, method="min").astype(int))
    table = table[["Rank", "Team", "Rating", "Games", "Avg margin", "Schedule strength"]]
    predicted = games[home].map(rating).to_numpy() - games[away].map(rating).to_numpy() + hfa * at_home
    detail = df.loc[games.index].copy()
    detail["Margin used"] = margin
    detail["Predicted margin"] = predicted
    detail["Residual"] = margin - predicted
    fit = pd.DataFrame([("Teams", str(m)), ("Games", str(n)), ("Home-field advantage", f"{hfa:.3f}" if home_field else "not estimated"), ("Margin cap", str(cap) if cap else "none"), ("RMSE", f"{float(np.sqrt(np.mean((margin - predicted) ** 2))):.3f}")], columns=["Measure", "Value"])
    return table, detail.reset_index(drop=True), fit


def elo_ratings(df, home, away, home_points, away_points, order=None, neutral=None, k=20.0, home_advantage=55.0, start=1500.0, margin_of_victory=True, season=None, carryover=0.75):
    import math

    cols = [c for c in [home, away, home_points, away_points, order, neutral, season] if c]
    games = df[list(dict.fromkeys(cols))].dropna(subset=[home, away, home_points, away_points])
    if order:
        games = games.sort_values(order, kind="stable")
    ratings, seasons, played, log = {}, {}, {}, []
    for idx, row in games.iterrows():
        h, a = str(row[home]), str(row[away])
        hp, ap = float(row[home_points]), float(row[away_points])
        if season:
            for team in (h, a):
                if team in seasons and seasons[team] != row[season]:
                    ratings[team] = start + carryover * (ratings[team] - start)
                seasons[team] = row[season]
        rh, ra = ratings.get(h, start), ratings.get(a, start)
        neutral_site = bool(neutral) and (row[neutral] is True or str(row[neutral]).strip().lower() in ("true", "1", "yes", "y", "t"))
        adv = 0.0 if neutral_site else float(home_advantage)
        expected = 1.0 / (1.0 + 10 ** (-(rh + adv - ra) / 400.0))
        result = 1.0 if hp > ap else 0.0 if hp < ap else 0.5
        multiplier = 1.0
        if margin_of_victory and hp != ap:
            winner_edge = (rh + adv - ra) if hp > ap else (ra - rh - adv)
            multiplier = math.log(abs(hp - ap) + 1) * (2.2 / (winner_edge * 0.001 + 2.2))
        delta = float(k) * multiplier * (result - expected)
        ratings[h], ratings[a] = rh + delta, ra - delta
        played[h], played[a] = played.get(h, 0) + 1, played.get(a, 0) + 1
        log.append({"_row": idx, "Home Elo before": rh, "Away Elo before": ra, "Home win probability": expected, "Home Elo after": ratings[h], "Away Elo after": ratings[a]})
    if not log:
        raise ValueError("No completed games: every game needs both teams and both scores")
    table = pd.DataFrame({"Team": list(ratings), "Elo": list(ratings.values()), "Games": [played[t] for t in ratings]}).sort_values("Elo", ascending=False, ignore_index=True)
    table.insert(0, "Rank", table["Elo"].rank(ascending=False, method="min").astype(int))
    extra = pd.DataFrame(log).set_index("_row")
    detail = df.loc[extra.index].join(extra).reset_index(drop=True)
    return table, detail
