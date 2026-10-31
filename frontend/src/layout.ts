import type { Edge } from "@xyflow/react";
import type { ToolNode } from "./store";
import type { ToolSpec } from "./types";

type Position = { x: number; y: number };
type Link = { source: string; target: string; out: number; in: number };
type Slot = { id: string; h: number; want: number | null; rel: number };
type Block = { slots: Slot[]; top: number; height: number; sum: number; weight: number };

const COLUMN_GAP = 110;
const ROW_GAP = 36;
const FLOW_GAP = 90;
const SWEEPS = 4;

function share(spec: ToolSpec | undefined, side: "inputs" | "outputs", handle: string | null | undefined) {
  const ports = spec?.[side] ?? [];
  const i = Math.max(0, ports.findIndex((p) => p.name === handle));
  return (i + 1) / (ports.length + 1);
}

function pack(slots: Slot[]): Map<string, number> {
  const blocks: Block[] = [];
  for (const slot of slots) {
    blocks.push({ slots: [{ ...slot, rel: 0 }], top: 0, height: slot.h, sum: slot.want ?? 0, weight: slot.want === null ? 0 : 1 });
    for (;;) {
      const b = blocks[blocks.length - 1];
      const prev = blocks[blocks.length - 2];
      const floor = prev ? prev.top + prev.height + ROW_GAP : 0;
      b.top = b.weight ? b.sum / b.weight : floor;
      if (!prev || b.top >= floor) break;
      const shift = prev.height + ROW_GAP;
      prev.slots.push(...b.slots.map((s) => ({ ...s, rel: s.rel + shift })));
      prev.sum += b.sum - b.weight * shift;
      prev.weight += b.weight;
      prev.height += ROW_GAP + b.height;
      blocks.pop();
    }
  }
  return new Map(blocks.flatMap((b) => b.slots.map((s) => [s.id, b.top + s.rel] as [string, number])));
}

function flows(nodes: ToolNode[], links: Link[]): ToolNode[][] {
  const root = new Map(nodes.map((n) => [n.id, n.id]));
  const find = (id: string): string => (root.get(id) === id ? id : find(root.get(id)!));
  for (const l of links) root.set(find(l.source), find(l.target));
  const groups = new Map<string, ToolNode[]>();
  for (const n of nodes) groups.set(find(n.id), [...(groups.get(find(n.id)) ?? []), n]);
  const top = (g: ToolNode[]) => Math.min(...g.map((n) => n.position.y));
  const left = (g: ToolNode[]) => Math.min(...g.map((n) => n.position.x));
  return [...groups.values()].sort((a, b) => top(a) - top(b) || left(a) - left(b));
}

function layoutFlow(nodes: ToolNode[], links: Link[]) {
  const size = new Map(nodes.map((n) => [n.id, { w: n.measured?.width ?? 196, h: n.measured?.height ?? 66 }]));
  const place = new Map(nodes.map((n) => [n.id, n.position]));
  const parents = (id: string, list: Link[]) => list.filter((l) => l.target === id);
  const children = (id: string, list: Link[]) => list.filter((l) => l.source === id);

  const waiting = new Map(nodes.map((n) => [n.id, parents(n.id, links).length]));
  const queue = nodes.filter((n) => !waiting.get(n.id)).map((n) => n.id);
  const order: string[] = [];
  while (queue.length) {
    const id = queue.shift()!;
    order.push(id);
    for (const l of children(id, links)) {
      waiting.set(l.target, waiting.get(l.target)! - 1);
      if (!waiting.get(l.target)) queue.push(l.target);
    }
  }
  for (const n of nodes) if (!order.includes(n.id)) order.push(n.id);

  const depth = new Map(order.map((id) => [id, 0]));
  for (const id of order) for (const l of children(id, links)) depth.set(l.target, Math.max(depth.get(l.target)!, depth.get(id)! + 1));
  for (const id of order) {
    const kids = children(id, links);
    if (!parents(id, links).length && kids.length) depth.set(id, Math.min(...kids.map((l) => depth.get(l.target)!)) - 1);
  }

  const segs: Link[] = [];
  links.forEach((l, i) => {
    let from = l.source;
    let out = l.out;
    for (let d = depth.get(l.source)! + 1; d < depth.get(l.target)!; d++) {
      const id = `~${i}.${d}`;
      depth.set(id, d);
      size.set(id, { w: 0, h: 0 });
      place.set(id, place.get(l.source)!);
      segs.push({ source: from, target: id, out, in: 0.5 });
      from = id;
      out = 0.5;
    }
    segs.push({ source: from, target: l.target, out, in: l.in });
  });
  const ids = [...depth.keys()];
  const ins = new Map(ids.map((id) => [id, parents(id, segs)]));
  const outs = new Map(ids.map((id) => [id, children(id, segs)]));

  const columns: string[][] = [];
  const byPlace = [...ids].sort((a, b) => place.get(a)!.y - place.get(b)!.y || place.get(a)!.x - place.get(b)!.x);
  for (const id of byPlace) (columns[depth.get(id)!] ??= []).push(id);
  for (let d = 0; d < columns.length; d++) columns[d] ??= [];

  const rank = new Map<string, number>();
  const ranked = () => columns.forEach((col) => col.forEach((id, i) => rank.set(id, i)));
  const reorder = (col: string[], near: (id: string) => number[]) => {
    const score = new Map(col.map((id) => {
      const vals = near(id);
      return [id, vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : rank.get(id)!];
    }));
    col.sort((a, b) => score.get(a)! - score.get(b)! || rank.get(a)! - rank.get(b)!);
  };
  ranked();
  for (let i = 0; i < SWEEPS; i++) {
    for (let d = 1; d < columns.length; d++) reorder(columns[d], (id) => ins.get(id)!.map((l) => rank.get(l.source)! + l.out));
    ranked();
    for (let d = columns.length - 2; d >= 0; d--) reorder(columns[d], (id) => outs.get(id)!.map((l) => rank.get(l.target)! + l.in));
    ranked();
  }

  const y = new Map<string, number>();
  const h = (id: string) => size.get(id)!.h;
  const mean = (vals: number[]) => (vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null);
  for (const col of columns) {
    const placed = pack(col.map((id) => ({ id, h: h(id), rel: 0, want: mean(ins.get(id)!.filter((l) => y.has(l.source)).map((l) => y.get(l.source)! + l.out * h(l.source) - l.in * h(id))) })));
    placed.forEach((v, id) => y.set(id, v));
  }
  for (let d = columns.length - 2; d >= 0; d--) {
    const col = columns[d];
    if (!col.some((id) => !ins.get(id)!.length && outs.get(id)!.length)) continue;
    const placed = pack(col.map((id) => ({ id, h: h(id), rel: 0, want: ins.get(id)!.length ? y.get(id)! : mean(outs.get(id)!.map((l) => y.get(l.target)! + l.in * h(l.target) - l.out * h(id))) })));
    placed.forEach((v, id) => y.set(id, v));
  }

  const x: number[] = [];
  columns.forEach((col, d) => (x[d] = d ? x[d - 1] + Math.max(196, ...columns[d - 1].map((id) => size.get(id)!.w)) + COLUMN_GAP : 0));
  const top = Math.min(...nodes.map((n) => y.get(n.id)!));
  const bottom = Math.max(...nodes.map((n) => y.get(n.id)! + h(n.id))) - top;
  return { at: new Map(nodes.map((n) => [n.id, { x: x[depth.get(n.id)!], y: y.get(n.id)! - top }])), height: bottom };
}

export function cleanLayout(nodes: ToolNode[], edges: Edge[], tools: Record<string, ToolSpec>): Record<string, Position> {
  if (!nodes.length) return {};
  const type = new Map(nodes.map((n) => [n.id, n.data.type]));
  const links: Link[] = edges
    .filter((e) => type.has(e.source) && type.has(e.target))
    .map((e) => ({ source: e.source, target: e.target, out: share(tools[type.get(e.source)!], "outputs", e.sourceHandle), in: share(tools[type.get(e.target)!], "inputs", e.targetHandle) }));
  const left = Math.min(...nodes.map((n) => n.position.x));
  let top = Math.min(...nodes.map((n) => n.position.y));
  const result: Record<string, Position> = {};
  for (const flow of flows(nodes, links)) {
    const ids = new Set(flow.map((n) => n.id));
    const { at, height } = layoutFlow(flow, links.filter((l) => ids.has(l.source)));
    at.forEach((p, id) => (result[id] = { x: Math.round(left + p.x), y: Math.round(top + p.y) }));
    top += height + FLOW_GAP;
  }
  return result;
}
