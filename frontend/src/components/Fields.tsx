import { useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUp, FolderOpen, Plus, Trash2 } from "lucide-react";
import FilePicker from "./FilePicker";
import { api } from "../api";
import { useFlow } from "../store";
import { FILE_MANAGER, basename, joinPath } from "../paths";
import type { Column, FieldSpec } from "../types";

export type FieldCtx = { columns: (port?: string) => Column[] };

export function shortType(dtype: string) {
  if (dtype.startsWith("datetime64")) return "date";
  if (dtype === "str" || dtype.startsWith("string")) return "text";
  if (dtype === "object") return "obj";
  return dtype.replace("float64", "float").replace("int64", "int").replace("Int64", "int?").replace("boolean", "bool?");
}

export function visible(field: FieldSpec, config: Record<string, any>) {
  if (!field.show_if) return true;
  return Object.entries(field.show_if).every(([k, vals]) => vals.includes(String(config[k] ?? "")));
}

type Props = { field: FieldSpec; value: any; config: Record<string, any>; onChange: (v: any) => void; onPatch?: (patch: Record<string, any>) => void; ctx: FieldCtx };

export function Field(props: Props) {
  const { field, config } = props;
  if (!visible(field, config)) return null;
  if (field.kind === "bool") {
    return (
      <label className="field field-bool">
        <input type="checkbox" checked={!!props.value} onChange={(e) => props.onChange(e.target.checked)} />
        <span>{field.label}</span>
        {field.help && <span className="help inline">{field.help}</span>}
      </label>
    );
  }
  return (
    <div className="field">
      <label>{field.label}</label>
      <Widget {...props} />
      {field.help && <div className="help">{field.help}</div>}
    </div>
  );
}

function Widget(props: Props) {
  const { field, value, onChange, ctx } = props;
  switch (field.kind) {
    case "number":
      return <input type="number" value={value ?? ""} onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))} />;
    case "select":
      return (
        <select value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
          {field.options?.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      );
    case "textarea":
      return <textarea className="mono" rows={8} value={value ?? ""} onChange={(e) => onChange(e.target.value)} spellCheck={false} />;
    case "code":
    case "python":
      return <CodeField {...props} />;
    case "file":
      return <FileField value={value ?? ""} onChange={onChange} save={!!field.save} fmt={String(props.config.format ?? "auto")} />;
    case "column":
      return <ColumnSelect value={value ?? ""} onChange={onChange} columns={ctx.columns(field.port)} />;
    case "columns":
      return <ColumnsMulti value={value ?? []} onChange={onChange} columns={ctx.columns(field.port)} />;
    case "multi_select":
      return <OptionChecks value={value ?? []} onChange={onChange} options={field.options ?? []} />;
    case "list":
      return <ListField {...props} />;
    case "select_fields":
      return <SelectFields {...props} />;
    default:
      return <input type="text" value={value ?? ""} placeholder={field.placeholder} onChange={(e) => onChange(e.target.value)} />;
  }
}

function CodeField({ field, value, onChange, ctx }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const python = field.kind === "python";
  const cols = ctx.columns("in");
  const insert = (name: string) => {
    const el = ref.current;
    const text = python ? `df[${JSON.stringify(name)}]` : `[${name}]`;
    const cur = value ?? "";
    const start = el?.selectionStart ?? cur.length;
    const end = el?.selectionEnd ?? cur.length;
    onChange(cur.slice(0, start) + text + cur.slice(end));
    requestAnimationFrame(() => {
      if (!el) return;
      el.focus();
      el.selectionStart = el.selectionEnd = start + text.length;
    });
  };
  return (
    <>
      <textarea ref={ref} className="mono" rows={python ? 14 : 3} value={value ?? ""} onChange={(e) => onChange(e.target.value)} spellCheck={false} placeholder={field.placeholder} />
      {cols.length > 0 && (
        <div className="chips" title="Click to insert">
          {cols.slice(0, 200).map((c) => (
            <button key={c.name} type="button" className="chip" onClick={() => insert(c.name)}>
              {c.name}
            </button>
          ))}
        </div>
      )}
    </>
  );
}

const QUICK_SAVE = ["Project output", "Desktop", "Documents", "Downloads"];

function FileField({ value, onChange, save, fmt }: { value: string; onChange: (v: string) => void; save: boolean; fmt: string }) {
  const [open, setOpen] = useState(false);
  const [resolved, setResolved] = useState<{ path: string; exists: boolean; folder_exists: boolean } | null>(null);
  const lastRun = useFlow((s) => s.lastRun);
  const places = useFlow((s) => s.project?.places ?? []);
  const quick = QUICK_SAVE.map((label) => places.find((p) => p.label === label)).filter((p): p is { label: string; path: string } => !!p);

  useEffect(() => {
    if (!save || !value.trim()) {
      setResolved(null);
      return;
    }
    const t = setTimeout(() => {
      api
        .resolve(value, fmt)
        .then(setResolved)
        .catch(() => setResolved(null));
    }, 250);
    return () => clearTimeout(t);
  }, [save, value, fmt, lastRun]);

  const saveIn = (dir: string) => onChange(joinPath(dir, basename(value.trim()) || "results.csv"));

  return (
    <>
      <div className="file-field">
        <input type="text" value={value} onChange={(e) => onChange(e.target.value)} placeholder={save ? "results.csv" : "~/path/file.csv or …/*.json"} spellCheck={false} />
        <button type="button" className="icon-btn" onClick={() => setOpen(true)} title="Browse">
          <FolderOpen size={16} />
        </button>
      </div>
      {save && quick.length > 0 && (
        <div className="quick-save">
          <span className="muted">Save in</span>
          {quick.map((p) => (
            <button key={p.label} type="button" className="chip" onClick={() => saveIn(p.path)} title={p.path}>
              {p.label}
            </button>
          ))}
        </div>
      )}
      {resolved && (
        <div className="resolved">
          <span className="muted">Saves to</span>
          <code title={resolved.path}>{resolved.path}</code>
          {!resolved.folder_exists && <span className="muted">The folder will be created.</span>}
          {resolved.exists && (
            <button type="button" className="link-btn" onClick={() => api.reveal(resolved.path)}>
              Show in {FILE_MANAGER}
            </button>
          )}
        </div>
      )}
      {open && (
        <FilePicker
          initial={value}
          mode={save ? "save" : "open"}
          onClose={() => setOpen(false)}
          onPick={(p) => {
            onChange(p);
            setOpen(false);
          }}
        />
      )}
    </>
  );
}

export function ColumnSelect({ value, onChange, columns }: { value: string; onChange: (v: string) => void; columns: Column[] }) {
  const names = columns.map((c) => c.name);
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} className={value && !names.includes(value) && names.length ? "missing" : ""}>
      <option value="">— pick a column —</option>
      {value && !names.includes(value) && <option value={value}>{value} (not in input)</option>}
      {columns.map((c) => (
        <option key={c.name} value={c.name}>
          {c.name} · {shortType(c.dtype)}
        </option>
      ))}
    </select>
  );
}

function ColumnsMulti({ value, onChange, columns }: { value: string[]; onChange: (v: string[]) => void; columns: Column[] }) {
  const [q, setQ] = useState("");
  const chosen = new Set(value);
  const names = columns.map((c) => c.name);
  const missing = value.filter((v) => !names.includes(v));
  const shown = columns.filter((c) => !q || c.name.toLowerCase().includes(q.toLowerCase()));
  const toggle = (name: string) => {
    const next = new Set(chosen);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    onChange([...names.filter((n) => next.has(n)), ...missing.filter((m) => next.has(m))]);
  };
  return (
    <div className="multi">
      <div className="multi-bar">
        <input placeholder="Filter" value={q} onChange={(e) => setQ(e.target.value)} />
        <span className="multi-count">{value.length} picked</span>
        <button type="button" onClick={() => onChange([...new Set([...value, ...shown.map((c) => c.name)])])}>
          All
        </button>
        <button type="button" onClick={() => onChange([])}>
          None
        </button>
      </div>
      <div className="multi-list">
        {missing.map((m) => (
          <label key={m} className="missing">
            <input type="checkbox" checked onChange={() => toggle(m)} /> {m} <em>not in input</em>
          </label>
        ))}
        {shown.map((c) => (
          <label key={c.name}>
            <input type="checkbox" aria-label={c.name} checked={chosen.has(c.name)} onChange={() => toggle(c.name)} /> {c.name}
            <em>{shortType(c.dtype)}</em>
          </label>
        ))}
        {columns.length === 0 && <div className="muted">Connect and configure the input first.</div>}
      </div>
    </div>
  );
}

function OptionChecks({ value, onChange, options }: { value: string[]; onChange: (v: string[]) => void; options: { value: string; label: string }[] }) {
  const chosen = new Set(value);
  return (
    <div className="option-checks">
      {options.map((o) => (
        <label key={o.value}>
          <input
            type="checkbox"
            checked={chosen.has(o.value)}
            onChange={() => onChange(options.map((x) => x.value).filter((v) => (v === o.value ? !chosen.has(v) : chosen.has(v))))}
          />
          {o.label}
        </label>
      ))}
    </div>
  );
}

function ListField({ field, value, onChange, ctx }: Props) {
  const items: Record<string, any>[] = Array.isArray(value) ? value : [];
  const sub = field.fields ?? [];
  const blank = () => Object.fromEntries(sub.map((f) => [f.key, structuredClone(f.default)]));
  const setItem = (i: number, patch: Record<string, any>) => onChange(items.map((it, j) => (j === i ? { ...it, ...patch } : it)));
  const move = (i: number, d: number) => {
    const next = [...items];
    const [it] = next.splice(i, 1);
    next.splice(i + d, 0, it);
    onChange(next);
  };
  const compact = sub.every((f) => f.kind !== "code");
  return (
    <div className="list-field">
      {items.map((item, i) => (
        <div key={i} className={`list-item${compact ? " compact" : ""}`}>
          <div className="list-item-fields" style={compact ? { gridTemplateColumns: `repeat(${sub.length}, minmax(0, 1fr))` } : undefined}>
            {sub.map((f) => (
              <Field key={f.key} field={f} value={item[f.key] ?? f.default} config={{ ...blank(), ...item }} onChange={(v) => setItem(i, { [f.key]: v })} ctx={ctx} />
            ))}
          </div>
          <div className="list-item-actions">
            <button type="button" className="icon-btn" disabled={i === 0} onClick={() => move(i, -1)} title="Move up">
              <ArrowUp size={14} />
            </button>
            <button type="button" className="icon-btn" disabled={i === items.length - 1} onClick={() => move(i, 1)} title="Move down">
              <ArrowDown size={14} />
            </button>
            <button type="button" className="icon-btn" onClick={() => onChange(items.filter((_, j) => j !== i))} title="Remove">
              <Trash2 size={14} />
            </button>
          </div>
        </div>
      ))}
      <button type="button" className="add-btn" onClick={() => onChange([...items, blank()])}>
        <Plus size={14} /> Add
      </button>
    </div>
  );
}

type SelectRow = { name: string; keep: boolean; rename: string; dtype: string };

function SelectFields({ field, value, config, onChange, ctx }: Props) {
  const [q, setQ] = useState("");
  const cols = ctx.columns("in");
  const listed: SelectRow[] = Array.isArray(value) ? value : [];
  const present = new Set(cols.map((c) => c.name));
  const byName = new Map(listed.map((f) => [f.name, f]));
  const keepNew = config.keep_new !== false;
  const rows: SelectRow[] = [
    ...listed.filter((f) => present.has(f.name)),
    ...cols.filter((c) => !byName.has(c.name)).map((c) => ({ name: c.name, keep: keepNew, rename: "", dtype: "" })),
  ];
  const missing = listed.filter((f) => !present.has(f.name));
  const dtypeOf = new Map(cols.map((c) => [c.name, c.dtype]));
  const commit = (next: SelectRow[]) => onChange([...next, ...missing]);
  const update = (name: string, patch: Partial<SelectRow>) => commit(rows.map((r) => (r.name === name ? { ...r, ...patch } : r)));
  const move = (i: number, d: number) => {
    const next = [...rows];
    const [r] = next.splice(i, 1);
    next.splice(i + d, 0, r);
    commit(next);
  };
  const shown = rows.map((r, i) => ({ r, i })).filter(({ r }) => !q || r.name.toLowerCase().includes(q.toLowerCase()));
  if (!cols.length) return <div className="muted">Connect and configure the input first.</div>;
  return (
    <div className="select-fields">
      <div className="multi-bar">
        <input placeholder="Filter" value={q} onChange={(e) => setQ(e.target.value)} />
        <span className="multi-count">
          {rows.filter((r) => r.keep).length}/{rows.length} kept
        </span>
        <button type="button" onClick={() => commit(rows.map((r) => ({ ...r, keep: true })))}>
          All
        </button>
        <button type="button" onClick={() => commit(rows.map((r) => ({ ...r, keep: false })))}>
          None
        </button>
      </div>
      <div className="select-table">
        {shown.map(({ r, i }) => (
          <div key={r.name} className={`select-row${r.keep ? "" : " dropped"}`}>
            <input type="checkbox" aria-label={`Keep ${r.name}`} checked={r.keep} onChange={(e) => update(r.name, { keep: e.target.checked })} />
            <span className="select-name" title={`${r.name} · ${dtypeOf.get(r.name)}`}>
              {r.name}
              <em>{shortType(dtypeOf.get(r.name) ?? "")}</em>
            </span>
            <select value={r.dtype} onChange={(e) => update(r.name, { dtype: e.target.value })}>
              {field.dtypes?.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
            <input type="text" placeholder="rename" value={r.rename} onChange={(e) => update(r.name, { rename: e.target.value })} />
            <span className="select-move">
              <button type="button" className="icon-btn" disabled={i === 0} onClick={() => move(i, -1)}>
                <ArrowUp size={12} />
              </button>
              <button type="button" className="icon-btn" disabled={i === rows.length - 1} onClick={() => move(i, 1)}>
                <ArrowDown size={12} />
              </button>
            </span>
          </div>
        ))}
        {missing.map((r) => (
          <div key={r.name} className="select-row missing">
            <span />
            <span className="select-name">
              {r.name} <em>not in input</em>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
