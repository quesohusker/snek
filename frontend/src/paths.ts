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
