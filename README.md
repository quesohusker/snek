# Snek

[![test](https://github.com/quesohusker/snek/actions/workflows/test.yml/badge.svg)](https://github.com/quesohusker/snek/actions/workflows/test.yml)

A visual workflow canvas for Python. Drag tools onto a canvas, wire them together, and watch the data change at every step. When you are done, export the whole workflow as a plain Python script.

Snek runs on your own machine. A small Python server does the work, and your browser shows the canvas at http://127.0.0.1:8765. Your data never leaves your computer. Snek goes online only for a once-a-day check for new versions, which you can turn off (see [Updates](#updates)), and when you use the API Request or Create with AI features.

## Download

Pick your system. These apps include everything Snek needs, so you do not need Python.

| System | Download |
|---|---|
| macOS, Apple Silicon (M1 and newer) | [Snek-macOS-AppleSilicon.zip](https://github.com/quesohusker/snek/releases/latest/download/Snek-macOS-AppleSilicon.zip) |
| macOS, Intel | [Snek-macOS-Intel.zip](https://github.com/quesohusker/snek/releases/latest/download/Snek-macOS-Intel.zip) |
| Windows 10 and 11 | [Snek-Windows.zip](https://github.com/quesohusker/snek/releases/latest/download/Snek-Windows.zip) |
| Linux x86-64 (Ubuntu 22.04 or newer) | [Snek-Linux.tar.gz](https://github.com/quesohusker/snek/releases/latest/download/Snek-Linux.tar.gz) |

- **macOS (one-time step required):** unzip and drag Snek to Applications. Snek is not signed by Apple yet, so the first time you open it macOS says **"Snek.app" Not Opened**. Click **Done**, not Move to Trash. Then allow Snek one of two ways:
  - **Through Settings (recommended):** paste this in Terminal to jump to the right page, scroll down to Security, click **Open Anyway**, and enter your password. Open Snek again and click **Open Anyway** once more. macOS still scans the app and records the exception for Snek alone.
    ```bash
    open "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Security"
    ```
  - **Faster, less safe:** this line removes the download flag from every file inside the app, so macOS skips its checks on them. Use it only after you have checked the download against `SHA256SUMS.txt` (see below).
    ```bash
    xattr -dr com.apple.quarantine /Applications/Snek.app && open /Applications/Snek.app
    ```

  You only do this once. Snek then opens in your browser; stop it with File ▸ Quit Snek.
- **Windows:** unzip, open the Snek folder, and double-click `Snek.exe`. If Windows shows "Windows protected your PC", click More info ▸ Run anyway. A console window stays open while Snek runs; close it, or use File ▸ Quit Snek, to stop.
- **Linux:** extract and run `Snek/Snek`.
- **Check the download:** every release includes `SHA256SUMS.txt`. In Terminal, run `shasum -a 256 -c SHA256SUMS.txt --ignore-missing` in the folder that holds the download (on Windows, `certutil -hashfile Snek-Windows.zip SHA256` and compare the line). A mismatch means the file is not the one the release build made.

Snek keeps its settings and a copy of the sample project in `~/.snek`.

**Already have Python 3.12+?** The smaller [snek.zip](https://github.com/quesohusker/snek/releases/latest/download/snek.zip) runs from source: unzip it and double-click `snek.command` (macOS) or `snek.bat` (Windows), or run `sh snek.command` on Linux. The first start installs Snek's packages into a `.venv` folder.

## Why

Drag-and-drop data tools are fast to learn but lock your work inside the tool. Snek generates real Python code for every step. You can read it in the Python tab of any tool, and Export gives you a standalone script that runs anywhere Python runs.

## Tools

110 steps so far. Pick a category in the tab bar under the menus and its steps appear in the sidebar, or search across every category. Every menu command is also in the Commands list at the top of the sidebar. Hover over any step, in the sidebar or on the canvas, to see what input it needs.

| Category | Steps |
|---|---|
| Open & Save | Open File, Type or Paste Data, Save File, List Files, Read Listed Files, Current Time, Make a Sequence, Web API, GitHub, Create Python |
| Rows | Keep Rows, Sort Rows, Take Rows, Rows by Position, Find Duplicates, Number Rows, Rank Rows, Bucket Values |
| Columns | Choose Columns, Calculate, Calculate Many Columns, Use Previous Rows, Cumulative Total, Rename Many Columns, Choose Columns by Rule, Column List |
| Clean | Tidy Up, Detect Types, Fill Blanks, Replace Text, Map Values, Split Text, Text Pattern, Dates and Times, Read JSON Text, One Row per Item, Spread Out Fields |
| SQL | Match Tables, Match Many Tables, Stack Tables, Every Combination, Look Up Values |
| Group & Pivot | Group and Total, Pivot Wider, Pivot Longer, Weighted Average, Count Rows |
| Explore | Inspect, Profile Columns, Summary Statistics, Count Values, Correlation, Cross Count, Compare Averages, Test Independence, Chart (bar, line, scatter, area, histogram, box plot, heat map) |
| Model | Linear and Logistic Regression, Ridge and Lasso, Count and Gamma Regression, Decision Tree, Random Forest, Gradient Boosting, Naive Bayes, Nearest-Neighbor Model, Support Vector Machine, Neural Network, Predict, Compare Models, Cross-Validation, Train and Test Split, Check Overlap (VIF) |
| Segment | K-Means Groups, Choose Number of Groups, Hierarchical Groups, Principal Components, Most Similar Rows |
| Forecast | Fill Missing Dates, Rolling Window, Smoothing Forecast, ARIMA Forecast, Trend and Season, Check Forecast |
| Simulate | **Random data:** Random Data, Fit Distribution. **Process:** Make Arrivals, Simulate Process |
| Maps | **Draw:** Map Chart. **Places:** Geocode Addresses, Distance, Find Nearest. **Boundaries:** Read Map File, Find Region |
| Sports | **All sports:** Team Ratings (SRS/Massey), Elo Ratings, Opponent Adjust, Spread & Win Probability (grades picks against betting lines), Season Simulation, Pythagorean Expectation. **Football:** Garbage-Time Filter, Success Rate, Football Efficiency (EPA, success rate, explosiveness, havoc). **Basketball:** Four Factors (with offensive, defensive and net rating), Shooting Efficiency. **Baseball:** Batting Stats (through wOBA), Pitching Stats (through FIP). **Volleyball:** Volleyball Box Stats, Side-Out & Serve |
| Code | Python Code (your own Python code) |

Open File reads CSV, TSV, Excel, JSON, JSON Lines and Parquet, gzipped CSV included. Put `*` in the path to stack many files into one table, for example `flights_2013_*.csv.gz`. List Files plus Read Listed Files reads every file in a folder.

Create Python writes the workflow as a file when you press Run. Connect it to the last step of the branch you want, or connect several steps to include several branches. The file holds every step upstream of those, in order. Choose a Python script (`.py`) or a Jupyter notebook (`.ipynb`). The notebook has one section for each step: a heading that says what the step does, then its code. Export Python in the File menu gives the same two formats for the whole workflow.

## Editing

Snek edits like a desktop app:

- Undo and redo every change with ⌘Z and ⇧⌘Z (Ctrl+Z and Ctrl+Shift+Z on Windows and Linux).
- Cut, copy, paste and duplicate tools with ⌘X, ⌘C, ⌘V and ⌘D. Connections between copied tools come along. Paste works between Snek windows.
- Drag a box on the canvas, or Shift-click, to select several tools. Scroll to pan; ⌘-scroll or pinch to zoom.
- Right-click a tool or the canvas for a menu.
- The **Favorites** section at the top of the sidebar keeps the tools you use most. It starts with ten popular tools. Click the star on any tool to add it or remove it. **Restore popular tools** brings the starting set back.
- Click **Clean up** in the toolbar, or press ⇧L, to line every step up in neat columns that follow the flow. One Undo puts them back.
- Paste a table copied from Excel and Snek makes a Type or Paste Data step from it. Drop a data file on the canvas and Snek copies it into the project's `data/` folder and adds an Open File step.
- The copy button above the results grid copies every row, ready to paste into Excel.
- Snek asks before it closes a workflow with unsaved changes. Help ▸ Keyboard shortcuts lists every shortcut.

## Expressions

Keep Rows and Calculate take Python expressions. Write a column as `[Column Name]`:

```
[pts] - [opp_pts]
iif([dep_delay] > 15, 'late', 'on time')
[Species].str.split(' ').str[0]
```

You can use `pd`, `np` and `iif(condition, then, else)`. Snek suggests a fix when a column name is misspelled.

### Spreadsheet functions

Expressions also know 311 spreadsheet functions with Excel's names and rules: `IF`, `IFS`, `IFERROR`, `SWITCH`, `LEFT`, `TRIM`, `TEXT`, `DATE`, `WORKDAY`, `ROUND`, `SUMIF`, `COUNTIFS`, `STDEV.S`, `PERCENTILE.INC`, `NORM.DIST`, `T.TEST`, `PMT`, `IRR`, `MATCH`, `XMATCH`, `INDEX` and more. The groups are Logical, Information, Text, Date and time, Math and trigonometry, Statistical, Distributions, Financial, Lookup, Mapping, and Engineering. 39 old Excel names such as `STDEV` and `NORMDIST` work too. Open the **Functions** tab in the sidebar, next to All, to browse every function by group. Click one to add a Calculate step that already uses it. The sidebar search finds them too. Under an expression box, click **Functions** to search them by name or by plain words ("remove spaces" finds `TRIM`) and insert one into a formula. Type a name in capitals and press Tab to complete it.

```
IF([sales] > 100, "high", "low")
ROUND([price] * 1.08, 2)
TEXT([game_date], "mmm d, yyyy")
WORKDAY([ordered], 3)
[sales] / SUM([sales])
SUMIF([region], [region], [sales])
PMT([rate] / 12, [months], [amount])
NORM.DIST([score], AVERAGE([score]), STDEV.S([score]), TRUE)
```

- Write names in capitals, with the dot where Excel has one: `CEILING.MATH`, `NETWORKDAYS.INTL`. Snek also accepts `TRUE`, `FALSE` and `<>`. Lowercase `round`, `sum` and `max` stay Python's own.
- Most functions work row by row on a column. The summary functions (`SUM`, `AVERAGE`, `MEDIAN`, `STDEV.S`, `CORREL`, `SLOPE`, `IRR` and the like) read the whole column and give one number, so `[sales] / SUM([sales])` is each row's share of the total. A few give a column back: `TREND`, `FREQUENCY`.
- The criteria functions (`SUMIF`, `COUNTIF`, `AVERAGEIF`, `SUMIFS`, `COUNTIFS`, `AVERAGEIFS`, `MAXIFS`, `MINIFS`) take Excel's criteria: `">5"`, `"<>West"`, `"w*"`, `""`. Give a column as the criteria and each row gets the answer for its own value, like a spreadsheet's formula filled down: `SUMIF([region], [region], [sales])` is each row's region total. The columns must have the same length.
- In a column that holds numbers and other things, the summary functions skip text, blanks and True/False, as Excel does. A column that is all True/False adds as 1 and 0, so `SUM([flag])` counts the true rows. Text that looks like a number is skipped inside a column; a value written straight in the formula, such as `SUM(1, "2")`, is read as a number.
- `MATCH`, `XMATCH`, `INDEX` and `LOOKUP` count positions from 1. Give a column as the lookup value to look up every row. A blank in a looked-up column stays blank, where Excel shows 0. Searches that need a sorted list (`MATCH` type 1 or -1, `LOOKUP`) give a blank when the value is out of range.
- `IRR`, `XIRR`, `RATE` and `MIRR` solve for the rate. They agree with Excel to about 7 digits, because Excel stops its search early.
- The distribution functions use scipy, which the apps already include. Exported scripts that use them list scipy at the top.
- Dates are real dates, not day numbers. `TIME` gives a time of day you can add to a date. A text such as `"2024-03-05"` works wherever a date is expected.
- A blank in gives a blank out. The exceptions follow Excel: `LEN`, `CONCAT`, `TEXTJOIN` and `ISBLANK` treat a blank as empty text, and `N` gives 0. An error such as a negative square root gives a blank. `IFERROR` replaces a blank or an infinite result, so it cannot tell an error from a real blank.
- `RAND()` gives one number. Pass a column to get a new number on every row: `RAND([id])`. For repeatable draws use Random Data.
- `CHAR` and `CODE` use Windows-1252 on every computer. `TEXT` does not support fraction formats such as `# ?/?`. `VALUE` reads `1/2` as an error, where Excel reads it as a date. A whole-number column keeps every digit when it becomes text. Excel cuts a typed constant to 15 digits.
- Exported scripts carry only the functions the workflow uses.

The functions were checked against Microsoft Excel for Mac 16.113.2 with about 2,500 formulas: many of the worked examples in Microsoft's function pages, and edge cases such as leap days, ties in rounding, negative numbers, mixed columns and blanks. The Excel answers are stored in `tests/data/excel_fx.json` and `tests/data/excel_fx_ranges.json`, so the check runs without Excel. Each place where Snek chooses to differ is listed in those files with its reason.

Use Previous Rows reaches into other rows with `[Row-1:column]` and `[Row+1:column]`, for example `[pts] - [Row-1:pts]` for the change since the last game. Calculate Many Columns applies one expression to many columns, with `[_CurrentField_]` standing for each column in turn.

## Modeling

Every model step has a **model** output that carries the fitted model. Connect it to **Predict** to score new rows, or to **Compare Models** with a validation sample to see which model holds up on data it never saw. Use **Train and Test Split** to make that split. Models come from scikit-learn and statsmodels, so exported scripts that use them list those packages at the top.

## Create a workflow with AI

Click **Create with AI** in the toolbar, or choose **Workflow ▸ Create workflow with AI…**, and describe what you want in plain words: "Rate the teams in the made-up football league with a 28-point margin cap, simulate the unplayed games, and chart projected wins." Claude designs the workflow, and Snek runs it. If a tool fails, Snek sends the error back to Claude for a fix, up to two times. The finished tools land on the canvas, ready to adjust; one Undo removes them.

- It needs an Anthropic API key, saved in **Edit ▸ Settings ▸ AI**. Anthropic bills your account for each request. Settings also picks the model: Claude Opus 5.5 by default, or the faster and cheaper Sonnet 5.5 or Haiku 5.5.
- Snek sends Claude your description, the list of Snek's tools, and the names and column names of the data files in the open project. It never sends the data itself. The dialog's **Show exactly what is sent** link shows the full text.

## Data Connections

**API Request** downloads JSON or CSV from any other web API. If the API needs a key, save the key under a name in the same Settings section and give that name to the tool.

**GitHub** reads a user's or organization's repositories, a repository's issues, pull requests, commits and releases, a folder listing, or a data file (CSV, TSV, Excel, JSON, JSON Lines or Parquet) stored in a repository. Public data works with no setup. For private repositories, save a GitHub token in **Edit ▸ Settings ▸ GitHub**. Give the token read access to the repositories you want to read. The token goes only to `api.github.com`. GitHub limits anonymous requests per hour; the tool says when you hit the limit. It reads only. It never commits or changes anything on GitHub.

Keys stay on your computer in `~/.snek/connections.json`. They never go into workflow files or exported scripts. An exported script reads the same file, or an environment variable named after the key, such as `WEATHER_API_KEY`.

## Charts

The **Chart** tool draws bar, line, scatter, area, histogram, box plot and heat map charts. The chart shows in the results panel, where its menu saves a PNG or SVG. To save a web page, connect Save File with a path ending in `.html`; stack several charts with Stack Tables first to put them on one page. Chart pages load the charting library from the web, so they need an internet connection to display.

## Maps and mapping

**Map Values** (Clean) changes a column's values with a list you paste, one pair per line: `TX = Texas`. A value with no pair stays as it is, or becomes a default or blank. A two-column paste from Excel works. For a lookup table in another table, use Look Up Values.

The **Maps** category works with places:

- **Map Chart** draws points from latitude and longitude columns, shades US states or US counties by a value, or shades the regions of a map file. States can be named, written as two-letter codes or given as FIPS codes; counties use five-digit FIPS codes. Several rows for one state are added, averaged or counted, as you choose. The map shows in the results panel; Save File with an `.html` path saves it as a web page. The outlines of the US and the world load from the web (the open Natural Earth and US Census shapes, through the `vega-datasets` files on jsdelivr), so a map needs an internet connection to draw.
- **Distance** adds the straight-line distance over the Earth between two points in each row, in miles, kilometers, meters, feet, yards or nautical miles, and optionally the compass direction. **Find Nearest** finds, for each row, the nearest places in a second table, or every place within a distance. It gives one row per match with the rank and distance. Distances use a sphere with the mean Earth radius, so they can differ from a survey by up to 0.5%.
- **Geocode Addresses** turns US street addresses into latitude and longitude with the US Census Bureau's free geocoder. **The addresses are sent to geocoding.geo.census.gov**, so do not use it on addresses you must keep private. It adds the latitude, longitude, a match status and the address the Census matched. Addresses it cannot find get a blank.
- **Read Map File** reads a shapefile (the `.shp` with its `.dbf` beside it) or a GeoJSON file into a table: one row per shape with its attributes, a center point and the shape itself in a `geometry` column. Coordinates must be latitude and longitude (WGS 84); Snek says so when a file uses a projection. **Find Region** adds, to each point, the columns of the region it falls in, using the shapes from Read Map File. A point in two regions gets the first.

The spreadsheet functions `DISTANCE`, `BEARING`, `STATE_NAME`, `STATE_ABBR`, `STATE_FIPS` and `XLOOKUP` do the same jobs row by row inside Calculate.

## Estimates, distributions and simulation

**Summary Statistics** gives, for each numeric column, the mean with its standard error and a confidence interval, a confidence interval for the standard deviation, a t-test against a value you pick, an effect size and a normality test. Category columns get each level's share with a confidence interval. Add a group column to get one set per group.

**Fit Distribution** ranks distributions for a column by AIC: normal, lognormal, exponential, gamma, Weibull, uniform, triangular, logistic and beta for measurements, Poisson, geometric and negative binomial for counts. It also gives Kolmogorov-Smirnov statistics (the p-values are approximate, because the parameters were fitted from the same data) and a chart of the data with the best fits drawn over it. Gamma and Weibull include the exponential as a special case, so they often rank just above it.

**Random Data** draws columns from those distributions, or a weighted choice from a list. Connect a Fit Distribution result to draw from the best fit.

**Simulate Process** runs a discrete-event simulation. Entities (cars, customers, orders) arrive, queue, get served and move on through a chain of stations. Each station has servers, a limit on how many can wait, a service-time distribution and a next station, or several with weights. A full line turns arrivals away. A station can hold its server until the next station has room, which is how a drive-thru lane backs up. A schedule table can change the number of servers during the run, and a numeric attribute can scale the service time (items in the order). Arrivals come from a table of events (your own log, or **Make Arrivals**) or from a gap distribution set in the tool, which gives fresh arrivals in every replication. Run many replications to get means with 95% intervals. The outputs are every entity, every visit to a station, station statistics (utilization, queue length, waits, losses), the summary, and an optional event log. The sample "Simulate - drive-thru lane" has the order board, the pay window and the pickup window.

Time has no unit. Use one unit throughout, such as seconds. The engine matches queueing theory: the tests check M/M/1, M/M/2 and M/M/1/K results against the exact formulas.

## Sports analytics

The Sports tab groups its tools by sport. The **All sports** tools work for any game with two teams and a score:

- **Team Ratings** and **Elo Ratings** rate teams from game results.
- **Opponent Adjust** corrects any per-game stat for the strength of the opponents faced.
- **Spread & Win Probability** turns ratings into a predicted margin and win chance for each game. Give it a betting line column and it grades every pick against the line.
- **Season Simulation** plays out the rest of a schedule thousands of times: projected wins, the chance of reaching a win total, and the chance to win out.
- **Pythagorean Expectation** shows which teams won more or fewer games than their scoring says they should.

The sport groups read play-by-play and box scores: success rate, EPA and havoc for football, the four factors for basketball, OBP through wOBA and ERA through FIP for baseball, and hitting percentage and side-out rate for volleyball.

Snek bundles no real league data. Bring your own exports, such as CFBD or NCAA stats files. The sports samples use made-up leagues.

## Files, autosave and settings

Snek workflows are `.snek` files. **File ▸ Save to file…** saves one anywhere, and **File ▸ Open file…** opens one from anywhere. After that, ⌘S saves back to the same file. On a Mac, Snek registers `.snek` as its document type, and `Snek path/to/workflow.snek` opens a file from the command line.

Snek autosaves every 5 minutes. Change the interval, or turn it off with 0, in **Edit ▸ Settings…**. By default autosave saves your workflow's own file; untitled work goes to `~/.snek/autosave` instead. Choose "Separate backup copies only" if you'd rather autosave never touch your files. **File ▸ Open autosaves…** opens that folder.

## Projects

A project is a folder for one piece of analysis. **File ▸ New project…** creates one with `data/`, `output/` and `workflows/` inside. **File ▸ Open project folder…** opens any existing folder as a project. While a project is open:

- File ▸ Open recent lists that project's workflows (saved as `.snek` files in `workflows/`).
- A relative path such as `output/results.csv` or `data/games.csv` starts from the project folder.
- Save File offers one-click **Save in** buttons for the project's output folder, Desktop, Documents and Downloads, and shows the full path it will write to.

The Snek folder itself is the built-in **Snek examples** project. Snek remembers the last project in `~/.snek/config.json`.

## File picker shortcuts

The file picker lists the project folders, Desktop, Documents, Downloads, Home and the bundled examples. Add your own folders with the `SNEK_PLACES` environment variable:

```bash
SNEK_PLACES="Data=~/data;Clients=~/work/clients" .venv/bin/python -m snek
```

## Sample workflows

The `workflows/` folder includes samples built on the bundled open data in `examples/data/`:

- Penguins: body mass by species
- Penguins: clean the raw field file
- Flights: Q1 delays by airline (wildcard input and a join)
- Flights: weather at departure (multi-key join)
- Flights: fleets from nested JSON (explode and unnest)
- Flights: daily delay trend (Dates and Times, Use Previous Rows, Cumulative Total, Rank Rows, Bucket Values)
- Penguins: predict body mass (Profile Columns, Correlation, Linear Regression)
- Penguins: classify species (Train and Test Split, Decision Tree vs. Random Forest, Compare Models, Predict)
- Flights: forecast daily departures (Fill Missing Dates, Smoothing and ARIMA forecasts with weekly seasonality)
- Flights: forecast accuracy check (hold out two weeks, forecast them, grade with Check Forecast; Trend and Season)
- Penguins: model bake-off (five classifiers, 5-fold Cross-Validation)
- Demo: league ratings for made-up teams (Team Ratings and Elo side by side)
- Sports: football play-by-play kit (Garbage-Time Filter, Success Rate, Football Efficiency, Opponent Adjust)
- Sports: season projection (Team Ratings, Season Simulation, Spread & Win Probability against lines, Pythagorean Expectation)
- Sports: basketball four factors (Four Factors, Shooting Efficiency)
- Sports: baseball batting and pitching (Batting Stats, Pitching Stats)
- Sports: volleyball box and side-out (Volleyball Box Stats, Side-Out & Serve)
- Penguins: charts (four chart types saved together as one web page)
- Demo: no files needed
- Simulate: drive-thru lane (order board, pay window and pickup window, made-up numbers)
- Simulate: fit and generate (fit a distribution, draw from it, test the draws)
- Maps: shaded states (Map Chart, STATE_NAME and STATE_FIPS, Map Values; made-up scores)
- Maps: nearest depot to each store (Find Nearest, Map Chart, made-up stores and depots)
- Maps: zones and customers (Read Map File, Find Region, a join, two maps; made-up zones)

All bundled data is CC0, and the sports data, the sales zones and the stores are made up. See [examples/data/README.md](examples/data/README.md) for sources and citations.

## Updates

Once a day, Snek asks GitHub's public releases page whether a newer version exists. If one does, a link appears in the toolbar. The check sends nothing about you or your data, and Snek never downloads or installs anything on its own. Turn it off with Help ▸ Check for updates automatically, or check on demand with Help ▸ Check for updates.

## Setup and packages

The first time you start Snek from source, `snek.command` (or `snek.bat`) makes a `.venv` folder and installs Snek's packages into it. Your own Python is not changed. On every later start it checks that each needed package is present and recent enough, and it adds or updates them inside `.venv` if not. `python -m snek --check` prints the same check and exits with 1 if anything is missing. Snek needs Python 3.12 or newer for that first step.

The downloadable apps and the Mac App Store app carry their own Python and every package, so there is nothing to install. The Mac app checks its own parts the first time it starts after an install or update. If a part is missing or damaged, it says so and asks you to reinstall. It never downloads code. A Python Code step that imports a package the app does not include says so and points you to Export Python, so you can run the workflow with your own Python.

## Caveats

- Calculate and Python Code run any code you type. The server listens on 127.0.0.1 only. Do not expose it to a network.
- Data is held in memory. Hundreds of thousands of rows are fast; tens of millions will strain it.

## Build from source

You need Python 3.12+ and Node 20.19+.

```bash
git clone https://github.com/quesohusker/snek.git
cd snek
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cd frontend && npm install && npm run build && cd ..
.venv/bin/python -m snek
```

Your browser opens Snek. Choose **File ▸ Open recent** and pick a sample workflow, then press **Run** (⌘ Enter).

## License

Snek is free to download and use for personal, noncommercial purposes under the [PolyForm Strict License 1.0.0](LICENSE). You may not sell it, redistribute it, or publish modified versions. Businesses that want to use Snek for commercial work need a separate license; open an issue to ask.

The bundled example data is CC0 (see [examples/data/README.md](examples/data/README.md)). Third-party components keep their own licenses, listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
