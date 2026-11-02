import numpy as np
import pandas as pd


def inference_summary(df, columns=None, confidence=95, mu=0.0, alternative="two-sided", group_by=None, max_levels=20, categories=True):
    from scipy import stats
    from statsmodels.stats.proportion import proportion_confint

    level = float(confidence) / 100
    alpha = 1 - level
    keys = list(group_by or [])
    chosen = [c for c in (columns or list(df.columns)) if c not in keys]
    numeric = [c for c in chosen if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])]
    labeled = [c for c in chosen if c not in numeric and not pd.api.types.is_datetime64_any_dtype(df[c])]
    if keys:
        parts = [(key if isinstance(key, tuple) else (key,), part) for key, part in df.groupby(keys, dropna=False, sort=True)]
    else:
        parts = [((), df)]
    nan = float("nan")
    rows, shares = [], []
    for key, part in parts:
        label = dict(zip(keys, key))
        for col in numeric:
            x = pd.to_numeric(part[col], errors="coerce").dropna().to_numpy(dtype=float)
            n = len(x)
            row = {**label, "column": col, "n": n, "missing": int(len(part) - n)}
            stat = dict.fromkeys(["mean", "sd", "std_error", "mean_ci_low", "mean_ci_high", "sd_ci_low", "sd_ci_high", "median", "min", "max", "skewness", "excess_kurtosis", "test_value", "t", "df", "p_value", "cohens_d", "normality_test", "normality_p"], nan)
            stat["normality_test"] = ""
            if n >= 1:
                stat.update(mean=float(x.mean()), median=float(np.median(x)), min=float(x.min()), max=float(x.max()), test_value=float(mu))
            if n >= 2:
                mean, sd = float(x.mean()), float(x.std(ddof=1))
                se = sd / np.sqrt(n)
                crit = stats.t.ppf(1 - alpha / 2, n - 1)
                stat.update(sd=sd, std_error=float(se), mean_ci_low=float(mean - crit * se), mean_ci_high=float(mean + crit * se), df=float(n - 1))
                if sd > 0:
                    stat.update(
                        sd_ci_low=float(np.sqrt((n - 1) * sd**2 / stats.chi2.ppf(1 - alpha / 2, n - 1))),
                        sd_ci_high=float(np.sqrt((n - 1) * sd**2 / stats.chi2.ppf(alpha / 2, n - 1))),
                        t=float((mean - mu) / se),
                        p_value=float(stats.ttest_1samp(x, mu, alternative=alternative).pvalue),
                        cohens_d=float((mean - mu) / sd),
                    )
                else:
                    stat.update(sd_ci_low=0.0, sd_ci_high=0.0)
            if n >= 3 and x.std() > 0:
                stat["skewness"] = float(stats.skew(x, bias=False))
                if n <= 5000:
                    result = stats.shapiro(x)
                    stat.update(normality_test="Shapiro-Wilk", normality_p=float(result.pvalue))
                elif n >= 8:
                    stat.update(normality_test="D'Agostino", normality_p=float(stats.normaltest(x).pvalue))
            if n >= 4 and x.std() > 0:
                stat["excess_kurtosis"] = float(stats.kurtosis(x, bias=False))
            rows.append({**row, **stat})
        if not categories:
            continue
        for col in labeled:
            counts = part[col].dropna().astype(str).value_counts()
            total = int(counts.sum())
            if total == 0 or df[col].nunique(dropna=True) > max_levels:
                continue
            equal = float(stats.chisquare(counts.to_numpy()).pvalue) if len(counts) > 1 else nan
            lows, highs = proportion_confint(counts.to_numpy(), total, alpha=alpha, method="wilson")
            for (value, count), lo, hi in zip(counts.items(), lows, highs):
                shares.append({**label, "column": col, "level": value, "count": int(count), "n": total, "share": count / total, "ci_low": float(lo), "ci_high": float(hi), "p_equal_shares": equal})
    numeric_cols = keys + ["column", "n", "missing", "mean", "sd", "std_error", "mean_ci_low", "mean_ci_high", "sd_ci_low", "sd_ci_high", "median", "min", "max", "skewness", "excess_kurtosis", "test_value", "t", "df", "p_value", "cohens_d", "normality_test", "normality_p"]
    share_cols = keys + ["column", "level", "count", "n", "share", "ci_low", "ci_high", "p_equal_shares"]
    return pd.DataFrame(rows, columns=numeric_cols), pd.DataFrame(shares, columns=share_cols)
