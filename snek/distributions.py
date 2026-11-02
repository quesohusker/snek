import json

import numpy as np
import pandas as pd

FAMILIES = {
    "normal": ("Normal", ["mean", "sd"], "continuous"),
    "lognormal": ("Lognormal", ["mean of the log", "sd of the log"], "continuous"),
    "exponential": ("Exponential", ["mean"], "continuous"),
    "gamma": ("Gamma", ["shape", "scale"], "continuous"),
    "weibull": ("Weibull", ["shape", "scale"], "continuous"),
    "uniform": ("Uniform", ["min", "max"], "continuous"),
    "triangular": ("Triangular", ["min", "mode", "max"], "continuous"),
    "logistic": ("Logistic", ["center", "scale"], "continuous"),
    "beta": ("Beta", ["a", "b"], "continuous"),
    "poisson": ("Poisson", ["mean"], "discrete"),
    "geometric": ("Geometric", ["chance of success"], "discrete"),
    "negative_binomial": ("Negative binomial", ["successes needed", "chance of success"], "discrete"),
}


def check_params(name, p):
    p = [float(v) for v in p]
    ok = {
        "normal": p[1] >= 0,
        "lognormal": p[1] >= 0,
        "exponential": p[0] > 0,
        "gamma": p[0] > 0 and p[1] > 0,
        "weibull": p[0] > 0 and p[1] > 0,
        "uniform": p[0] <= p[1],
        "triangular": p[0] <= p[1] <= p[2] and p[0] < p[2],
        "logistic": p[1] > 0,
        "beta": p[0] > 0 and p[1] > 0,
        "poisson": p[0] >= 0,
        "geometric": 0 < p[0] <= 1,
        "negative_binomial": p[0] > 0 and 0 < p[1] <= 1,
        "binomial": p[0] >= 0 and 0 <= p[1] <= 1,
        "integer_uniform": p[0] <= p[1],
        "constant": True,
    }
    if name not in ok:
        raise ValueError(f"Unknown distribution {name!r}")
    count = len(FAMILIES[name][1]) if name in FAMILIES else {"binomial": 2, "integer_uniform": 2, "constant": 1}[name]
    if not ok[name] or any(v != v for v in p[:count]):
        raise ValueError(f"The numbers for {name.replace('_', ' ')} are not valid: {', '.join(f'{v:g}' for v in p)}")
    return p


def parse_choices(text):
    names, weights = [], []
    for part in str(text or "").split(","):
        part = part.strip()
        if not part:
            continue
        label, _, weight = part.rpartition(":")
        if not label:
            label, weight = part, "1"
        try:
            value = float(weight)
        except ValueError:
            label, value = part, 1.0
        if value < 0:
            raise ValueError(f"A weight cannot be negative: {part}")
        names.append(label.strip())
        weights.append(value)
    if not names or sum(weights) <= 0:
        raise ValueError("Enter the choices like this: small:0.5, medium:0.3, large:0.2")
    return names, np.array(weights) / sum(weights)


def draw_values(rng, name, params, size):
    p = check_params(name, list(params) + [0.0] * (3 - len(params)))
    if name == "normal":
        return rng.normal(p[0], p[1], size)
    if name == "lognormal":
        return rng.lognormal(p[0], p[1], size)
    if name == "exponential":
        return rng.exponential(p[0], size)
    if name == "gamma":
        return rng.gamma(p[0], p[1], size)
    if name == "weibull":
        return p[1] * rng.weibull(p[0], size)
    if name == "uniform":
        return rng.uniform(p[0], p[1], size)
    if name == "triangular":
        return rng.triangular(p[0], p[1], p[2], size)
    if name == "logistic":
        return rng.logistic(p[0], p[1], size)
    if name == "beta":
        return rng.beta(p[0], p[1], size)
    if name == "poisson":
        return rng.poisson(p[0], size)
    if name == "geometric":
        return rng.geometric(p[0], size)
    if name == "negative_binomial":
        return rng.negative_binomial(p[0], p[1], size)
    if name == "binomial":
        return rng.binomial(int(p[0]), p[1], size)
    if name == "integer_uniform":
        return rng.integers(int(p[0]), int(p[1]) + 1, size)
    return np.full(size, p[0])


def random_data(rows, columns, seed=1, fit=None, fit_rank=1, fit_name="value"):
    rng = np.random.default_rng(int(seed))
    rows = int(rows)
    if rows < 0:
        raise ValueError("Rows must be 0 or more")
    out = {}
    if fit is not None:
        ranked = fit[fit["note"].fillna("") == ""].sort_values("rank")
        if fit_rank < 1 or fit_rank > len(ranked):
            raise ValueError(f"The fit table has {len(ranked)} usable fits. Rank {fit_rank} is not one of them.")
        row = ranked.iloc[int(fit_rank) - 1]
        out[fit_name or "value"] = draw_values(rng, row["distribution"], [row["p1"], row["p2"], row["p3"]], rows)
        return pd.DataFrame(out)
    for spec in columns:
        name = str(spec.get("name") or "").strip()
        if not name:
            raise ValueError("Every column needs a name")
        if name in out:
            raise ValueError(f"Two columns are named {name}")
        dist = spec.get("dist")
        if dist == "choice":
            labels, weights = parse_choices(spec.get("choices"))
            out[name] = rng.choice(np.array(labels, dtype=object), size=rows, p=weights)
        else:
            params = [spec.get(k) for k in ("p1", "p2", "p3")]
            params = [float("nan") if v in (None, "") else float(v) for v in params]
            out[name] = draw_values(rng, dist, params, rows)
    return pd.DataFrame(out)


def fit_candidates(x, kind):
    from scipy import stats

    n = len(x)
    mean = float(x.mean())
    var = float(x.var(ddof=1))
    spread = float(x.max() - x.min())
    pad = spread / (n - 1) if n > 1 else 0.0
    positive = bool((x > 0).all())
    unit = bool(((x >= 0) & (x <= 1)).all())
    out = []

    def add(name, params, frozen, k, note=""):
        out.append({"name": name, "params": list(params) + [float("nan")] * (3 - len(params)), "frozen": frozen, "k": k, "note": note})

    def skip(name, note):
        out.append({"name": name, "params": [float("nan")] * 3, "frozen": None, "k": 0, "note": note})

    if kind == "continuous":
        add("normal", [mean, float(x.std())], stats.norm(mean, max(float(x.std()), 1e-12)), 2)
        if positive:
            lx = np.log(x)
            mu, sigma = float(lx.mean()), float(lx.std())
            add("lognormal", [mu, sigma], stats.lognorm(s=max(sigma, 1e-12), scale=float(np.exp(mu))), 2)
        else:
            skip("lognormal", "needs values above 0")
        if (x >= 0).all() and mean > 0:
            add("exponential", [mean], stats.expon(scale=mean), 1)
        else:
            skip("exponential", "needs values of 0 or more")
        if positive:
            a, _, scale = stats.gamma.fit(x, floc=0)
            add("gamma", [a, scale], stats.gamma(a, scale=scale), 2)
            c, _, scale = stats.weibull_min.fit(x, floc=0)
            add("weibull", [c, scale], stats.weibull_min(c, scale=scale), 2)
        else:
            skip("gamma", "needs values above 0")
            skip("weibull", "needs values above 0")
        if spread > 0:
            lo, hi = float(x.min() - pad), float(x.max() + pad)
            add("uniform", [lo, hi], stats.uniform(lo, hi - lo), 2)
            mode = float(np.clip(3 * mean - lo - hi, lo + 1e-9 * spread, hi - 1e-9 * spread))
            add("triangular", [lo, mode, hi], stats.triang((mode - lo) / (hi - lo), loc=lo, scale=hi - lo), 3)
            loc, scale = stats.logistic.fit(x)
            add("logistic", [loc, scale], stats.logistic(loc, scale), 2)
        else:
            skip("uniform", "all values are the same")
            skip("triangular", "all values are the same")
            skip("logistic", "all values are the same")
        if unit and spread > 0:
            xb = np.clip(x, 1e-9, 1 - 1e-9)
            a, b, _, _ = stats.beta.fit(xb, floc=0, fscale=1)
            add("beta", [a, b], stats.beta(a, b), 2)
        else:
            skip("beta", "needs values from 0 to 1")
        return out
    add("poisson", [mean], stats.poisson(mean), 1) if mean > 0 else skip("poisson", "the mean is 0")
    if x.min() >= 1:
        add("geometric", [1 / mean], stats.geom(1 / mean), 1)
    else:
        skip("geometric", "needs values of 1 or more")
    if var > mean > 0:
        p = mean / var
        r = mean * p / (1 - p)
        add("negative_binomial", [r, p], stats.nbinom(r, p), 2)
    else:
        skip("negative_binomial", "needs a variance larger than the mean")
    return out


def ks_statistic(x, frozen, discrete):
    from scipy import stats

    if not discrete:
        result = stats.kstest(x, frozen.cdf)
        return float(result.statistic), float(result.pvalue)
    values, counts = np.unique(x, return_counts=True)
    ecdf = np.cumsum(counts) / len(x)
    below = np.concatenate([[0.0], ecdf[:-1]])
    d = max(np.abs(ecdf - frozen.cdf(values)).max(), np.abs(below - frozen.cdf(values - 1)).max())
    return float(d), float("nan")


def fit_distribution(df, column, kind="auto", top=3):
    x = pd.to_numeric(df[column], errors="coerce").dropna().to_numpy(dtype=float)
    n = len(x)
    if n < 8:
        raise ValueError(f"Need at least 8 values in {column} to fit a distribution. Found {n}.")
    whole = bool((np.mod(x, 1) == 0).all())
    if kind == "auto":
        kind = "discrete" if whole and len(np.unique(x)) <= max(20, n // 5) else "continuous"
    if kind == "discrete" and not whole:
        raise ValueError(f"{column} has values that are not whole numbers, so it cannot be fitted as counts")
    rows = []
    for c in fit_candidates(x, kind):
        row = {"distribution": c["name"], "label": FAMILIES[c["name"]][0], "kind": kind, "p1": c["params"][0], "p2": c["params"][1], "p3": c["params"][2], "n": n}
        names = FAMILIES[c["name"]][1]
        row["parameters"] = ", ".join(f"{label} {value:.6g}" for label, value in zip(names, c["params"])) if c["frozen"] is not None else ""
        if c["frozen"] is None:
            row.update(loglik=float("nan"), aic=float("nan"), bic=float("nan"), ks_stat=float("nan"), ks_p=float("nan"), note=c["note"])
        else:
            with np.errstate(all="ignore"):
                loglik = float((c["frozen"].logpmf(x) if kind == "discrete" else c["frozen"].logpdf(x)).sum())
            if not np.isfinite(loglik):
                row.update(loglik=float("nan"), aic=float("nan"), bic=float("nan"), ks_stat=float("nan"), ks_p=float("nan"), note="does not fit these values")
            else:
                ks, ks_p = ks_statistic(x, c["frozen"], kind == "discrete")
                row.update(loglik=loglik, aic=2 * c["k"] - 2 * loglik, bic=c["k"] * np.log(n) - 2 * loglik, ks_stat=ks, ks_p=ks_p, note="")
        rows.append(row)
    fits = pd.DataFrame(rows)
    usable = fits["note"] == ""
    fits["delta_aic"] = fits["aic"] - fits.loc[usable, "aic"].min()
    weights = np.exp(-fits["delta_aic"] / 2).where(usable)
    fits["akaike_weight"] = weights / weights.sum()
    fits = pd.concat([fits[usable].sort_values("aic"), fits[~usable]], ignore_index=True)
    fits.insert(0, "rank", np.where(fits["note"] == "", np.arange(len(fits)) + 1, np.nan))
    fits["rank"] = fits["rank"].astype("Int64")
    fits = fits[["rank", "distribution", "label", "kind", "parameters", "p1", "p2", "p3", "n", "loglik", "aic", "bic", "delta_aic", "akaike_weight", "ks_stat", "ks_p", "note"]]
    return fits, fit_chart(x, fits, column, kind, int(top))


def fit_chart(x, fits, column, kind, top=3):
    from scipy import stats

    best = fits[fits["note"] == ""].head(max(top, 1))
    discrete = kind == "discrete"
    layers = []
    if discrete:
        values, counts = np.unique(x, return_counts=True)
        grid = np.arange(int(x.min()), int(x.max()) + 1)
        layers.append({"data": {"values": [{"x": int(v), "share": float(c / len(x))} for v, c in zip(values, counts)]}, "mark": {"type": "bar", "opacity": 0.35, "tooltip": True}, "encoding": {"x": {"field": "x", "type": "ordinal", "title": column}, "y": {"field": "share", "type": "quantitative", "title": "Share of values"}}})
    else:
        bins = int(min(40, max(8, np.sqrt(len(x)))))
        density, edges = np.histogram(x, bins=bins, density=True)
        grid = np.linspace(x.min(), x.max(), 160)
        layers.append({"data": {"values": [{"lo": float(a), "hi": float(b), "density": float(d)} for a, b, d in zip(edges[:-1], edges[1:], density)]}, "mark": {"type": "bar", "opacity": 0.35, "tooltip": True}, "encoding": {"x": {"field": "lo", "type": "quantitative", "title": column}, "x2": {"field": "hi"}, "y": {"field": "density", "type": "quantitative", "title": "Density"}}})
    lines = []
    for _, row in best.iterrows():
        frozen = dict((c["name"], c["frozen"]) for c in fit_candidates(x, kind))[row["distribution"]]
        values = frozen.pmf(grid) if discrete else frozen.pdf(grid)
        label = f"{row['rank']}. {row['label']}"
        lines += [{"x": float(g) if not discrete else int(g), "y": float(v), "fit": label} for g, v in zip(grid, values) if np.isfinite(v)]
    if lines:
        layers.append({"data": {"values": lines}, "mark": {"type": "line", "point": discrete, "tooltip": True}, "encoding": {"x": {"field": "x", "type": "ordinal" if discrete else "quantitative"}, "y": {"field": "y", "type": "quantitative", "title": "Share of values" if discrete else "Density"}, "color": {"field": "fit", "type": "nominal", "title": "Fit"}}})
    spec = {"$schema": "https://vega.github.io/schema/vega-lite/v6.json", "title": f"{column}: data and best fits", "width": "container", "height": 280, "layer": layers}
    return pd.DataFrame([{"Kind": "fit", "Title": spec["title"], "Rows plotted": len(x), "Rows in data": len(x), "Vega-Lite": json.dumps(spec)}])
