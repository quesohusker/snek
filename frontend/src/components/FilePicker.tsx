import { useEffect, useState } from "react";
import { File, Folder, FolderOpen } from "lucide-react";
import Modal from "./Modal";
import { api } from "../api";
import type { FsListing } from "../types";

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

function toPattern(p: string) {
  const dir = dirname(p);
  const base = p.slice(dir.length + 1);
  const m = base.match(/^(.*?)(\d+)(\D*)$/);
  return m ? `${dir}/${m[1]}*${m[3]}` : `${dir}/*${base.includes(".") ? base.slice(base.lastIndexOf(".")) : ""}`;
}

export default function FilePicker({ initial, save, onPick, onClose }: { initial: string; save?: boolean; onPick: (path: string) => void; onClose: () => void }) {
  const [listing, setListing] = useState<FsListing | null>(null);
  const [typed, setTyped] = useState(initial);
  const [error, setError] = useState("");

  const open = (path: string) => {
    api
      .fs(path)
      .then((l) => {
        setListing(l);
        setError("");
      })
      .catch((e) => setError(String(e.message ?? e)));
  };

  useEffect(() => {
    open(initial ? dirname(initial) : "");
  }, [initial]);

  const footer = (
    <>
      <input className="picker-path" value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={save ? "Folder and file name" : "Path or pattern with *"} />
      {!save && (
        <button onClick={() => typed && setTyped(toPattern(typed))} disabled={!typed} title="Replace the number in the file name with *">
          Make pattern
        </button>
      )}
      <button className="primary" disabled={!typed} onClick={() => onPick(typed)}>
        {save ? "Use this file" : "Select"}
      </button>
    </>
  );

  return (
    <Modal title={save ? "Choose output file" : "Choose input file"} onClose={onClose} footer={footer} wide>
      <div className="picker">
        <nav className="picker-places">
          {listing?.places.map((p) => (
            <button key={p.path} onClick={() => open(p.path)}>
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
            {listing?.entries.map((e) => (
              <li
                key={e.path}
                className={typed === e.path ? "active" : ""}
                onClick={() => (e.dir ? open(e.path) : setTyped(e.path))}
                onDoubleClick={() => !e.dir && onPick(e.path)}
              >
                {e.dir ? <Folder size={14} /> : <File size={14} />}
                <span className="name">{e.name}</span>
                <span className="meta">{e.dir ? "" : size(e.size)}</span>
                <span className="meta">{e.modified.replace("T", " ")}</span>
              </li>
            ))}
            {save && listing && (
              <li className="picker-new" onClick={() => setTyped(`${listing.path}/output.csv`)}>
                + New file in this folder
              </li>
            )}
          </ul>
        </div>
      </div>
    </Modal>
  );
}
