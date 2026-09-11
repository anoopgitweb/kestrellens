"""Deterministic statistical profiling and analysis. No AI or network services."""
from itertools import combinations
import math
import re
import warnings

import numpy as np
import pandas as pd
from scipy import stats

MODULES = {
    'quality': 'Data quality profiling', 'descriptive': 'Descriptive statistics',
    'distribution': 'Distribution analysis', 'correlation': 'Correlation',
    'groups': 'Group comparison', 'outliers': 'Outlier detection',
    'trend': 'Trend analysis', 'variance': 'Variance / volatility',
    'regression': 'Regression / relationships', 'significance': 'Significance testing',
    'effect_size': 'Effect sizes & confidence intervals', 'nonparametric': 'Nonparametric tests',
    'seasonality': 'Seasonality', 'pca': 'Principal components', 'clustering': 'Pattern clustering',
    'multiple_regression': 'Multiple regression', 'logistic': 'Logistic regression',
    'forecasting': 'Forecasting', 'posthoc': 'ANOVA post-hoc comparisons',
    'bayesian': 'Bayesian proportions', 'survival': 'Survival analysis', 'power': 'Power & sample size',
    'anova': 'ANOVA', 'bootstrap_ci': 'Bootstrap confidence intervals', 'decomposition': 'Time-series decomposition',
    'cohort': 'Cohort analysis', 'odds_ratio': 'Odds ratios & risk', 'missing_analysis': 'Missing-data analysis',
    'model_evaluation': 'Model evaluation', 'control_charts': 'Control charts',
}
MAX_NUMERIC = 12
MAX_CATEGORY = 5
MAX_DATES = 2


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [clean(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def fmt(value):
    return f'{value:,.4g}' if np.isfinite(value) else 'unavailable'


def profile(frame, overrides=None):
    df = frame.copy()
    columns = []
    overrides = overrides or {}
    for col in df:
        raw = df[col]
        if raw.dtype == object or pd.api.types.is_string_dtype(raw):
            raw = raw.replace(r'^\s*$', np.nan, regex=True)
            df[col] = raw
        nonnull = raw.dropna()
        n, unique = len(nonnull), nonnull.nunique()
        ratio = unique / max(n, 1)
        reason = ''
        kind = 'text'
        numeric = pd.to_numeric(raw, errors='coerce')
        date = None
        named_id = bool(re.search(r'(^id$|(^|[ _-])(id|key|uuid|zip|postcode)($|[ _-])|_id$)', str(col), re.I))
        if n == 0:
            kind, reason = 'empty', 'No usable values.'
        elif unique == 1:
            kind, reason = 'constant', 'Only one distinct value; cannot explain variation.'
        elif named_id:
            kind, reason = 'id', 'Column name suggests an identifier or code.'
        elif pd.api.types.is_bool_dtype(raw) or set(str(v).lower() for v in nonnull.unique()[:10]) <= {'true', 'false', 'yes', 'no', '0', '1'} and unique <= 2:
            kind, reason = 'boolean', 'Two-state values.'
        elif pd.api.types.is_datetime64_any_dtype(raw):
            kind, reason = 'date', 'Native date/time values.'
            date = pd.to_datetime(raw, errors='coerce', utc=True)
        elif numeric.notna().sum() / n >= .95:
            kind, reason = 'numeric', 'At least 95% of populated values parse as numbers.'
        else:
            # Avoid interpreting arbitrary numbers and short codes as timestamps.
            sample = nonnull.astype(str).head(1000)
            date_like = sample.str.contains(r'[-/:]|[A-Za-z]{3}', regex=True).mean() >= .8
            if date_like:
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore')
                    date = pd.to_datetime(raw, errors='coerce', format='mixed', utc=True)
                if date.notna().sum() / n >= .95:
                    kind, reason = 'date', 'At least 95% of populated values parse as dates (month-first for ambiguous dates).'
            if kind != 'date':
                if ratio > .98 and n >= 20:
                    kind, reason = 'id', 'Almost every value is unique; likely an identifier or free text.'
                elif unique <= 50 or (unique <= 200 and ratio < .05):
                    kind, reason = 'categorical', 'Repeated labels with limited distinct values.'
                else:
                    reason = 'High-cardinality text; retained for profiling only.'
        if col in overrides:
            kind = overrides[col]
            reason = 'Type selected by you.'
        invalid = 0
        if kind == 'numeric':
            numeric = numeric.replace([np.inf, -np.inf], np.nan)
            invalid = int((raw.notna() & numeric.isna()).sum())
            df[col] = numeric
        elif kind == 'date':
            if date is None:
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore')
                    date = pd.to_datetime(raw, errors='coerce', format='mixed', utc=True)
            invalid = int((raw.notna() & date.isna()).sum())
            df[col] = date
        columns.append(dict(name=col, type=kind, reason=reason, missing=int(raw.isna().sum()),
                            missing_percent=round(100 * raw.isna().mean(), 2), invalid=invalid,
                            unique=int(unique), examples=[str(v)[:100] for v in nonnull.unique()[:3]]))
    return df, columns


def analyze(frame, filename='dataset', overrides=None, progress=None):
    progress = progress or (lambda *args: None)
    progress(10, 'Detecting column types and checking data quality')
    df, columns = profile(frame, overrides)
    rows = len(df)
    eligible_num = [c['name'] for c in columns if c['type'] == 'numeric']
    nums = eligible_num[:MAX_NUMERIC]
    cats = [c['name'] for c in columns if c['type'] in ('categorical', 'boolean') and 2 <= c['unique'] <= 20][:MAX_CATEGORY]
    dates = [c['name'] for c in columns if c['type'] == 'date'][:MAX_DATES]
    results, tests = [], []
    def add(module, title, explanation, metrics, method, caveat='', chart=None, p=None, fields=None):
        item = dict(id=f'r{len(results)+1}', module=module, title=title, explanation=explanation,
                    metrics=metrics, method=method, caveat=caveat, chart=chart)
        if not fields:
            if module in ('quality','missing_analysis'):
                fields = list(df.columns)
            else:
                fields = [c for c in df.columns if str(c) in str(title)]
        if fields: item['fields'] = list(fields)
        if p is not None and np.isfinite(p):
            item['p_value'] = float(p)
            tests.append(item)
        results.append(item)
        return item
    missing = int(df.isna().sum().sum())
    duplicates = int(df.duplicated().sum())
    add('quality', 'Can this data be trusted?',
        f'The file contains {rows:,} rows and {len(columns):,} columns. {missing:,} cells are missing or unusable after type conversion. '
        f'{duplicates:,} rows repeat an earlier row exactly. Duplicates are reported, not removed: repeated transactions may be legitimate.',
        {'Rows': rows, 'Columns': len(columns), 'Missing / unusable cells': missing, 'Duplicate rows': duplicates,
         'Completeness %': 100 * (1 - missing / max(df.size, 1))},
        'Full-dataset profiling; blanks treated as missing; non-finite numeric values treated as unusable.',
        'Confirm column types below. Codes stored as numbers may need to be marked as identifiers. No missing values are imputed.')
    progress(25, 'Summarizing numeric columns and distributions')
    for col in nums:
        x = df[col].dropna().to_numpy(dtype=float)
        n = len(x)
        if not n:
            continue
        q1, median, q3 = np.percentile(x, [25, 50, 75])
        mean, sd = float(np.mean(x)), float(np.std(x, ddof=1)) if n > 1 else np.nan
        add('descriptive', col,
            f'The typical {col} is {fmt(median)} (median). Its average is {fmt(mean)}. The middle half of observations ranges from '
            f'{fmt(q1)} to {fmt(q3)}. Use the median when extreme values could distort the average.',
            {'Valid rows': n, 'Mean': mean, 'Median': median, 'Standard deviation': sd, 'Minimum': min(x), '25th percentile': q1,
             '75th percentile': q3, 'Maximum': max(x)}, 'Mean, sample standard deviation, and empirical percentiles; missing values excluded.')
        counts, edges = np.histogram(x, bins=min(24, max(1, int(np.sqrt(n)))))
        skew = float(stats.skew(x, bias=False)) if n >= 3 and sd > 0 else np.nan
        shape = 'roughly symmetric' if abs(skew) < .5 else ('right-skewed (a longer upper tail)' if skew > 0 else 'left-skewed (a longer lower tail)')
        if not np.isfinite(skew):
            shape = 'constant or too small to assess'
        add('distribution', col, f'{col} is {shape}. The histogram shows how frequently different values occur. '
            'A skewed distribution can make the average less representative of a typical observation.',
            {'Valid rows': n, 'Skewness': skew}, 'Full-data histogram and bias-corrected sample skewness.',
            'Histogram shape does not establish normality. Bin choices affect appearance.',
            {'type': 'bar', 'labels': [f'{fmt(edges[i])}–{fmt(edges[i+1])}' for i in range(len(counts))], 'values': counts.tolist()})
        iqr = q3 - q1
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        out = int(((x < lower) | (x > upper)).sum())
        add('outliers', col, f'{out:,} values ({out/max(n,1):.1%}) fall outside the usual middle-range fences for {col}. '
            'These are review candidates: check for input errors, unusual transactions, or meaningful exceptions before taking action.',
            {'Flagged values': out, 'Flagged %': 100*out/n, 'Lower fence': lower, 'Upper fence': upper, 'IQR': iqr},
            'Tukey fences: Q1 − 1.5 × IQR and Q3 + 1.5 × IQR.',
            'Flags are not proof of error. When IQR is zero, any value away from the central value is flagged; none are deleted.')
        cv = 100 * sd / abs(mean) if mean != 0 and np.isfinite(sd) else np.nan
        add('variance', col, f'{col} has a standard deviation of {fmt(sd)}, describing the spread around its average. '
            'Compare spread across similar business measures to assess consistency.',
            {'Valid rows': n, 'Sample variance': sd**2, 'Standard deviation': sd, 'Coefficient of variation %': cv},
            'Sample variance (n−1 denominator) and standard deviation / absolute mean.',
            'Coefficient of variation is meaningful only for ratio-scale values with a meaningful zero, and is unstable when the mean is near zero.')
    progress(45, 'Analyzing relationships and group differences')
    for a, b in combinations(nums, 2):
        pair = df[[a,b]].dropna()
        if len(pair) < 8 or pair[a].nunique() < 2 or pair[b].nunique() < 2:
            continue
        x, y = pair[a].to_numpy(float), pair[b].to_numpy(float)
        pearson = stats.pearsonr(x,y)
        spearman = stats.spearmanr(x,y)
        strength = 'strong' if abs(pearson.statistic) >= .7 else 'moderate' if abs(pearson.statistic) >= .3 else 'weak'
        add('correlation', f'{a} × {b}',
            f'There is a {strength} {"positive" if pearson.statistic >= 0 else "negative"} linear association between {a} and {b}. '
            f'Pearson r is {pearson.statistic:.3f}; Spearman rank correlation is {spearman.statistic:.3f}. '
            'This describes movement together, not cause and effect.',
            {'Paired rows': len(pair), 'Pearson r': pearson.statistic, 'Spearman rho': spearman.statistic},
            'Pearson correlation and two-sided test; Spearman shown as a descriptive robustness check.',
            'Inference assumes independent observations. Outliers and repeated measurements can distort the result.', p=pearson.pvalue)
        reg = stats.linregress(x,y)
        margin = stats.t.ppf(.975, len(x)-2) * reg.stderr
        sample = pair.sample(min(250, len(pair)), random_state=42)
        add('regression', f'{b} in relation to {a}',
            f'Within this dataset, a one-unit increase in {a} is associated with a {fmt(reg.slope)}-unit change in {b}. '
            f'This straight-line model accounts for {reg.rvalue**2:.1%} of observed variation in {b}. '
            'It is an exploratory description, not a validated forecast.',
            {'Paired rows': len(pair), 'Slope': reg.slope, 'Intercept': reg.intercept, 'R²': reg.rvalue**2,
             'Slope 95% CI lower': reg.slope-margin, 'Slope 95% CI upper': reg.slope+margin},
            'Exploratory ordinary least squares, one predictor. Column order sets predictor and response; no business target is inferred.',
            'Classical confidence intervals assume independent, constant-variance errors and an appropriate linear model. No holdout validation or causal adjustment.',
            {'type': 'scatter', 'xLabel': a, 'yLabel': b, 'points': sample.to_numpy().tolist()})
    for category in cats:
        for col in nums:
            grouped = [(str(k), g[col].dropna().to_numpy(float)) for k,g in df.groupby(category, observed=True)]
            grouped = [(k,v) for k,v in grouped if len(v) >= 5]
            if len(grouped) < 2:
                continue
            labels, values = zip(*grouped)
            means = [float(np.mean(v)) for v in values]
            hi, lo = int(np.argmax(means)), int(np.argmin(means))
            add('groups', f'{col} by {category}',
                f'{labels[hi]} has the highest average ({fmt(means[hi])}); {labels[lo]} has the lowest ({fmt(means[lo])}). '
                f'The gap is {fmt(means[hi]-means[lo])}. Compare group sizes and the significance result before prioritizing action.',
                {'Rows used': sum(map(len, values)), **{f'{label} · n / mean / median': f'{len(v):,} / {fmt(np.mean(v))} / {fmt(np.median(v))}' for label,v in grouped}},
                'Full-data group summaries; groups with fewer than five valid observations are excluded.',
                'Different group composition can explain apparent gaps.', {'type':'bar', 'labels': list(labels), 'values': means})
            if len(values) == 2:
                if all(np.var(v) == 0 for v in values):
                    continue
                test = stats.ttest_ind(*values, equal_var=False)
                method = 'Two-sided Welch t-test for a difference in group means (unequal variances allowed).'
                pooled = np.sqrt(((len(values[0])-1)*np.var(values[0],ddof=1)+(len(values[1])-1)*np.var(values[1],ddof=1))/(sum(map(len,values))-2))
                d = (np.mean(values[0])-np.mean(values[1]))/pooled if pooled else np.nan
                add('effect_size', f'{col} · {labels[0]} vs {labels[1]}',
                    f'The standardized mean difference is {fmt(d)} (Cohen’s d). This expresses the group gap in standard-deviation units so it can be compared across measures.',
                    {'Rows used': sum(map(len,values)), 'Cohen’s d': d, 'Mean difference': np.mean(values[0])-np.mean(values[1]), 'Group 1 mean': np.mean(values[0]), 'Group 2 mean': np.mean(values[1])},
                    'Cohen’s d using the pooled within-group sample standard deviation.',
                    'Effect size describes magnitude, not importance. It is sensitive to outliers and assumes a meaningful numeric scale.')
                nonparam = stats.mannwhitneyu(values[0], values[1], alternative='two-sided')
                add('nonparametric', f'{col} across {category} · rank test',
                    'This rank-based test asks whether one group tends to have higher values than the other without requiring normally distributed measurements.',
                    {'U statistic': nonparam.statistic, 'Groups used': 2, 'Rows used': sum(map(len,values))},
                    'Two-sided Mann–Whitney U test with exact calculation disabled for speed on large datasets.',
                    'The test evaluates rank distributions, not specifically means; ties and unequal shapes affect interpretation.', p=nonparam.pvalue)
            else:
                if len(np.unique(np.concatenate(values))) < 2:
                    continue
                test = stats.kruskal(*values)
                method = 'Kruskal–Wallis test for differences in rank distributions across groups.'
            add('significance', f'{col} across {category}',
                'This test checks whether the observed group differences are compatible with the null hypothesis. '
                'The adjusted evidence label below accounts for the many tests run in this upload. Business importance still depends on the size of the gap.',
                {'Test statistic': test.statistic, 'Groups used': len(values), 'Rows used': sum(map(len,values))}, method,
                'Requires independent observations and a representative sample. Kruskal–Wallis is not specifically a test of means; pairwise winners are not established.', p=test.pvalue)
    for a,b in combinations(cats,2):
        table = pd.crosstab(df[a], df[b])
        if min(table.shape) < 2:
            continue
        chi, p, dof, expected = stats.chi2_contingency(table, correction=False)
        sparse = bool((expected < 5).any())
        add('significance', f'{a} × {b}',
            f'Cramér’s V is {fmt(np.sqrt(chi/(table.to_numpy().sum()*(min(table.shape)-1))))}; values closer to zero indicate weaker association. '
            + ('Expected cell counts are too small for the chi-square approximation; no significance decision is made.' if sparse else 'The test evaluates whether the category patterns are independent.'),
            {'Chi-square': chi, 'Degrees of freedom': dof, 'Paired rows': int(table.to_numpy().sum()),
             'Cramér’s V': np.sqrt(chi/(table.to_numpy().sum()*(min(table.shape)-1))), 'Smallest expected count': float(expected.min())},
            'Pearson chi-square independence test and uncorrected Cramér’s V.',
            'Assumes independent observations; association does not imply causation.', p=None if sparse else p)
    progress(75, 'Checking time patterns and adjusting statistical evidence')
    for date in dates:
        for col in nums:
            pair = df[[date,col]].dropna().sort_values(date)
            if len(pair) < 8 or pair[date].nunique() < 4:
                continue
            daily = pair.set_index(date)[col].resample('D').mean().dropna()
            frequency = 'daily'
            if len(daily) > 180:
                daily = pair.set_index(date)[col].resample('MS').mean().dropna()
                frequency = 'monthly'
            if len(daily) < 4 or daily.nunique() < 2:
                continue
            days = (daily.index-daily.index[0]).total_seconds().to_numpy()/86400
            reg = stats.linregress(days, daily.to_numpy())
            add('trend', f'{col} over {date}',
                f'The {frequency} average of {col} changes by approximately {fmt(reg.slope)} units per calendar day along the fitted trend. '
                f'The first observed period averages {fmt(daily.iloc[0])}; the last averages {fmt(daily.iloc[-1])}.',
                {'Rows used': len(pair), 'Observed periods': len(daily), 'Slope per day': reg.slope, 'Trend R²': reg.rvalue**2},
                f'Linear fit to {frequency} means with equal weight per observed period; missing periods excluded.',
                'Descriptive trend only: seasonality, autocorrelation, incomplete periods and changing sample composition are not modeled. No forecast is made.',
                {'type':'line', 'labels':[v.strftime('%Y-%m-%d') for v in daily.index], 'values':daily.to_list()})
            changes = daily.diff().dropna()
            add('variance', f'{col} · time variation',
                f'The standard deviation of changes between successive observed {frequency} averages is {fmt(changes.std())} units. '
                'Larger values indicate less consistent period-to-period movement.',
                {'Changes measured': len(changes), 'Change standard deviation': changes.std(), 'Mean change': changes.mean()},
                f'Sample standard deviation of differences between successive observed {frequency} means.',
                'This is absolute change variability, not financial return volatility. Gaps in the time series may span multiple periods.')
            monthly = pair.set_index(date)[col].resample('MS').mean().dropna()
            if len(monthly) >= 24:
                by_month = monthly.groupby(monthly.index.month).mean()
                peak, trough = int(by_month.idxmax()), int(by_month.idxmin())
                add('seasonality', f'{col} · month-of-year pattern',
                    f'The strongest average month is {peak}; the weakest is {trough}. The peak-to-trough seasonal range is {fmt(by_month.max()-by_month.min())} units.',
                    {'Observed months': len(monthly), 'Seasonal range': by_month.max()-by_month.min(), 'Peak month': peak, 'Trough month': trough},
                    'Average of monthly means grouped by calendar month; at least 24 observed months required.',
                    'This is descriptive seasonality, not a forecast. Calendar effects, incomplete months and changing composition can create the pattern.',
                    {'type':'line','labels':[f'Month {i}' for i in by_month.index], 'values':by_month.to_list()})
    progress(86, 'Finding multivariate structure and customer-like patterns')
    if len(nums) >= 2 and len(df) >= 20:
        matrix = df[nums].dropna()
        if len(matrix) >= 20:
            x = matrix.to_numpy(float)
            std = x.std(axis=0, ddof=1)
            keep = std > 0
            x = (x[:,keep]-x[:,keep].mean(axis=0))/std[keep]
            used = [c for c,k in zip(nums,keep) if k]
            if x.shape[1] >= 2:
                _, singular, vt = np.linalg.svd(x, full_matrices=False)
                var = (singular**2)/(len(x)-1)
                explained = var/var.sum()
                add('pca', 'Principal component structure',
                    f'The first component explains {explained[0]:.1%} of standardized numeric variation; the first two explain {explained[:2].sum():.1%}. '
                    'This compresses correlated measures into a few interpretable dimensions.',
                    {'Rows used': len(x), 'Numeric measures': len(used), 'PC1 variance %': explained[0]*100, 'PC2 variance %': explained[1]*100,
                     'PC1 loadings': {c:vt[0,i] for i,c in enumerate(used)}, 'PC2 loadings': {c:vt[1,i] for i,c in enumerate(used)}},
                    'PCA on complete rows after standardizing each numeric measure to mean 0 and sample SD 1.',
                    'Components are mathematical combinations, not causal factors. Missing rows are excluded; signs can be reversed without changing the solution.', fields=used)
                # Deterministic k-means on a bounded sample keeps the local UI responsive.
                sample = x if len(x) <= 5000 else x[np.linspace(0,len(x)-1,5000).astype(int)]
                k = 3 if len(sample) >= 30 else 2
                centers = sample[np.linspace(0,len(sample)-1,k).astype(int)].copy()
                for _ in range(30):
                    dist = ((sample[:,None,:]-centers[None,:,:])**2).sum(axis=2)
                    labels = dist.argmin(axis=1)
                    new = np.array([sample[labels==i].mean(axis=0) if np.any(labels==i) else centers[i] for i in range(k)])
                    if np.allclose(new,centers): break
                    centers = new
                sizes = np.bincount(labels,minlength=k)
                add('clustering', 'Three pattern clusters',
                    'Observations are grouped by similarity across standardized numeric measures. Use the cluster sizes and centers to investigate distinct operating patterns or customer segments.',
                    {'Rows used': len(sample), 'Clusters': k, **{f'Cluster {i+1} rows': int(sizes[i]) for i in range(k)},
                     'Cluster centers': {f'Cluster {i+1}': {c:centers[i,j] for j,c in enumerate(used)} for i in range(k)}},
                    'Deterministic k-means with three centers (two when fewer than 30 rows), standardized numeric inputs, and at most 5,000 evenly spaced rows.',
                    'Clusters are exploratory and depend on variables, scaling and chosen k. They do not prove natural segments or explain why groups differ.', fields=used)
    # Additional study-design-aware methods. Each runs only when the column roles are clear enough.
    if len(nums) >= 3 and len(df) >= 30:
        target = nums[-1]; predictors = nums[:-1][:6]
        multi = df[predictors+[target]].dropna()
        if len(multi) >= max(30, len(predictors)*8):
            X = multi[predictors].to_numpy(float); y = multi[target].to_numpy(float)
            Xs = (X-X.mean(axis=0))/np.where(X.std(axis=0,ddof=1)==0,1,X.std(axis=0,ddof=1))
            design = np.column_stack([np.ones(len(Xs)),Xs]); beta=np.linalg.lstsq(design,y,rcond=None)[0]; pred=design@beta
            sst=((y-y.mean())**2).sum(); sse=((y-pred)**2).sum(); r2=1-sse/sst if sst else np.nan
            add('multiple_regression', f'{target} from {len(predictors)} numeric measures',
                f'An exploratory model estimates {target} from {", ".join(predictors)} together. The standardized coefficients show each measure’s association after accounting for the others; the model explains {r2:.1%} of observed variation.',
                {'Rows used':len(multi),'Predictors':len(predictors),'R²':r2,'Intercept':beta[0],**{f'Standardized coefficient · {c}':beta[i+1] for i,c in enumerate(predictors)}},
                'Ordinary least squares with standardized predictors and an intercept. Predictors are selected from the first eligible numeric columns; the last eligible numeric column is the outcome.',
                'This is exploratory, not causal or validated forecasting. Correlated predictors make coefficients unstable; assumptions about independent, constant-variance errors still apply.', fields=predictors+[target])
    binary_cat=[]
    for c in cats:
        vals=df[c].dropna().astype(str).unique()
        if len(vals)==2: binary_cat.append((c,vals))
    if binary_cat and nums:
        outcome, vals = binary_cat[0]; predictor=nums[0]
        pair=df[[outcome,predictor]].dropna(); y=(pair[outcome].astype(str)==vals[1]).astype(float).to_numpy(); x=pair[predictor].to_numpy(float)
        if len(pair)>=30 and y.min()<y.max() and x.std()>0:
            z=(x-x.mean())/(x.std(ddof=1) or 1); X=np.column_stack([np.ones(len(z)),z]); beta=np.zeros(2)
            for _ in range(120):
                prob=1/(1+np.exp(-np.clip(X@beta,-30,30))); beta += .08*(X.T@(y-prob))/len(y)
            prob=1/(1+np.exp(-np.clip(X@beta,-30,30))); ll=np.sum(y*np.log(np.maximum(prob,1e-12))+(1-y)*np.log(np.maximum(1-prob,1e-12))); null=np.sum(y*np.log(y.mean())+(1-y)*np.log(1-y.mean())); pseudo=1-ll/null if null else np.nan
            add('logistic', f'{outcome} predicted by {predictor}',
                f'The model estimates the probability of {vals[1]} from {predictor}. A positive standardized coefficient means higher {predictor} is associated with higher probability of that outcome.',
                {'Rows used':len(pair),'Positive outcome':vals[1],'Positive rate %':100*y.mean(),'Standardized coefficient':beta[1],'Odds ratio per SD':np.exp(beta[1]),'McFadden pseudo-R²':pseudo},
                'Two-parameter logistic model fit by deterministic gradient descent; predictor standardized. The first eligible two-level category is used as the outcome.',
                'Exploratory classification summary. It has no train/test validation, calibration curve or causal interpretation.', fields=[outcome,predictor])
    for date in dates:
        for col in nums[:3]:
            pair=df[[date,col]].dropna().sort_values(date)
            if len(pair)<20: continue
            series=pair.set_index(date)[col].resample('MS').mean().dropna()
            if len(series)<6: continue
            horizon=min(3,max(1,len(series)//6)); t=np.arange(len(series)); fit=stats.linregress(t,series.to_numpy()); future=np.arange(len(series),len(series)+horizon); forecast=fit.intercept+fit.slope*future
            add('forecasting', f'{col} · next {horizon} periods',
                f'An exploratory linear trend extends the observed {len(series)} monthly averages for {col} into the next {horizon} periods. The projected values are a planning reference, not a commitment.',
                {'Observed periods':len(series),'Forecast periods':horizon,'Slope per period':fit.slope,'Forecast values':{f'Period +{i+1}':v for i,v in enumerate(forecast)}},
                'Linear trend extrapolation over monthly means; no seasonality, autocorrelation or external drivers are modeled.',
                'Forecast uncertainty is not estimated. Do not use this as a production forecast without holdout validation and time-series diagnostics.', fields=[date,col])
            break
    for category in cats:
        for col in nums[:4]:
            grouped=[(str(k),g[col].dropna().to_numpy(float)) for k,g in df.groupby(category,observed=True)]; grouped=[(k,v) for k,v in grouped if len(v)>=5]
            if len(grouped)<3: continue
            for (a,va),(b,vb) in combinations(grouped,2):
                test=stats.ttest_ind(va,vb,equal_var=False)
                add('posthoc', f'{col} · {a} vs {b}', f'After seeing differences across {category}, this pairwise comparison estimates whether {a} and {b} differ in average {col}.',
                    {'Rows used':len(va)+len(vb),'Mean difference':np.mean(va)-np.mean(vb),'Group 1 mean':np.mean(va),'Group 2 mean':np.mean(vb)},
                    'Two-sided Welch comparison for one pair of groups; p-values are adjusted together with the other inferential tests.',
                    'Pairwise results are exploratory and can overstate evidence when many groups are compared.', p=test.pvalue, fields=[category,col])
            break
        if any(r['module']=='posthoc' for r in results): break
    if binary_cat and nums:
        outcome, vals=binary_cat[0]; successes=int((df[outcome].astype(str)==vals[1]).sum()); total=int(df[outcome].notna().sum()); prior_a=1; prior_b=1
        if total:
            post_mean=(successes+prior_a)/(total+prior_a+prior_b); lo,hi=stats.beta.ppf([.025,.975],successes+prior_a,total-successes+prior_b+1)
            add('bayesian', f'{outcome} · posterior proportion', f'Using a neutral Beta(1,1) prior, the estimated proportion of {vals[1]} updates to {post_mean:.1%} after observing {successes:,} successes in {total:,} valid rows.',
                {'Valid rows':total,'Successes':successes,'Posterior mean %':100*post_mean,'95% credible interval lower %':100*lo,'95% credible interval upper %':100*hi},
                'Conjugate Beta–Binomial update with a uniform Beta(1,1) prior.', 'The prior is a transparent default, not domain knowledge. Results depend on the outcome definition and independent-trial assumption.', fields=[outcome])
    event_candidates=[c for c in cats if re.search(r'(event|status|churn|death|fail|cancel)',str(c),re.I)]
    if event_candidates and nums:
        event=event_candidates[0]; duration=nums[0]; pair=df[[duration,event]].dropna(); ev=pair[event].astype(str).str.lower().isin(['1','true','yes','y','event','failed','cancelled','churned']).to_numpy(); dur=pair[duration].to_numpy(float); order=np.argsort(dur); at=len(dur); surv=1.; median=None
        for value in np.unique(dur[order]):
            d=ev[dur==value].sum(); surv*=1-d/max(at,1); at-=int((dur==value).sum());
            if median is None and surv<=.5: median=float(value)
        add('survival', f'{duration} until {event}', f'The observed event rate is {ev.mean():.1%}. The Kaplan–Meier estimate reaches 50% survival at approximately {fmt(median)} units when enough events are observed.',
            {'Rows used':len(pair),'Events':int(ev.sum()),'Event rate %':100*ev.mean(),'Estimated median time':median}, 'Kaplan–Meier product-limit survival estimate; event labels are inferred from common event/status values.', 'Censoring and event definitions should be reviewed. This summary assumes non-informative censoring and a meaningful duration scale.', fields=[event,duration])
    if binary_cat and nums:
        outcome, vals=binary_cat[0]; pair=df[[outcome,nums[0]]].dropna(); y=(pair[outcome].astype(str)==vals[1]).to_numpy(); n1=int(y.sum()); n0=len(y)-n1; p0=.5; effect=abs(n1/len(y)-p0)
        if effect>.01:
            required=int(math.ceil(2*((1.96*math.sqrt(2*.25)+.84*math.sqrt((n1/len(y))*(1-n1/len(y))+.25))/effect)**2))
            add('power', f'{outcome} · sample size planning', f'With the observed difference from a 50% baseline, a rough two-sided 80% power calculation suggests about {required:,} total observations for a future two-group proportion comparison.',
                {'Rows used':len(y),'Observed proportion %':100*n1/len(y),'Approx. required total n':required,'Observed absolute difference':effect}, 'Normal approximation for two-proportion planning, alpha 0.05 and 80% power.', 'Planning is illustrative and depends on the future design, baseline rate and practically meaningful effect. It does not replace a preregistered power analysis.', fields=[outcome,nums[0]])
    # Eight high-priority additions with conservative eligibility rules.
    if cats and nums:
        category=cats[0]; col=nums[0]; groups=[g[col].dropna().to_numpy(float) for _,g in df.groupby(category,observed=True) if len(g[col].dropna())>=5]
        if len(groups)>=3:
            test=stats.f_oneway(*groups); allv=np.concatenate(groups); grand=allv.mean(); between=sum(len(g)*(g.mean()-grand)**2 for g in groups); eta=between/max(((allv-grand)**2).sum(),1)
            add('anova', f'{col} across {category}', f'ANOVA compares the average {col} across {len(groups)} groups. The observed group variation accounts for {eta:.1%} of total variation before considering other factors.', {'Rows used':len(allv),'Groups':len(groups),'F statistic':test.statistic,'Eta squared':eta}, 'One-way ANOVA F-test with complete numeric values within groups.', 'Assumes independent observations, roughly normal residuals and similar variances. Use the post-hoc results to locate pairwise differences.', p=test.pvalue, fields=[category,col])
    if nums:
        col=nums[0]; x=df[col].dropna().to_numpy(float)
        if len(x)>=20:
            rng=np.random.default_rng(42); means=np.array([rng.choice(x,len(x),replace=True).mean() for _ in range(1000)]); lo,hi=np.percentile(means,[2.5,97.5])
            add('bootstrap_ci', f'{col} · bootstrap mean interval', f'Resampling the observed {col} values produces a 95% interval of {fmt(lo)} to {fmt(hi)} for the average. This shows sampling uncertainty without relying on a normal-theory formula.', {'Valid rows':len(x),'Mean':x.mean(),'Bootstrap 95% lower':lo,'Bootstrap 95% upper':hi}, '1,000 reproducible bootstrap resamples of the mean.', 'The interval reflects the uploaded sample and its dependence structure. It does not correct selection bias or dependence between rows.', fields=[col])
    for date in dates[:1]:
        for col in nums[:1]:
            s=df[[date,col]].dropna().set_index(date)[col].resample('MS').mean().dropna()
            if len(s)>=12:
                trend=np.polyfit(np.arange(len(s)),s.to_numpy(),1); seasonal=s.groupby(s.index.month).mean(); add('decomposition', f'{col} · trend and seasonal components', f'The monthly series separates into a linear trend plus repeating month-of-year effects. The trend changes by {fmt(trend[0])} units per month; seasonal amplitude is {fmt(seasonal.max()-seasonal.min())}.', {'Observed periods':len(s),'Trend per month':trend[0],'Seasonal amplitude':seasonal.max()-seasonal.min()}, 'Descriptive additive decomposition of monthly means into linear trend and calendar-month averages.', 'This is a descriptive decomposition. Irregular shocks and changing composition remain in the residual variation.', fields=[date,col])
            break
    if dates:
        d=df[dates[0]].dropna(); d=d.dt.tz_localize(None) if getattr(d.dt,'tz',None) is not None else d; months=d.dt.to_period('M').astype(str).value_counts().sort_index()
        if len(months)>=2: add('cohort', f'{dates[0]} · monthly cohorts', f'The dataset contains {len(months)} observed monthly cohorts. Cohort sizes range from {int(months.min()):,} to {int(months.max()):,} rows, which helps identify uneven coverage before retention analysis.', {'Cohorts':len(months),'Smallest cohort':int(months.min()),'Largest cohort':int(months.max()),'Median cohort size':int(months.median())}, 'Rows grouped by the month of the detected date column.', 'This is cohort sizing, not retention. A customer or case identifier and a repeated activity measure are needed for true cohort retention.', fields=[dates[0]])
    if len(binary_cat)>=2:
        a,av=binary_cat[0]; b,bv=binary_cat[1]; tab=pd.crosstab(df[a],df[b]).reindex(index=av,columns=bv,fill_value=0).to_numpy();
        if tab.shape==(2,2) and tab[0,1] and tab[1,0]:
            odds=(tab[1,1]*tab[0,0])/(tab[1,0]*tab[0,1]); risk1=tab[1,1]/max(tab[1].sum(),1); risk0=tab[0,1]/max(tab[0].sum(),1)
            add('odds_ratio', f'{b} by {a}', f'The odds of {bv[1]} are {fmt(odds)} times as high for {av[1]} compared with {av[0]}. The risk ratio is {fmt(risk1/max(risk0,1e-12))}.', {'Rows used':int(tab.sum()),'Odds ratio':odds,'Risk ratio':risk1/max(risk0,1e-12)}, '2×2 contingency-table odds ratio and risk ratio.', 'Association is not causation. Zero cells, confounding and outcome definition can make ratios unstable.', fields=[a,b])
    missing_counts=df.isna().sum(); missing_cols=missing_counts[missing_counts>0]
    if len(missing_cols): add('missing_analysis','Missing-data patterns', f'{len(missing_cols)} columns contain missing values. The most incomplete column is {missing_cols.idxmax()} with {int(missing_cols.max()):,} missing cells.', {'Rows':len(df),'Columns with missing values':len(missing_cols),'Rows with any missing value':int(df.isna().any(axis=1).sum()),'Most incomplete column':missing_cols.idxmax()}, 'Column-wise and row-wise missingness counts before any imputation.', 'Missingness may be systematic. The app does not impute values automatically or assume missing values are random.', fields=list(df.columns))
    if len(nums)>=2:
        pair=df[nums[:2]].dropna(); split=int(len(pair)*.8)
        if len(pair)>=30:
            x=pair.iloc[:split,0].to_numpy(); y=pair.iloc[:split,1].to_numpy(); xt=pair.iloc[split:,0].to_numpy(); yt=pair.iloc[split:,1].to_numpy(); slope,inter=np.polyfit(x,y,1); pred=slope*xt+inter; rmse=np.sqrt(np.mean((yt-pred)**2)); baseline=np.sqrt(np.mean((yt-yt.mean())**2)); r2=1-rmse**2/max(baseline**2,1e-12)
            add('model_evaluation', f'{nums[1]} holdout evaluation', f'A simple relationship model trained on the first 80% of complete rows explains {r2:.1%} of variation in the final 20% holdout by this R²-style comparison.', {'Training rows':split,'Holdout rows':len(pair)-split,'Holdout RMSE':rmse,'Holdout R²':r2}, 'Chronological-by-file-order 80/20 holdout for a one-predictor linear model.', 'File order may not represent time. This is a simple diagnostic, not a production model benchmark.', fields=nums[:2])
    # Control charts are generated for every numeric field. Identifier-like numbers remain visible,
    # but the caveat explicitly warns that a case number is not a process measure.
    for col in eligible_num:
        x=df[col].dropna().to_numpy(float)
        if len(x)>=20 and np.std(x)>0:
            mean=x.mean(); sd=x.std(ddof=1); upper=mean+3*sd; lower=mean-3*sd; flags=int(((x<lower)|(x>upper)).sum())
            id_warning=' This field looks identifier-like; use this chart only if the number represents an ordered process measure.' if any(c['name']==col and c['type']=='id' for c in columns) else ''
            add('control_charts', f'{col} · control limits', f'Using the observed average and three standard deviations, {flags:,} of {len(x):,} values fall outside the initial control limits. These points deserve process review.{id_warning}', {'Valid rows':len(x),'Center line':mean,'Lower control limit':lower,'Upper control limit':upper,'Out-of-control points':flags}, 'Shewhart-style limits at mean ± 3 sample standard deviations.', 'Limits are preliminary when observations are not ordered process measurements. They do not prove a special cause or guarantee process stability.'+id_warning, fields=[col])
    # Benjamini–Hochberg correction across unique inferential tests; regression reuses correlation evidence and is not retested.
    ordered = sorted(tests, key=lambda t: t['p_value'])
    bound = 1.
    for i in range(len(ordered)-1,-1,-1):
        bound = min(bound, ordered[i]['p_value']*len(ordered)/(i+1))
        ordered[i]['q_value'] = bound
        ordered[i]['evidence'] = 'Evidence after adjustment' if bound < .05 else 'Insufficient evidence after adjustment'
    recommendations = []
    reasons = {'descriptive':'Needs a usable numeric column.', 'distribution':'Needs a usable numeric column.',
        'outliers':'Needs a usable numeric column.', 'variance':'Needs a usable numeric column.',
        'correlation':'Needs two varying numeric columns and at least eight complete pairs.',
        'regression':'Needs two varying numeric columns and at least eight complete pairs.',
        'groups':'Needs a category with 2–20 labels and at least two groups with five valid numeric values each.',
        'significance':'Needs eligible groups or a categorical pair; constant groups may be skipped.',
        'effect_size':'Needs two eligible groups with varying numeric values.', 'nonparametric':'Needs two eligible groups with at least five values each.',
        'seasonality':'Needs at least 24 observed months after date aggregation.', 'pca':'Needs at least two varying numeric columns and 20 complete rows.',
        'clustering':'Needs at least two varying numeric columns and 20 complete rows.',
        'multiple_regression':'Needs at least three varying numeric columns and 30 complete rows.', 'logistic':'Needs a two-level category and a varying numeric predictor.',
        'forecasting':'Needs a date column with at least six observed monthly periods.', 'posthoc':'Needs at least three eligible groups for a numeric measure.',
        'bayesian':'Needs a two-level category to estimate a proportion.', 'survival':'Needs an event/status category and a duration measure.',
        'power':'Needs a two-level outcome and an observed difference from the planning baseline.',
        'anova':'Needs three or more eligible groups with at least five numeric observations each.', 'bootstrap_ci':'Needs at least 20 valid numeric observations.',
        'decomposition':'Needs a date and numeric column with at least 12 monthly periods.', 'cohort':'Needs at least two observed date cohorts.',
        'odds_ratio':'Needs two two-level categorical columns with nonzero 2×2 cells.', 'missing_analysis':'Runs when at least one column contains missing values.',
        'model_evaluation':'Needs two numeric columns and at least 30 complete rows.', 'control_charts':'Needs at least 20 varying numeric observations.',
        'trend':'Needs dates, numeric values, eight complete rows, and four varying observed periods.', 'quality':''}
    for module,label in MODULES.items():
        count = sum(r['module']==module for r in results)
        recommendations.append(dict(module=module, label=label, count=count, status='Completed' if count else 'Not applicable',
                                    reason=f'{count} relevant results selected automatically.' if count else reasons[module]))
    progress(95, 'Preparing business-friendly results')
    return clean(dict(filename=filename, rows=rows, column_count=len(columns), columns=columns, results=results,
        recommendations=recommendations, tests_run=len(tests), preview=frame.head(20).fillna('').astype(str).to_dict('records'),
        policy=dict(numeric_selected=nums, categories_selected=cats, dates_selected=dates,
            notes=[f'Analysis limits: first {MAX_NUMERIC} numeric, {MAX_CATEGORY} eligible categorical and {MAX_DATES} date columns in file order. All columns are profiled.',
                'Each analysis excludes only rows missing its required values. No automatic deletion, imputation or deduplication.',
                'Benjamini–Hochberg false discovery rate adjustment across all eligible Pearson, group and chi-square tests; threshold q < 0.05. Dependence among tests can affect error control.',
                'Statistical evidence is exploratory. Sampling design, independence, business meaning and causation cannot be inferred from an uploaded file.',
                'Full data is used for calculations. Scatter charts display at most 250 reproducibly sampled points. Dates use month-first parsing when ambiguous.'])))
