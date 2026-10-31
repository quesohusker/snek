# Snek

A local, Alteryx-style workflow canvas. You drag tools onto a canvas, wire them, and each tool runs pandas code. Export Python turns the whole workflow into one standalone script.

## Run it

- Double-click `snek.command`, or run `.venv/bin/python -m snek` from this folder. It serves on http://127.0.0.1:8765 and opens the browser.
- Frontend changes need a rebuild: `cd frontend && npm run build`. The server serves `frontend/dist`.
- Frontend dev with hot reload: start the server, then `cd frontend && npm run dev` (port 5173, proxies `/api`).
- Python changes need a server restart. There is no auto-reload.
- Tests: `.venv/bin/python -m pytest -q`. Typecheck: `cd frontend && npx tsc --noEmit`.

## Layout

- `snek/tools/` holds one module per palette category. Each tool is a class with `fields` (form spec), `inputs`/`outputs` (ports) and `code(cfg, ctx)`, which returns pandas source.
- `snek/engine.py` topologically sorts the graph, generates each tool's code, and `exec`s it with the input frames bound to their variable names. Results cache by a hash of the code, the input hashes and the file stamps.
- `snek/runtime.py` holds the helpers the generated code calls (`read_any`, `write_any`, `join_lrj`, `unnest`, `iif`). Export copies their source into the script.
- `snek/expr.py` turns `[Column Name]` into `df['Column Name']` for Filter and Formula expressions.
- `snek/codegen.py` builds the exported script from the engine's generated code.
- `snek/server.py` is the FastAPI app. `/api/schema` dry-runs a tool to get its input columns and code. `/api/preview` runs up to a tool and returns a page of rows.
- `frontend/` is React + React Flow (`@xyflow/react`) + zustand, built with Vite. `src/commands.ts` defines the menus once; the top menu bar and the sidebar's Menu section both render from it. Add new commands there.
- `workflows/*.flow.json` are saved workflows. `scripts/make_samples.py` regenerates the bundled samples.
- `examples/data/` holds the bundled CC0 datasets (Palmer Penguins, nycflights13 Q1). Sources and citations are in its README.

## Rules

- One source of truth. A tool's behavior lives only in `code()`. The engine runs that code and export writes that code. Never add a separate execution path, or the export drifts from the canvas.
- Tools must not mutate their inputs. Start in-place edits with `out = inp.copy()`. The engine passes shallow copies as a backstop.
- Every row-subsetting tool resets the index.
- Output tools have `side_effect = True`. They write only on Run, never on preview or schema calls.
- Add a golden test in `tests/test_tools.py` for every new tool or behavior change. `test_export_matches_engine` must keep passing.
- pandas is 3.x: strings default to the `str` dtype, Copy-on-Write is always on, and datetimes parse as `datetime64[us, ...]`.
- No comments in code.

## Data

- Bundle only openly licensed data (CC0 or similar) and record the source and license in `examples/data/README.md`.
- Sample paths are relative to the repo root. `python -m snek` changes into the repo root when it finds `examples/`.
- Sample outputs go to `output/`, which git ignores.
