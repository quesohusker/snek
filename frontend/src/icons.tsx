import {
  ArrowDownWideNarrow,
  Braces,
  Code,
  Columns3,
  Combine,
  Dices,
  Eye,
  FileInput,
  FileOutput,
  Filter,
  Fingerprint,
  Grid3x3,
  Hash,
  Layers,
  ListChecks,
  ListTree,
  Replace,
  Rotate3d,
  Sigma,
  Sparkles,
  Split,
  SquareFunction,
  Table,
  type LucideIcon,
} from "lucide-react";

const ICONS: Record<string, LucideIcon> = {
  input: FileInput,
  text_input: Table,
  output: FileOutput,
  browse: Eye,
  select: ListChecks,
  filter: Filter,
  formula: SquareFunction,
  sort: ArrowDownWideNarrow,
  sample: Dices,
  unique: Fingerprint,
  record_id: Hash,
  cleanse: Sparkles,
  replace: Replace,
  join: Combine,
  union: Layers,
  append: Columns3,
  split: Split,
  explode: ListTree,
  unnest: Braces,
  summarize: Sigma,
  crosstab: Grid3x3,
  transpose: Rotate3d,
  python: Code,
};

export const CATEGORY_COLORS: Record<string, string> = {
  "In/Out": "var(--cat-io)",
  Preparation: "var(--cat-prep)",
  Join: "var(--cat-join)",
  Parse: "var(--cat-parse)",
  Transform: "var(--cat-transform)",
  Developer: "var(--cat-dev)",
};

export function ToolIcon({ type, size = 22 }: { type: string; size?: number }) {
  const Icon = ICONS[type] ?? Code;
  return <Icon size={size} strokeWidth={1.8} />;
}
