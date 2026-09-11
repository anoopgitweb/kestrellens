# StatLens

A local, deterministic statistical analysis application. Python handles full datasets; a dependency-free HTML/CSS/JavaScript interface displays compact results. No AI, telemetry, CDN assets or external APIs.

## Run on this computer

Double-click **Start StatLens.cmd**, or open PowerShell in this folder and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

Open **http://127.0.0.1:8765**. Keep the server running while using the app; Ctrl+C stops it and clears all datasets from memory. This workspace includes a local SciPy dependency directory and uses the bundled Python runtime when available.

Try the included `sample-business-55000.csv`, an entirely synthetic 55,000-row business dataset. See `VALIDATION.md` for measured test results and verification limits.

## Portable installation

Python 3.11 or newer recommended. Install dependencies once, then run completely offline:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python backend/server.py
```

On macOS/Linux use `.venv/bin/python`. The workspace's `.runtime` folder takes import priority; when moving to another platform, omit that Windows-specific dependency folder and install requirements in the virtual environment. For a different port, pass `--port 8766`.

## Workflow

1. Upload UTF-8 CSV, TSV, or XLSX. The first Excel worksheet is used. Headers must be unique and populated.
2. Inspect automatic types, missing values, invalid conversions and duplicate rows. Change column types and rerun when needed.
3. Review the automatically selected modules and reasons for modules that do not apply.
4. Filter or search the dashboard; open a finding to see metrics, charts, methods and limitations.
5. Open Results summary for one table containing every completed analysis, its S.No, valid data points, key statistics, evidence and interpretation.
6. Export CSV results, complete JSON, print/save a readable report as PDF, or generate a PowerPoint deck. For PPT, select any completed findings; each selected result becomes an editable slide with a relevant native chart when chart data exists.
7. Open Learn for quick, plain-language explanations and examples for every current module. Uploaded results replace the general examples whenever that analysis is available.

## Statistical rules

| Input | Automatic output |
|---|---|
| Every column / dataset | Types, missing values, invalid values, cardinality, duplicates, completeness |
| Numeric | Mean, median, sample SD, percentiles, histogram, skewness, IQR outliers, sample variance, coefficient of variation |
| Numeric + numeric | Pearson / Spearman association; exploratory one-predictor OLS with slope interval |
| Category + numeric | Group means / medians; two-sided Welch test for two eligible groups, Kruskal–Wallis for more |
| Category + category | Chi-square independence and Cramér’s V; no significance decision when any expected cell is below five |
| Date + numeric | Daily or monthly mean trend; variability of successive observed-period changes; month-of-year seasonality when 24+ months exist |
| Two eligible groups + numeric | Cohen’s d effect size and Mann–Whitney U rank test |
| Two or more varying numeric columns | PCA loadings / explained variance and deterministic exploratory k-means clusters |
| Three or more varying numeric columns | Exploratory multiple regression |
| Two-level category + numeric | Logistic regression, Bayesian proportion summary and sample-size planning when an observable effect exists |
| Event/status category + duration | Kaplan–Meier survival summary |

All eligible analyses run automatically. The recommendation screen reports completed and inapplicable modules; it does not require manual test selection. The original ten modules remain, with five additional modules for effect sizes, nonparametric tests, seasonality, PCA and clustering.

Inference uses Benjamini–Hochberg adjustment across eligible Pearson, group, chi-square and Mann–Whitney tests (q < 0.05). Regression is descriptive and does not add the equivalent Pearson hypothesis again. Spearman, PCA, clustering and effect sizes are descriptive. Confidence intervals are classical, unadjusted 95% intervals, not simultaneous intervals. Tests are exploratory; this app cannot determine whether sampling or independence assumptions hold. Statistical evidence does not establish practical importance or causation.

## Limits and data handling

- 100 MB uploaded file limit and 300 columns. 50,000+ rows are supported; capacity depends on row width and available RAM. Data is loaded in memory, not streamed from disk.
- Profiling covers every row and column. Deep analysis uses the first 12 numeric, first five eligible categorical (2–20 labels), and first two date columns in file order. This controls combinatorial cost; excluded columns remain in the profile. Adjust types to exclude unneeded columns.
- Pair analyses need eight complete observations and varying inputs. Group tests need at least five observations per included group. Trends need at least four observed aggregated periods.
- Numeric/date parsing needs 95% success among populated values; unsuccessful conversions are reported. Blank strings and Pandas' standard CSV NA tokens become missing. Date parsing uses month-first interpretation for ambiguous dates; prefer ISO dates.
- Likely identifiers and high-cardinality text are excluded from numerical inference. Detection is heuristic; inspect codes, dates and business measures before acting.
- No automatic imputation, duplicate deletion or outlier removal. Each analysis uses available rows for its own variables.
- Full-data calculations; browser receives only summaries, 20 preview rows and at most 250 sampled points per scatter plot. Histograms and time charts use aggregates.
- One analysis at a time and up to three dataset sessions. Older sessions are evicted as new uploads arrive; inactive sessions older than an hour are removed on the next upload. Stop the server to clear all data immediately. There is no persistence or resume after restart.
- The server binds only to 127.0.0.1 and validates Host/Origin. It is for a trusted single-user machine, not public deployment or hostile multi-user environments.
- CSV export guards spreadsheet formula prefixes. JSON includes the 20-row preview; review exports before sharing.
- No forecasting, multivariable regression, automatic causal interpretation, post-hoc pairwise group tests or dedicated XLSX export in this initial version. PCA and clustering are exploratory summaries, not predictive models.
- PowerPoint generation supports up to 80 selected findings per deck. It creates a cover slide plus one slide per finding, preserving the result explanation, key metrics, evidence and caveats. Bar, line and scatter chart data are mapped to editable native PowerPoint charts when the chart type is supported.

## Validate

```powershell
python -m unittest discover -s tests -v
node --check frontend/app.js
```

Tests verify a deterministic 55,000-row dataset, known correlation calculations, type corrections, missing/nonfinite values, sparse categorical tables, file parsing, and HTTP upload/poll/export/reanalysis with local-origin checks.

Code: `backend/engine.py` (rules and statistics), `backend/server.py` (local API), `frontend/` (UI), `tests/` (automated checks). Reference files under `sources/` are untouched.
