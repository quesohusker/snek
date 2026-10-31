# Snek

[![test](https://github.com/quesohusker/snek/actions/workflows/test.yml/badge.svg)](https://github.com/quesohusker/snek/actions/workflows/test.yml)

A visual workflow canvas for pandas. Drag tools onto a canvas, wire them together, and watch the data change at every step. When you are done, export the whole workflow as a plain Python script.

Snek runs on your own machine. A small Python server does the work, and your browser shows the canvas at http://127.0.0.1:8765. Your data never leaves your computer. The only network call is a once-a-day check for new versions, which you can turn off (see [Updates](#updates)).

## Download

Pick your system. These apps include everything Snek needs, so you do not need Python.

| System | Download |
|---|---|
| macOS, Apple Silicon (M1 and newer) | [Snek-macOS-AppleSilicon.zip](https://github.com/quesohusker/snek/releases/latest/download/Snek-macOS-AppleSilicon.zip) |
| macOS, Intel | [Snek-macOS-Intel.zip](https://github.com/quesohusker/snek/releases/latest/download/Snek-macOS-Intel.zip) |
| Windows 10 and 11 | [Snek-Windows.zip](https://github.com/quesohusker/snek/releases/latest/download/Snek-Windows.zip) |
| Linux x86-64 (Ubuntu 22.04 or newer) | [Snek-Linux.tar.gz](https://github.com/quesohusker/snek/releases/latest/download/Snek-Linux.tar.gz) |

- **macOS (one-time step required):** unzip and drag Snek to Applications. Snek is not signed by Apple yet, so the first time you open it macOS says **"Snek.app" Not Opened**. Click **Done**, not Move to Trash. Then allow Snek one of two ways:
  - **Fastest:** open Terminal and paste this line. It clears the block and starts Snek:
    ```bash
    xattr -dr com.apple.quarantine /Applications/Snek.app && open /Applications/Snek.app
    ```
  - **Through Settings:** paste this in Terminal to jump to the right page, scroll down to Security, click **Open Anyway**, and enter your password. Open Snek again and click **Open Anyway** once more.
    ```bash
    open "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Security"
    ```

  You only do this once. Snek then opens in your browser; stop it with File ▸ Quit Snek.
- **Windows:** unzip, open the Snek folder, and double-click `Snek.exe`. If Windows shows "Windows protected your PC", click More info ▸ Run anyway. A console window stays open while Snek runs; close it, or use File ▸ Quit Snek, to stop.
- **Linux:** extract and run `Snek/Snek`.

Snek keeps its settings and a copy of the sample project in `~/.snek`.

**Already have Python 3.12+?** The smaller [snek.zip](https://github.com/quesohusker/snek/releases/latest/download/snek.zip) runs from source: unzip it and double-click `snek.command` (macOS) or `snek.bat` (Windows), or run `sh snek.command` on Linux. The first start installs Snek's packages into a `.venv` folder.

## Why

Drag-and-drop data tools are fast to learn but lock your work inside the tool. Snek generates real pandas code for every step. You can read it in the Python tab of any tool, and Export gives you a standalone script that runs anywhere pandas runs.

## Tools

94 working tools so far. Pick a category in the tab bar under the menus and its tools appear in the sidebar. Star the ones you use most to keep them on the Favorites tab, or search across every category. Hover over any tool, in the sidebar or on the canvas, to see what input it needs.

| Category | Tools |
|---|---|
| In/Out | Input Data, Text Input, Output Data, Browse, Directory, Date Time Now |
| Preparation | Select, Filter, Formula, Multi-Field Formula, Multi-Row Formula, Sort, Sample, Select Records, Unique, Record ID, Rank, Tile, Auto Field, Data Cleansing, Imputation, Replace Text, Generate Rows |
| Join | Join (L/J/R outputs), Join Multiple, Union, Append Fields, Find Replace (lookup table) |
| Parse | Text to Columns, RegEx, DateTime, JSON Parse, Explode List, Unnest JSON |
| Transform | Summarize, Cross Tab, Transpose, Running Total, Weighted Average, Count Records |
| Data Investigation | Field Summary, Frequency Table, Correlation, Contingency Table, Test of Means, Chi-Square Test |
| Modeling | Linear, Logistic, Regularized (Ridge/Lasso/Elastic Net), Count (Poisson/negative binomial) and Gamma Regression, Decision Tree, Random Forest, Boosted Model, Naive Bayes, K-Nearest Neighbors, Support Vector Machine, Neural Network, Score, Model Comparison, Cross-Validation, Create Samples, Variance Inflation Factors |
| Predictive Grouping | K-Means Clusters, Cluster Diagnostics, Hierarchical Clustering, Principal Components, Find Nearest Neighbors |
| Time Series | TS Filler, Rolling Window, Seasonal Decomposition, ETS Forecast, ARIMA Forecast, TS Compare |
| Sports | **All sports:** Team Ratings (SRS/Massey), Elo Ratings, Opponent Adjust, Spread & Win Probability (grades picks against betting lines), Season Simulation, Pythagorean Expectation. **Football:** Garbage-Time Filter, Success Rate, Football Efficiency (EPA, success rate, explosiveness, havoc). **Basketball:** Four Factors (with offensive, defensive and net rating), Shooting Efficiency. **Baseball:** Batting Stats (through wOBA), Pitching Stats (through FIP). **Volleyball:** Volleyball Box Stats, Side-Out & Serve |
| Developer | Python (your own pandas code), Dynamic Input, Dynamic Rename, Dynamic Select, Field Info |

Input Data reads CSV, TSV, Excel, JSON, JSON Lines and Parquet, gzipped CSV included. Put `*` in the path to stack many files into one table, for example `flights_2013_*.csv.gz`. Directory plus Dynamic Input reads every file in a folder.

## Expressions

Filter and Formula take pandas expressions. Write a column as `[Column Name]`:

```
[pts] - [opp_pts]
iif([dep_delay] > 15, 'late', 'on time')
[Species].str.split(' ').str[0]
```

You can use `pd`, `np` and `iif(condition, then, else)`. Snek suggests a fix when a column name is misspelled.

Multi-Row Formula reaches into other rows with `[Row-1:column]` and `[Row+1:column]`, for example `[pts] - [Row-1:pts]` for the change since the last game. Multi-Field Formula applies one expression to many columns, with `[_CurrentField_]` standing for each column in turn.

## Modeling

Every model tool has an **M** output that carries the fitted model. Connect it to **Score** to predict new rows, or to **Model Comparison** with a validation sample to see which model holds up on data it never saw. Use **Create Samples** to make that split. Models come from scikit-learn and statsmodels, so exported scripts that use them list those packages at the top.

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
- Output Data offers one-click **Save in** buttons for the project's output folder, Desktop, Documents and Downloads, and shows the full path it will write to.

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
- Flights: daily delay trend (DateTime, Multi-Row Formula, Running Total, Rank, Tile)
- Penguins: predict body mass (Field Summary, Correlation, Linear Regression)
- Penguins: classify species (Create Samples, Decision Tree vs. Random Forest, Model Comparison, Score)
- Flights: forecast daily departures (TS Filler, ETS and ARIMA with weekly seasonality)
- Flights: forecast accuracy check (hold out two weeks, forecast them, grade with TS Compare; Seasonal Decomposition)
- Penguins: model bake-off (five classifiers, 5-fold Cross-Validation)
- Demo: league ratings for made-up teams (Team Ratings and Elo side by side)
- Sports: football play-by-play kit (Garbage-Time Filter, Success Rate, Football Efficiency, Opponent Adjust)
- Sports: season projection (Team Ratings, Season Simulation, Spread & Win Probability against lines, Pythagorean Expectation)
- Sports: basketball four factors (Four Factors, Shooting Efficiency)
- Sports: baseball batting and pitching (Batting Stats, Pitching Stats)
- Sports: volleyball box and side-out (Volleyball Box Stats, Side-Out & Serve)
- Demo: no files needed

All bundled data is CC0, and the sports data is made up. See [examples/data/README.md](examples/data/README.md) for sources and citations.

## Updates

Once a day, Snek asks GitHub's public releases page whether a newer version exists. If one does, a link appears in the toolbar. The check sends nothing about you or your data, and Snek never downloads or installs anything on its own. Turn it off with Help ▸ Check for updates automatically, or check on demand with Help ▸ Check for updates.

## Caveats

- Formula and Python tools run any code you type. The server listens on 127.0.0.1 only. Do not expose it to a network.
- Data is held in memory. Hundreds of thousands of rows are fast; tens of millions will strain it.
- No undo/redo or copy/paste yet.

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
