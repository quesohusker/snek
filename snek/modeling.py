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
    drop_first = algorithm == "logistic"
    X = design_matrix(df, info["Features"], info["Columns"], drop_first=drop_first)
    ok = X.notna().all(axis=1).to_numpy()
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
            raise ValueError(f"{date_col} has more than one row per period{label}. Summarize first.")
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
            raise ValueError(f"{date_col} has more than one row per period{f' in group {key}' if group_by else ''}. Summarize first.")
        y = pd.to_numeric(g.set_index(date_col)[value_col], errors="coerce").sort_index()
        y = y.reindex(pd.period_range(y.index.min(), y.index.max(), freq=freq))
        if y.isna().any():
            raise ValueError(f"{value_col} has gaps or nulls{f' in group {key}' if group_by else ''}. Use TS Filler first.")
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
