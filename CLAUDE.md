# Snek

A local workflow canvas for pandas. You drag tools onto a canvas, wire them, and each tool runs pandas code. Export Python turns the whole workflow into one standalone script.

## Run it

- Double-click `snek.command`, or run `.venv/bin/python -m snek` from this folder. It serves on http://127.0.0.1:8765 and opens the browser.
- Frontend changes need a rebuild: `cd frontend && npm run build`. The server serves `frontend/dist`.
- Frontend dev with hot reload: start the server, then `cd frontend && npm run dev` (port 5173, proxies `/api`).
- Python changes need a server restart. There is no auto-reload.
- Tests: `.venv/bin/python -m pytest -q`. Typecheck: `cd frontend && npx tsc --noEmit`.
- Build the standalone app for this OS: `.venv/bin/pip install pyinstaller pillow`, then `.venv/bin/python packaging/build.py`, then `.venv/bin/python packaging/smoke_test.py packaging/dist/Snek.app/Contents/MacOS/Snek` (on Windows `packaging/dist/Snek/Snek.exe`, on Linux `packaging/dist/Snek/Snek`). The build regenerates THIRD_PARTY_NOTICES.md first.
- These developer notes live here, not in the README: the PolyForm Strict license does not let others change the code, so the README covers only using and building Snek.

## Layout

- `snek/modeling.py` holds the model helpers (scikit-learn, statsmodels). Model tools pass the fitted model between tools as a one-row DataFrame (Model, Algorithm, Task, Target, Features, Columns), so the engine still only moves DataFrames. `score_model` knows how to apply each algorithm.
- `snek/tools/` holds one module per palette category. Each tool is a class with `fields` (form spec), `inputs`/`outputs` (ports) and `code(cfg, ctx)`, which returns pandas source.
- Every tool sets `needs`: one or two sentences on the input it expects. The hover card and the Configure tab show it. Set `group` to nest tools inside a category; the sidebar shows each group as a collapsible section. Sports helpers live in `snek/sports_math.py`.
- Every store action that changes nodes or edges calls `checkpoint(label, key)` first; that is what undo and redo replay. Typing in one field coalesces into one step by key. Clipboard data is JSON with `format: "snek-clipboard"` (`frontend/src/editing.ts`).
- Data Connections helpers live in `snek/connect.py`. API keys live in `~/.snek/connections.json` (mode 600) and never enter workflows or exports. Tests use a local fake API, never a real one. The GitHub tool calls `connect.github` (read-only); its token is declared with `host=api.github.com`, and `tests/test_github.py` reroutes `urllib.request.urlopen` to a local fake.
- Add-ons are separate Python packages that declare a `snek.plugins` entry point. On import they call `snek.tools.add_category`, `snek.runtime.register_helper` and `register` for their tools; tools may set `icon` and `color`. `snek/plugins.py` loads them. A packaged build includes an add-on only when `SNEK_BUNDLE_PLUGINS` names its distribution, and the add-on must be installed normally (not editable) for PyInstaller to find it. `SNEK_MIN_TOOLS` raises the smoke test's tool-count floor for such builds. Keep add-on code out of this repo.
- Create with AI lives in `snek/ai.py` and uses the official `anthropic` SDK: Claude Opus 5.5 by default, structured JSON output, a cached system prompt holding the tool catalog, server-side refusal fallback, and up to two repair rounds fed by a real engine run. Tests use a fake client.
- `snek/distributions.py` holds the distribution catalog (`FAMILIES`), `draw_values`, `random_data` and `fit_distribution` (scipy). Fits and draws share one parameter convention so a fit can feed Random Data. `snek/simulation.py` is the discrete-event engine (`Sim`, a heap-based event loop; `simulate_process`, `make_arrivals`). `snek/inference.py` holds `inference_summary` for Summary Statistics. Their tools are in `snek/tools/simulate.py` and `snek/tools/investigate.py`. Helper functions that export copies must reference only each other, numpy, pandas and the modules named in `HELPERS`; shared constants go through the `constants` map in `snek/codegen.py`.
- A `Port` can be `optional=True`. The engine then skips it when nothing is connected, and `code()` reads `ctx.ins.get(name)` instead of `ctx.var(name)`.
- `snek/health.py` checks that the needed packages are installed. `python -m snek --check [quick]`, `/api/health` and the launchers use it. `PACKAGES` must list every dependency in `pyproject.toml` (a test checks this).
- Charts are Vega-Lite specs in a one-row frame (`Vega-Lite` column) from `snek/charts.py`. The results panel renders them with vega-embed, loaded on demand; Output Data writes them as HTML.
- `snek/engine.py` topologically sorts the graph, generates each tool's code, and `exec`s it with the input frames bound to their variable names. Results cache by a hash of the code, the input hashes and the file stamps.
- `snek/runtime.py` holds the helpers the generated code calls (`read_any`, `write_any`, `join_lrj`, `unnest`, `iif`). Export copies their source into the script.
- `snek/fx.py` holds the spreadsheet functions: 311 uppercase functions (`IF`, `TEXT`, `SUMIF`, `NORM.DIST`, `PMT` and so on, plus 39 old Excel names written as one-line wrappers) that work on a column or a single value. Summary functions read a whole column through `_values` (text, blanks and True/False in a mixed column are skipped; a pure True/False column counts as 1 and 0). The distribution functions import scipy inside `_sp()`, and `registry()` lists scipy as a package for export. `_each` runs a Python function over each row and turns blanks and errors into NaN; `_vec` does the same for numpy math. `FUNCTIONS` lists them and `registry()` builds the `HELPERS` entries from each function's bytecode, so export copies exactly the functions and helpers a workflow uses. Keep them free of module-level data and use only `math`, `re`, `decimal`, numpy and pandas. `snek/fx_docs.py` holds the catalog (syntax, plain description, example and its result); `tests/test_fx.py` runs every example. `tests/data/excel_fx.json` and `tests/data/excel_fx_ranges.json` (formulas over a small data sheet, stored in the file) hold answers from real Excel for about 2,500 formulas; `tests/test_fx_excel.py` checks them, and each file's `known_differences` explains each place Snek chooses to differ. To add a function: write it in `fx.py`, add its row to `fx_docs.py`, add Excel cases and refresh the fixture from Excel.
- `snek/geo.py` holds the map helpers: `distance_between`, `find_nearest` (scikit-learn BallTree, haversine), `geocode_addresses` (US Census batch geocoder, one POST per 1,000 rows), `read_map_file` (pyshp for shapefiles, json for GeoJSON; no shapely, so no GEOS), `find_region` (numpy ray casting with a bounding-box filter) and `map_chart` (Vega-Lite layers on `vega-datasets@2.11.0` TopoJSON loaded from jsdelivr). Distance, bearing and the state table live in `fx.py` so the functions and the tools share them. Tools are in `snek/tools/maps.py`; `map_values` is in `runtime.py`. Geometry travels between tools as GeoJSON text in a `geometry` column, since tools pass only DataFrames. Geocoding sends addresses off the Mac; tests patch `urllib.request.urlopen`.
- `snek/expr.py` turns `[Column Name]` into `df['Column Name']` for Filter and Formula expressions. It also rewrites dotted function names (`CEILING.MATH` to `CEILING_MATH`), bare `TRUE` and `FALSE`, and `<>`.
- `snek/codegen.py` builds the exported script and notebook from the engine's generated code (`export_steps`, `script_text`, `notebook_text`). The Create Python tool sets `needs_upstream`: the engine gives its `code()` the ordered steps of everything upstream (`ctx.upstream`) and binds them as `workflow_steps` when the code runs. It sets `exportable = False`, so exports leave it out.
- `snek/projects.py` tracks the open project folder. Opening a project changes the server's working directory to it, so relative paths in generated code resolve inside the project. Config lives in `~/.snek/config.json` (`SNEK_HOME` overrides the folder, which tests use).
- `snek/server.py` is the FastAPI app. `/api/schema` dry-runs a tool to get its input columns and code. `/api/preview` runs up to a tool and returns a page of rows. The `LocalOnly` middleware rejects any request whose Host is not loopback and any `/api` request whose Origin or Sec-Fetch-Site is foreign, so pages on other sites cannot drive the server.
- The sidebar's Favorites section keeps tool types in `localStorage` (`snek.favorites`); `POPULAR_TOOLS` in `store.ts` is the starting set.
- `frontend/` is React + React Flow (`@xyflow/react`) + zustand, built with Vite. `src/commands.ts` defines the menus once; the top menu bar and the sidebar's Menu section both render from it. Add new commands there.
- Workflows are `.snek` files (JSON with `"format": "snek"`). Older `.flow.json` files still load and are converted when saved. `snek/settings.py` holds user settings (autosave interval and mode) in `~/.snek/settings.json`; autosave copies go to `~/.snek/autosave`.
- `workflows/*.snek` are the bundled sample workflows. `scripts/make_samples.py` regenerates the bundled samples.
- `examples/data/` holds the bundled CC0 datasets (Palmer Penguins, nycflights13 Q1). Sources and citations are in its README.

## Rules

- One source of truth. A tool's behavior lives only in `code()`. The engine runs that code and export writes that code. Never add a separate execution path, or the export drifts from the canvas.
- Tools must not mutate their inputs. Start in-place edits with `out = inp.copy()`. The engine passes shallow copies as a backstop.
- Every row-subsetting tool resets the index.
- Output tools have `side_effect = True`. They write only on Run, never on preview or schema calls.
- Tools that run user-written code set `needs_trust = True`. Outside Run, the engine runs such a step only when its node carries `trusted: true`. The frontend sets the flag on steps the user adds or edits and on every step when Run is pressed; the server clears it on everything read from disk and strips it on save, and AI drafts start without it.
- Add a golden test in `tests/test_tools.py` for every new tool or behavior change. `test_export_matches_engine` must keep passing.
- pandas is 3.x: strings default to the `str` dtype, Copy-on-Write is always on, and datetimes parse as `datetime64[us, ...]`.
- No comments in code.

## Releases

- The version lives in `snek/__init__.py` (`__version__`); `pyproject.toml` and the app bundle read it from there.
- To release: bump `__version__`, commit, push, then push a `vX.Y.Z` tag. `.github/workflows/release.yml` builds and smoke-tests the macOS, Windows and Linux apps and publishes them with the source zip and a `SHA256SUMS.txt`. Rewrite the release notes afterward; the workflow posts a placeholder.
- Python packages for the builds and the test job come from `packaging/requirements.lock`, pinned with hashes. When a dependency changes, regenerate it with the `uv pip compile` command in its header, then run the suite from a fresh venv made from the lock.
- `snek/updates.py` checks GitHub's releases API once a day, sends no user data, and can be turned off in Help.

## Data

- Bundle only openly licensed data (CC0 or similar) and record the source and license in `examples/data/README.md`.
- Sample paths are relative to the repo root, which is the built-in "Snek examples" project.
- Sample outputs go to `output/`, which git ignores.
