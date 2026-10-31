# Snek

A local, Alteryx-style workflow canvas. You drag tools onto a canvas, wire them, and each tool runs pandas code. Export Python turns the whole workflow into one standalone script.

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
- `snek/engine.py` topologically sorts the graph, generates each tool's code, and `exec`s it with the input frames bound to their variable names. Results cache by a hash of the code, the input hashes and the file stamps.
- `snek/runtime.py` holds the helpers the generated code calls (`read_any`, `write_any`, `join_lrj`, `unnest`, `iif`). Export copies their source into the script.
- `snek/expr.py` turns `[Column Name]` into `df['Column Name']` for Filter and Formula expressions.
- `snek/codegen.py` builds the exported script from the engine's generated code.
- `snek/projects.py` tracks the open project folder. Opening a project changes the server's working directory to it, so relative paths in generated code resolve inside the project. Config lives in `~/.snek/config.json` (`SNEK_HOME` overrides the folder, which tests use).
- `snek/server.py` is the FastAPI app. `/api/schema` dry-runs a tool to get its input columns and code. `/api/preview` runs up to a tool and returns a page of rows.
- `frontend/` is React + React Flow (`@xyflow/react`) + zustand, built with Vite. `src/commands.ts` defines the menus once; the top menu bar and the sidebar's Menu section both render from it. Add new commands there.
- Workflows are `.snek` files (JSON with `"format": "snek"`). Older `.flow.json` files still load and are converted when saved. `snek/settings.py` holds user settings (autosave interval and mode) in `~/.snek/settings.json`; autosave copies go to `~/.snek/autosave`.
- `workflows/*.snek` are the bundled sample workflows. `scripts/make_samples.py` regenerates the bundled samples.
- `examples/data/` holds the bundled CC0 datasets (Palmer Penguins, nycflights13 Q1). Sources and citations are in its README.

## Rules

- One source of truth. A tool's behavior lives only in `code()`. The engine runs that code and export writes that code. Never add a separate execution path, or the export drifts from the canvas.
- Tools must not mutate their inputs. Start in-place edits with `out = inp.copy()`. The engine passes shallow copies as a backstop.
- Every row-subsetting tool resets the index.
- Output tools have `side_effect = True`. They write only on Run, never on preview or schema calls.
- Add a golden test in `tests/test_tools.py` for every new tool or behavior change. `test_export_matches_engine` must keep passing.
- pandas is 3.x: strings default to the `str` dtype, Copy-on-Write is always on, and datetimes parse as `datetime64[us, ...]`.
- No comments in code.

## Releases

- The version lives in `snek/__init__.py` (`__version__`); `pyproject.toml` and the app bundle read it from there.
- To release: bump `__version__`, commit, push, then push a `vX.Y.Z` tag. `.github/workflows/release.yml` builds and smoke-tests the macOS, Windows and Linux apps and publishes them with the source zip. Rewrite the release notes afterward; the workflow posts a placeholder.
- `snek/updates.py` checks GitHub's releases API once a day, sends no user data, and can be turned off in Help.

## Data

- Bundle only openly licensed data (CC0 or similar) and record the source and license in `examples/data/README.md`.
- Sample paths are relative to the repo root, which is the built-in "Snek examples" project.
- Sample outputs go to `output/`, which git ignores.
