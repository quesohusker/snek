export function separator(path: string) {
  return path.includes("\\") && !path.includes("/") ? "\\" : "/";
}

export function dirname(path: string) {
  const i = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  if (i < 0) return path;
  if (i === 0) return path.slice(0, 1);
  if (i === 2 && path[1] === ":") return path.slice(0, 3);
  return path.slice(0, i);
}

export function basename(path: string) {
  return path.slice(Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\")) + 1);
}

export function joinPath(dir: string, name: string) {
  const sep = separator(dir);
  return dir.endsWith("/") || dir.endsWith("\\") ? `${dir}${name}` : `${dir}${sep}${name}`;
}

export function isBareName(path: string) {
  return !path.includes("/") && !path.includes("\\") && !path.startsWith("~");
}

const ua = typeof navigator === "undefined" ? "" : navigator.userAgent;

export const FILE_MANAGER = ua.includes("Mac") ? "Finder" : ua.includes("Win") ? "Explorer" : "file manager";

export const IS_MAC = ua.includes("Mac");

export function keyLabel(combo: string) {
  const plus = combo.endsWith("++");
  const parts = combo.split("+");
  const key = plus ? "+" : parts[parts.length - 1];
  const mods = new Set(parts.slice(0, plus ? -2 : -1));
  if (IS_MAC) return `${mods.has("shift") ? "⇧" : ""}${mods.has("alt") ? "⌥" : ""}${mods.has("mod") ? "⌘" : ""}${key}`;
  return [...(mods.has("mod") ? ["Ctrl"] : []), ...(mods.has("shift") ? ["Shift"] : []), ...(mods.has("alt") ? ["Alt"] : []), key].join("+");
}
