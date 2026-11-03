type Bridge = { postMessage: (message: unknown) => Promise<unknown> };

function bridge(): Bridge | null {
  const w = window as unknown as { webkit?: { messageHandlers?: { snek?: Bridge } } };
  return w.webkit?.messageHandlers?.snek ?? null;
}

export const hasNative = () => bridge() !== null;

export async function allowFolder(): Promise<string | null> {
  const reply = (await bridge()?.postMessage({ action: "allowFolder" })) as { path?: string | null } | undefined;
  return reply?.path ?? null;
}

const NORM = "com.quesohusker.norm";

export async function normAppNative(): Promise<boolean> {
  const b = bridge();
  if (!b) return false;
  try {
    const reply = (await b.postMessage({ action: "appPath", bundle: NORM })) as { path?: string | null } | undefined;
    return !!reply?.path;
  } catch {
    return false;
  }
}

export async function openInNormNative(path: string): Promise<boolean> {
  const b = bridge();
  if (!b) return false;
  try {
    const reply = (await b.postMessage({ action: "openWith", bundle: NORM, path })) as { ok?: boolean } | undefined;
    return !!reply?.ok;
  } catch {
    return false;
  }
}

export async function revealNative(path: string): Promise<boolean> {
  const b = bridge();
  if (!b) return false;
  await b.postMessage({ action: "reveal", path });
  return true;
}
