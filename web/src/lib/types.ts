export type RankRow = {
  id?: string;
  model_id?: string;
  name?: string;
  model?: string;
  vendor?: string;
  quality?: number | string | null;
  score?: number | string | null;
  rank?: number | null;
  value?: number | null;
  cycle_cost?: number | null;
  note?: string;
  input?: number | null;
  output?: number | null;
  context?: number | null;
};

export type RankPage = {
  list?: string;
  items: RankRow[];
  total: number;
  next_cursor: string | null;
};

export type Benchmark = {
  id?: string;
  name?: string;
  url?: string;
  category?: string;
  list?: string;
  rankings?: RankRow[];
  rankings_total?: number;
  next_cursor?: string | null;
};

export type Category = {
  id?: string;
  name?: string;
  description?: string;
  list?: string;
  quality_ranked?: RankRow[];
  quality_total?: number;
  next_cursor?: string | null;
  benchmarks?: Array<{ id?: string; name?: string }>;
};

export type Source = {
  name?: string;
  url?: string;
  ok?: boolean;
  kind?: string;
  error?: string;
  status?: number | null;
};

export type EmergingModel = {
  id?: string;
  name?: string;
  vendor?: string;
  input?: number | null;
  output?: number | null;
  context?: number | null;
  release_date?: string;
  catalog_sources?: string[];
};

export type Snapshot = {
  generated_at?: string;
  sources?: Source[];
  model_count?: number;
  benchmarks?: Benchmark[];
  categories?: Category[];
  emerging_models?: EmergingModel[];
  emerging_total?: number;
};

export function rowLabel(row: RankRow): string {
  return row.name || row.model || row.model_id || row.id || "unknown";
}

export function rowScore(row: RankRow): string {
  const raw = row.quality ?? row.score ?? row.rank;
  if (raw == null || raw === "") return "—";
  if (typeof raw === "number") {
    return Number.isInteger(raw) ? String(raw) : raw.toFixed(1);
  }
  return String(raw);
}

export function rowKey(row: RankRow, index: number): string {
  return row.model_id || row.id || `${rowLabel(row)}-${index}`;
}
