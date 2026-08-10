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

export type Benchmark = {
  id?: string;
  name?: string;
  url?: string;
  category?: string;
  rankings?: RankRow[];
};

export type Category = {
  id?: string;
  name?: string;
  description?: string;
  quality_ranked?: RankRow[];
  value_ranked?: RankRow[];
  benchmarks?: Benchmark[];
  benchmark_details?: Benchmark[];
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
  models?: Record<string, unknown> | unknown[];
  benchmarks?: Benchmark[];
  categories?: Category[];
  emerging_models?: EmergingModel[];
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

export function sortByPerformance(rows: RankRow[]): RankRow[] {
  return [...rows].sort((a, b) => {
    const aq = typeof a.quality === "number" ? a.quality : null;
    const bq = typeof b.quality === "number" ? b.quality : null;
    if (aq != null && bq != null) return bq - aq;

    const as = typeof a.score === "number" ? a.score : Number(a.score);
    const bs = typeof b.score === "number" ? b.score : Number(b.score);
    if (Number.isFinite(as) && Number.isFinite(bs)) return bs - as;

    const ar = typeof a.rank === "number" ? a.rank : Number.POSITIVE_INFINITY;
    const br = typeof b.rank === "number" ? b.rank : Number.POSITIVE_INFINITY;
    return ar - br;
  });
}
