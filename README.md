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

96 steps so far. Pick a category in the tab bar under the menus and its steps appear in the sidebar, or search across every category. Every menu command is also in the Commands list at the top of the sidebar. Hover over any step, in the sidebar or on the canvas, to see what input it needs.

| Category | Steps |
|---|---|
| Open & Save | Open File, Type or Paste Data, Save File, List Files, Read Listed Files, Current Time, Make a Sequence, Web API |
| Rows | Keep Rows, Sort Rows, Take Rows, Rows by Position, Find Duplicates, Number Rows, Rank Rows, Bucket Values |
| Columns | Choose Columns, Calculate, Calculate Many Columns, Use Previous Rows, Cumulative Total, Rename Many Columns, Choose Columns by Rule, Column List |
| Clean | Tidy Up, Detect Types, Fill Blanks, Replace Text, Split Text, Text Pattern, Dates and Times, Read JSON Text, One Row per Item, Spread Out Fields |
| SQL | Match Tables, Match Many Tables, Stack Tables, Every Combination, Look Up Values |
| Group & Pivot | Group and Total, Pivot Wider, Pivot Longer, Weighted Average, Count Rows |
| Explore | Inspect, Profile Columns, Count Values, Correlation, Cross Count, Compare Averages, Test Independence, Chart (bar, line, scatter, area, histogram, box plot, heat map) |
| Model | Linear and Logistic Regression, Ridge and Lasso, Count and Gamma Regression, Decision Tree, Random Forest, Gradient Boosting, Naive Bayes, Nearest-Neighbor Model, Support Vector Machine, Neural Network, Predict, Compare Models, Cross-Validation, Train and Test Split, Check Overlap (VIF) |
| Segment | K-Means Groups, Choose Number of Groups, Hierarchical Groups, Principal Components, Most Similar Rows |
| Forecast | Fill Missing Dates, Rolling Window, Smoothing Forecast, ARIMA Forecast, Trend and Season, Check Forecast |
| Sports | **All sports:** Team Ratings (SRS/Massey), Elo Ratings, Opponent Adjust, Spread & Win Probability (grades picks against betting lines), Season Simulation, Pythagorean Expectation. **Football:** Garbage-Time Filter, Success Rate, Football Efficiency (EPA, success rate, explosiveness, havoc). **Basketball:** Four Factors (with offensive, defensive and net rating), Shooting Efficiency. **Baseball:** Batting Stats (through wOBA), Pitching Stats (through FIP). **Volleyball:** Volleyball Box Stats, Side-Out & Serve |
| Code | Python Code (your own Python code) |

Open File reads CSV, TSV, Excel, JSON, JSON Lines and Parquet, gzipped CSV included. Put `*` in the path to stack many files into one table, for example `flights_2013_*.csv.gz`. List Files plus Read Listed Files reads every file in a folder.

## Editing

Snek edits like a desktop app:

- Undo and redo every change with ⌘Z and ⇧⌘Z (Ctrl+Z and Ctrl+Shift+Z on Windows and Linux).
- Cut, copy, paste and duplicate tools with ⌘X, ⌘C, ⌘V and ⌘D. Connections between copied tools come along. Paste works between Snek windows.
- Drag a box on the canvas, or Shift-click, to select several tools. Scroll to pan; ⌘-scroll or pinch to zoom.
- Right-click a tool or the canvas for a menu.
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

Use Previous Rows reaches into other rows with `[Row-1:column]` and `[Row+1:column]`, for example `[pts] - [Row-1:pts]` for the change since the last game. Calculate Many Columns applies one expression to many columns, with `[_CurrentField_]` standing for each column in turn.

## Modeling

Every model step has a **model** output that carries the fitted model. Connect it to **Predict** to score new rows, or to **Compare Models** with a validation sample to see which model holds up on data it never saw. Use **Train and Test Split** to make that split. Models come from scikit-learn and statsmodels, so exported scripts that use them list those packages at the top.

## Create a workflow with AI

Click **Create with AI** in the toolbar, or choose **Workflow ▸ Create workflow with AI…**, and describe what you want in plain words: "Rate the teams in the made-up football league with a 28-point margin cap, simulate the unplayed games, and chart projected wins." Claude designs the workflow, and Snek runs it. If a tool fails, Snek sends the error back to Claude for a fix, up to two times. The finished tools land on the canvas, ready to adjust; one Undo removes them.

- It needs an Anthropic API key, saved in **Edit ▸ Settings ▸ AI**. Anthropic bills your account for each request. Settings also picks the model: Claude Opus 5.5 by default, or the faster and cheaper Sonnet 5.5 or Haiku 5.5.
- Snek sends Claude your description, the list of Snek's tools, and the names and column names of the data files in the open project. It never sends the data itself. The dialog's **Show exactly what is sent** link shows the full text.

## Data Connections

**API Request** downloads JSON or CSV from any other web API. If the API needs a key, save the key under a name in the same Settings section and give that name to the tool.

Keys stay on your computer in `~/.snek/connections.json`. They never go into workflow files or exported scripts. An exported script reads the same file, or an environment variable named after the key, such as `WEATHER_API_KEY`.

## Charts

The **Chart** tool draws bar, line, scatter, area, histogram, box plot and heat map charts. The chart shows in the results panel, where its menu saves a PNG or SVG. To save a web page, connect Save File with a path ending in `.html`; stack several charts with Stack Tables first to put them on one page. Chart pages load the charting library from the web, so they need an internet connection to display.

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

All bundled data is CC0, and the sports data is made up. See [examples/data/README.md](examples/data/README.md) for sources and citations.

## Updates

Once a day, Snek asks GitHub's public releases page whether a newer version exists. If one does, a link appears in the toolbar. The check sends nothing about you or your data, and Snek never downloads or installs anything on its own. Turn it off with Help ▸ Check for updates automatically, or check on demand with Help ▸ Check for updates.

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
