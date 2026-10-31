# Snek

[![test](https://github.com/quesohusker/snek/actions/workflows/test.yml/badge.svg)](https://github.com/quesohusker/snek/actions/workflows/test.yml)

A visual workflow canvas for pandas. Drag tools onto a canvas, wire them together, and watch the data change at every step. When you are done, export the whole workflow as a plain Python script.

Snek runs on your own machine. A small Python server does the work, and your browser shows the canvas at http://127.0.0.1:8765. Nothing leaves your computer.

## Download

**[Download Snek (zip)](https://github.com/quesohusker/snek/releases/latest/download/snek.zip)**

1. Install [Python 3.12 or newer](https://www.python.org/downloads/) if you do not have it.
2. Unzip the file.
3. Start Snek:
   - macOS: double-click `snek.command`. If macOS blocks it, open System Settings ▸ Privacy & Security and click Open Anyway, or run `sh snek.command` in Terminal.
   - Windows: double-click `snek.bat`.
   - Linux: run `sh snek.command`.

The first start installs Snek's Python packages into a `.venv` folder inside the Snek folder, which takes about a minute. After that it starts in seconds. Your browser opens Snek; choose **File ▸ Open recent** and pick a sample.

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

| Category | Tools |
|---|---|
| In/Out | Input Data, Text Input, Output Data, Browse |
| Preparation | Select, Filter, Formula, Sort, Sample, Unique, Record ID, Data Cleansing, Find Replace |
| Join | Join (L/J/R outputs), Union, Append Fields |
| Parse | Text to Columns, Explode List, Unnest JSON |
| Transform | Summarize, Cross Tab, Transpose |
| Developer | Python (your own pandas code) |

Input Data reads CSV, TSV, Excel, JSON, JSON Lines and Parquet, gzipped CSV included. Put `*` in the path to stack many files into one table, for example `flights_2013_*.csv.gz`.

## Expressions

Filter and Formula take pandas expressions. Write a column as `[Column Name]`:

```
[pts] - [opp_pts]
iif([dep_delay] > 15, 'late', 'on time')
[Species].str.split(' ').str[0]
```

You can use `pd`, `np` and `iif(condition, then, else)`. Snek suggests a fix when a column name is misspelled.

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

```bash
.venv/bin/python -m pytest -q
cd frontend && npx tsc --noEmit && npm run build
```

For hot reload, run the server, then `npm run dev` in `frontend/` and open http://localhost:5173.

Each tool lives in `snek/tools/` as a class that returns pandas source code. The engine runs that code, and Export writes the same code, so the canvas and the script cannot drift apart. See [CLAUDE.md](CLAUDE.md) for the architecture notes.

## File picker shortcuts

The file picker lists Home, Examples, Workflows and Output. Add your own folders with the `SNEK_PLACES` environment variable:

```bash
SNEK_PLACES="Data=~/data;Downloads=~/Downloads" .venv/bin/python -m snek
```

## Caveats

- Formula and Python tools run any code you type. The server listens on 127.0.0.1 only. Do not expose it to a network.
- Data is held in memory. Hundreds of thousands of rows are fast; tens of millions will strain it.
- No undo/redo or copy/paste yet.

## License

MIT. See [LICENSE](LICENSE).
