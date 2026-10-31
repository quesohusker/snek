import { useEffect, useState } from "react";
import { File, Folder, FolderOpen } from "lucide-react";
import Modal from "./Modal";
import { api } from "../api";
import type { FsListing } from "../types";

export type PickerMode = "open" | "save" | "folder";

function size(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(1)} GB`;
}

function dirname(p: string) {
  const i = p.lastIndexOf("/");
  return i > 0 ? p.slice(0, i) : p;
}

function basename(p: string) {
  return p.slice(p.lastIndexOf("/") + 1);
}

function toPattern(p: string) {
  const dir = dirname(p);
  const base = p.slice(dir.length + 1);
  const m = base.match(/^(.*?)(\d+)(\D*)$/);
  return m ? `${dir}/${m[1]}*${m[3]}` : `${dir}/*${base.includes(".") ? base.slice(base.lastIndexOf(".")) : ""}`;
}

const TITLES: Record<PickerMode, string> = { open: "Choose input file", save: "Choose where to save", folder: "Choose a folder" };

export default function FilePicker({ initial, mode, title, onPick, onClose }: { initial: string; mode: PickerMode; title?: string; onPick: (path: string) => void; onClose: () => void }) {
  const [listing, setListing] = useState<FsListing | null>(null);
  const [typed, setTyped] = useState(mode === "save" ? basename(initial) : initial);
  const [error, setError] = useState("");

  const open = (path: string) => {
    api
      .fs(path)
      .then((l) => {
        setListing(l);
        setError("");
        if (mode === "folder") setTyped(l.path);
      })
      .catch((e) => setError(String(e.message ?? e)));
  };

  useEffect(() => {
    open(mode === "folder" ? initial : initial ? dirname(initial) : "");
  }, [initial, mode]);

  const finish = (p: string) => {
    const bare = !p.includes("/") && !p.includes("\\") && !p.startsWith("~");
    onPick(bare && listing ? `${listing.path}/${p}` : p);
  };

  const placeholder = mode === "save" ? "File name, e.g. results.csv" : mode === "folder" ? "Folder path" : "Path or pattern with *";

  const footer = (
    <>
      {mode === "save" && listing && <span className="picker-into muted">Save in {basename(listing.path) || listing.path} as</span>}
      <input className="picker-path" value={typed} onChange={(e) => setTyped(e.target.value)} onKeyDown={(e) => e.key === "Enter" && typed && finish(typed)} placeholder={placeholder} />
      {mode === "open" && (
        <button onClick={() => typed && setTyped(toPattern(typed))} disabled={!typed} title="Replace the number in the file name with *">
          Make pattern
        </button>
      )}
      <button className="primary" disabled={!typed} onClick={() => finish(typed)}>
        {mode === "save" ? "Save here" : mode === "folder" ? "Open this folder" : "Select"}
      </button>
    </>
  );

  return (
    <Modal title={title ?? TITLES[mode]} onClose={onClose} footer={footer} wide>
      <div className="picker">
        <nav className="picker-places">
          {listing?.places.map((p) => (
            <button key={`${p.label}:${p.path}`} className={listing.path === p.path ? "active" : ""} onClick={() => open(p.path)} title={p.path}>
              <FolderOpen size={14} /> {p.label}
            </button>
          ))}
        </nav>
        <div className="picker-main">
          <div className="picker-crumb">
            <button onClick={() => listing && open(listing.parent)} disabled={!listing || listing.parent === listing.path}>
              ↑ Up
            </button>
            <code>{listing?.path}</code>
          </div>
          {error && <div className="error-box">{error}</div>}
          <ul className="picker-list">
            {listing?.entries.map((e) => {
              const pickable = e.dir || mode !== "folder";
              const active = mode === "save" ? typed === e.name : typed === e.path;
              return (
                <li
                  key={e.path}
                  className={`${active ? "active" : ""}${pickable ? "" : " disabled"}`}
                  onClick={() => (e.dir ? open(e.path) : mode === "save" ? setTyped(e.name) : mode === "open" && setTyped(e.path))}
                  onDoubleClick={() => !e.dir && mode !== "folder" && finish(mode === "save" ? e.name : e.path)}
                >
                  {e.dir ? <Folder size={14} /> : <File size={14} />}
                  <span className="name">{e.name}</span>
                  <span className="meta">{e.dir ? "" : size(e.size)}</span>
                  <span className="meta">{e.modified.replace("T", " ")}</span>
                </li>
              );
            })}
            {listing && !listing.entries.length && <li className="muted">This folder is empty.</li>}
          </ul>
        </div>
      </div>
    </Modal>
  );
}
