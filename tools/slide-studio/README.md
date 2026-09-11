# Slide Studio

A fully offline PPT Maker with Flask, HTML/CSS/JavaScript, JSON templates, and python-pptx. No AI, accounts, API keys, external fonts, CDN scripts, or runtime internet requests.

## Run on this computer

Double-click `start.bat`, keep the server window open, and visit http://127.0.0.1:5050. Dependencies are installed in `.packages` for the bundled Python runtime on this computer.

## Set up on another computer

Requires Python 3.10 or newer. Install dependencies once with `python -m pip install -r requirements.txt`, then run `python run.py`. Open http://127.0.0.1:5050. For installation without internet, prepare matching wheels on an internet-connected computer using `pip download -r requirements.txt -d wheels`, transfer them, then install with `pip install --no-index --find-links wheels -r requirements.txt`. The wheel files must match the destination Python version and operating system.

## Use

The starter deck contains all nine slide types with illustrative content. Select a slide in the left sidebar, edit its title, subtitle, and rows on the right, and select one of three themes. Use Add slide, Copy, the up/down arrows, and Delete to manage the deck. Content rows use `|` between fields; the editor shows the expected format.

Trend / Chart slides offer column, horizontal bar, line, area, stacked column, pie, donut, scatter, and column + line charts. Enter up to 12 rows and 4 series as `Category | Value 1 | Value 2`; series names use `Revenue | Target` in their separate field. Pie/donut require one nonnegative series with a positive total. Scatter uses numeric X values in the first column. Combination charts require exactly two series sharing the same value axis. No header row is needed.

Upload one PNG, JPEG, or WebP per slide (up to 5 MB and 20 megapixels). Choose left/right placement and small/medium/large image space. Pictures retain their proportions, and content shares the remaining width. Large images reduce text size, so inspect the preview. Images embed in saved JSON projects and PowerPoint files. Projects may be up to 40 MB. If browser autosave fills up, a visible message tells you to use Save project.

Generate PPT downloads a widescreen `.pptx`. Charts are native editable PowerPoint charts with embedded workbooks, and images are native picture objects. Preview and export share chart data and placement, but PowerPoint controls its own chart typography and spacing, so chart appearance can differ. Long content produces an actionable validation error instead of being silently clipped. Supported size is 1–60 slides, up to 12 chart rows, 8 rows for summaries/action plans and 6 for other structured layouts.

Changes autosave in this browser. Save project downloads portable JSON; Open project restores it. Browser storage is not a backup, so save important work as a project file. PowerPoint files cannot be imported in this version.

## Statistical charts

Descriptive statistics, Histogram, and Box plot are also available from Chart type. Enter up to 100 observations or load an illustrative example.

- Descriptive statistics takes one value per row and reports count, mean, median, sample standard deviation, min/max, quartiles, IQR, 90th/95th percentiles, and potential outlier count. Sample SD uses n−1 and is unavailable for a single value.
- Histogram takes one value per row. Automatic bin count is the square root of n rounded up, limited to 2–12; you may choose 2–12 manually. Constant data uses one bin. Bins have equal width, include their left edge, and exclude the right edge except for the final bin.
- Box plot takes Group and Value fields, supporting up to four groups with unequal sample sizes. Whiskers end at the most extreme observed values within 1.5×IQR of the quartiles. Red points mark potential outliers, which remain in the data. Single values and constant groups display a collapsed box.

Percentiles and quartiles use linear interpolation at position (n−1)×p in sorted data. These tools export as editable shapes and text, with calculations refreshed on re-export from the project.

On a Trend / Chart slide, choose Pareto, Correlation + regression, or Correlation matrix. Use Load example data for an illustrative dataset, or enter your own values in the labeled row inputs.

- Pareto: up to 12 nonnegative category/value rows. Repeated category labels are aggregated, then sorted descending. The chart shows value bars, cumulative percentages on the right axis, an 80% reference, and the number of categories needed to reach 80%.
- Correlation: 3–100 matched numeric X/Y pairs. Reports Pearson r, R², observation count, and a least-squares line with an intercept. Constant variables produce undefined r; constant X has no fitted line. These are descriptive statistics, without significance tests or causal conclusions.
- Correlation matrix: 3–100 complete observations across 2–4 variables. Add variable columns and name them individually. Blue indicates positive correlation, red negative, and N/A indicates a constant variable. Blank and non-finite observations must be corrected; no rows are silently removed.

Statistical plots export as editable PowerPoint shapes and text, not native chart workbooks. Their computed values update when you edit the project and generate PowerPoint again. Existing chart types continue to export as native charts. Calculation reference: [NIST Pearson correlation](https://www.itl.nist.gov/div898/software/dataplot/refman2/auxillar/correlat.htm).

Drafts with unfinished rows remain available after reloading. Complete the fields before previewing or exporting. The row editor preserves existing columns and supports individually named series.

## Structure and extension

- `app.py`: Flask routes, error responses, local-only server.
- `engine.py`: validation, shared layout scene, SVG and PowerPoint renderers.
- `charts.py`, `images.py`: chart renderers and image validation/placement.
- `config/templates.json`: slide catalog, editable fields, defaults, and layout selection.
- `config/themes.json`: theme colors.
- `templates/index.html`, `static/`: offline editor.
- `tests/test_app.py`: API, template/export, negative data, and invalid-input tests.

To add a template using an existing layout, append a unique template entry in the JSON catalog with the matching field count. For a new layout, add a scene branch and corresponding validation rules in `engine.py`; the frontend automatically reads the catalog. Add themes by providing all six color keys and a name.

Run checks with `python -m unittest discover -s tests` after installing requirements (or set PYTHONPATH to `.packages` when using the bundled runtime). This is a local single-user application; the Flask development server binds only to 127.0.0.1.
