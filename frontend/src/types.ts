export type Option = { value: string; label: string };

export type FieldSpec = {
  key: string;
  label: string;
  kind: string;
  default: any;
  options?: Option[];
  help?: string;
  placeholder?: string;
  show_if?: Record<string, string[]>;
  port?: string;
  fields?: FieldSpec[];
  dtypes?: Option[];
  save?: boolean;
};

export type PortSpec = { name: string; label: string; multi: boolean };

export type ToolSpec = {
  type: string;
  label: string;
  category: string;
  description: string;
  inputs: PortSpec[];
  outputs: PortSpec[];
  fields: FieldSpec[];
};

export type Column = {
  name: string;
  dtype: string;
  nulls?: number;
  unique?: number | null;
  min?: any;
  max?: any;
  mean?: any;
  top?: any;
  top_count?: number;
};

export type PortInfo = { rows: number; columns: Column[]; count?: number };

export type NodeResult = {
  status: "ok" | "error" | "skipped";
  error: string;
  message: string;
  warnings: string[];
  code: string;
  elapsed_ms: number;
  cached: boolean;
  executed: boolean;
  inputs: Record<string, PortInfo>;
  outputs: Record<string, PortInfo>;
};

export type PreviewData = {
  total: number;
  offset: number;
  limit: number;
  columns: Column[];
  rows: any[][];
};

export type FlowNodeData = {
  type: string;
  label: string;
  config: Record<string, any>;
};

export type WorkflowNode = {
  id: string;
  type: string;
  label?: string;
  position: { x: number; y: number };
  config: Record<string, any>;
};

export type WorkflowEdge = {
  id: string;
  source: string;
  sourceHandle: string;
  target: string;
  targetHandle: string;
};

export type WorkflowFile = {
  version: number;
  name?: string;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
};

export type FsEntry = { name: string; path: string; dir: boolean; size: number; modified: string };

export type FsListing = {
  path: string;
  parent: string;
  entries: FsEntry[];
  places: Place[];
};

export type Place = { label: string; path: string };

export type ProjectInfo = {
  path: string;
  name: string;
  is_examples: boolean;
  workflows: string;
  recent: { path: string; name: string }[];
  examples: string;
  places: Place[];
};
