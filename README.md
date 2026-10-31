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


## Tools

45 tools so far, modeled on the core Alteryx palettes:

| Category | Tools |
|---|---|
| In/Out | Input Data, Text Input, Output Data, Browse, Directory, Date Time Now |
| Preparation | Select, Filter, Formula, Multi-Field Formula, Multi-Row Formula, Sort, Sample, Select Records, Unique, Record ID, Rank, Tile, Auto Field, Data Cleansing, Imputation, Replace Text, Generate Rows |
| Join | Join (L/J/R outputs), Join Multiple, Union, Append Fields, Find Replace (lookup table) |
| Parse | Text to Columns, RegEx, DateTime, JSON Parse, Explode List, Unnest JSON |
| Transform | Summarize, Cross Tab, Transpose, Running Total, Weighted Average, Count Records |
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

## Sample workflows

The `workflows/` folder includes samples built on the bundled open data in `examples/data/`:

- Penguins: body mass by species
- Penguins: clean the raw field file
- Flights: Q1 delays by airline (wildcard input and a join)
- Flights: weather at departure (multi-key join)
- Flights: fleets from nested JSON (explode and unnest)
- Demo: no files needed

All bundled data is CC0. See [examples/data/README.md](examples/data/README.md) for sources and citations.

## Development

Build a standalone app for the system you are on:

```bash
.venv/bin/pip install pyinstaller pillow
.venv/bin/python packaging/build.py
.venv/bin/python packaging/smoke_test.py packaging/dist/Snek.app/Contents/MacOS/Snek
```

Pushing a `v*` tag runs `.github/workflows/release.yml`, which builds and smoke-tests the macOS, Windows and Linux apps and attaches them to the GitHub release.

```bash
.venv/bin/python -m pytest -q
cd frontend && npx tsc --noEmit && npm run build
```

For hot reload, run the server, then `npm run dev` in `frontend/` and open http://localhost:5173.

Each tool lives in `snek/tools/` as a class that returns pandas source code. The engine runs that code, and Export writes the same code, so the canvas and the script cannot drift apart. See [CLAUDE.md](CLAUDE.md) for the architecture notes.

## Projects

A project is a folder for one piece of analysis. **File ▸ New project…** creates one with `data/`, `output/` and `workflows/` inside. **File ▸ Open project folder…** opens any existing folder as a project. While a project is open:

- File ▸ Open recent lists that project's workflows.
- A relative path such as `output/results.csv` or `data/games.csv` starts from the project folder.
- Output Data offers one-click **Save in** buttons for the project's output folder, Desktop, Documents and Downloads, and shows the full path it will write to.

The Snek folder itself is the built-in **Snek examples** project. Snek remembers the last project in `~/.snek/config.json`.

## File picker shortcuts

The file picker lists the project folders, Desktop, Documents, Downloads, Home and the bundled examples. Add your own folders with the `SNEK_PLACES` environment variable:

```bash
SNEK_PLACES="Data=~/data;Clients=~/work/clients" .venv/bin/python -m snek
```

## Updates

Once a day, Snek asks GitHub's public releases page whether a newer version exists. If one does, a link appears in the toolbar. The check sends nothing about you or your data, and Snek never downloads or installs anything on its own. Turn it off with Help ▸ Check for updates automatically, or check on demand with Help ▸ Check for updates.

## Caveats

- Formula and Python tools run any code you type. The server listens on 127.0.0.1 only. Do not expose it to a network.
- Data is held in memory. Hundreds of thousands of rows are fast; tens of millions will strain it.
- No undo/redo or copy/paste yet.

## License

MIT. See [LICENSE](LICENSE).
