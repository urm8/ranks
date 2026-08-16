<script lang="ts">
  import { onMount } from "svelte";
  import ExpandableRankList from "./lib/ExpandableRankList.svelte";
  import { readSnapshotCache, writeSnapshotCache } from "./lib/snapshotCache";
  import type { Snapshot } from "./lib/types";

  let data = $state.raw<Snapshot | null>(null);
  let error = $state<string | null>(null);
  let loading = $state(true);

  const categories = $derived(data?.categories ?? []);
  const benchmarks = $derived(data?.benchmarks ?? []);
  const sources = $derived(data?.sources ?? []);
  const emerging = $derived(data?.emerging_models ?? []);
  const modelCount = $derived(data?.model_count ?? 0);

  async function load() {
    error = null;
    try {
      const res = await fetch("/api/data");
      if (!res.ok) throw new Error(`API ${res.status}`);
      const next = (await res.json()) as Snapshot;
      data = next;
      writeSnapshotCache(next);
    } catch (err) {
      if (data == null) {
        error = err instanceof Error ? err.message : String(err);
      }
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    const cached = readSnapshotCache();
    if (cached) {
      data = cached;
      loading = false;
    }
    void load();
  });
</script>

<div class="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-12">
  <header class="max-w-3xl">
    <p class="text-sm font-medium tracking-wide text-muted">ranks.urm8.org</p>
    <h1 class="mt-2 font-display text-4xl font-semibold tracking-tight text-ink sm:text-5xl">
      Model ranks
    </h1>
    <p class="mt-3 max-w-2xl text-base leading-relaxed text-muted">
      Live snapshot from Postgres — categories, benchmarks, and prices. Lists show
      the top 5 by performance; expand to load the rest in chunks.
    </p>
    <p class="mt-2 text-sm text-muted">
      Refreshed
      <span class="text-ink">{data?.generated_at ?? "…"}</span>
    </p>
  </header>

  <div class="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
    <div class="border border-line bg-panel px-4 py-3">
      <div class="font-display text-2xl font-semibold tabular-nums">{categories.length}</div>
      <div class="text-xs text-muted">categories</div>
    </div>
    <div class="border border-line bg-panel px-4 py-3">
      <div class="font-display text-2xl font-semibold tabular-nums">{benchmarks.length}</div>
      <div class="text-xs text-muted">benchmarks</div>
    </div>
    <div class="border border-line bg-panel px-4 py-3">
      <div class="font-display text-2xl font-semibold tabular-nums">{modelCount}</div>
      <div class="text-xs text-muted">models</div>
    </div>
    <div class="border border-line bg-panel px-4 py-3">
      <div class="font-display text-2xl font-semibold tabular-nums">{sources.length}</div>
      <div class="text-xs text-muted">sources</div>
    </div>
  </div>

  {#if loading}
    <p class="mt-10 text-muted">Loading snapshot…</p>
  {:else if error}
    <div class="mt-10 border border-line bg-panel px-4 py-3 text-sm">
      <p class="font-medium text-ink">Could not load /api/data</p>
      <p class="mt-1 text-muted">{error}</p>
      <button
        type="button"
        class="mt-3 border border-line px-3 py-1.5 text-sm font-medium hover:border-ink"
        onclick={() => void load()}
      >
        Retry
      </button>
    </div>
  {:else}
    <nav class="mt-10 flex flex-wrap gap-2 text-sm" aria-label="Sections">
      <a class="border border-line bg-panel px-3 py-1.5 hover:border-ink" href="#categories">Categories</a>
      <a class="border border-line bg-panel px-3 py-1.5 hover:border-ink" href="#benchmarks">Benchmarks</a>
      {#if emerging.length}
        <a class="border border-line bg-panel px-3 py-1.5 hover:border-ink" href="#emerging">Emerging</a>
      {/if}
      <a class="border border-line bg-panel px-3 py-1.5 hover:border-ink" href="#sources">Sources</a>
    </nav>

    <section id="categories" class="mt-12 scroll-mt-6">
      <h2 class="font-display text-3xl font-semibold tracking-tight">Categories</h2>
      <p class="mt-2 text-sm text-muted">Quality-ranked models per workload. Benchmark tables live once in the section below.</p>

      {#each categories as cat (cat.id ?? cat.name)}
        <article class="mt-8 border-t border-line pt-8">
          <h3 class="text-xl font-semibold">{cat.name ?? cat.id}</h3>
          {#if cat.description}
            <p class="mt-1 max-w-2xl text-sm text-muted">{cat.description}</p>
          {/if}
          <div class="mt-4">
            {#key cat.list}
              <ExpandableRankList
                rows={cat.quality_ranked ?? []}
                total={cat.quality_total ?? cat.quality_ranked?.length ?? 0}
                nextCursor={cat.next_cursor ?? null}
                listId={cat.list ?? ""}
                metricLabel="Quality"
              />
            {/key}
          </div>
          {#if cat.benchmarks?.length}
            <ul class="mt-4 flex flex-wrap gap-2 text-sm">
              {#each cat.benchmarks as bench (bench.id ?? bench.name)}
                <li>
                  <a class="border border-line bg-panel px-3 py-1.5 hover:border-ink" href={`#bench-${bench.id}`}>
                    {bench.name ?? bench.id}
                  </a>
                </li>
              {/each}
            </ul>
          {/if}
        </article>
      {:else}
        <p class="mt-4 text-sm text-muted">No categories in this snapshot.</p>
      {/each}
    </section>

    <section id="benchmarks" class="mt-16 scroll-mt-6">
      <h2 class="font-display text-3xl font-semibold tracking-tight">All benchmarks</h2>
      <p class="mt-2 text-sm text-muted">Each leaderboard is listed once. Expand to page through the rest.</p>
      <div class="mt-6 grid gap-4 md:grid-cols-2">
        {#each benchmarks as bench (bench.id ?? bench.name)}
          <div class="border border-line bg-panel p-4" id={`bench-${bench.id}`}>
            <div class="flex items-baseline justify-between gap-3">
              <h3 class="font-medium">{bench.name ?? bench.id}</h3>
              {#if bench.url}
                <a class="text-xs text-accent underline-offset-2 hover:underline" href={bench.url} target="_blank" rel="noreferrer">source</a>
              {/if}
            </div>
            <div class="mt-3">
              {#key bench.list}
                <ExpandableRankList
                  rows={bench.rankings ?? []}
                  total={bench.rankings_total ?? bench.rankings?.length ?? 0}
                  nextCursor={bench.next_cursor ?? null}
                  listId={bench.list ?? ""}
                />
              {/key}
            </div>
          </div>
        {:else}
          <p class="text-sm text-muted">No top-level benchmarks.</p>
        {/each}
      </div>
    </section>

    {#if emerging.length}
      <section id="emerging" class="mt-16 scroll-mt-6">
        <h2 class="font-display text-3xl font-semibold tracking-tight">Newly listed</h2>
        <p class="mt-2 text-sm text-muted">Catalogued models not yet ranked on a leaderboard.</p>
        <div class="mt-4 overflow-x-auto border border-line bg-panel">
          <table class="w-full min-w-[40rem] border-collapse text-left text-sm">
            <thead>
              <tr class="border-b border-line text-[0.7rem] uppercase tracking-[0.06em] text-muted">
                <th class="px-3 py-2.5 font-semibold">Model</th>
                <th class="px-3 py-2.5 font-semibold">Vendor</th>
                <th class="px-3 py-2.5 font-semibold">In / Out</th>
                <th class="px-3 py-2.5 font-semibold">Context</th>
              </tr>
            </thead>
            <tbody>
              {#each emerging as m (m.id ?? m.name)}
                <tr class="border-b border-line/80 last:border-0">
                  <td class="px-3 py-2.5 font-medium">{m.name ?? m.id}</td>
                  <td class="px-3 py-2.5 text-muted">{m.vendor ?? ""}</td>
                  <td class="px-3 py-2.5 tabular-nums text-muted">
                    {m.input ?? "—"} / {m.output ?? "—"}
                  </td>
                  <td class="px-3 py-2.5 tabular-nums text-muted">{m.context ?? "—"}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </section>
    {/if}

    <section id="sources" class="mt-16 scroll-mt-6 pb-16">
      <h2 class="font-display text-3xl font-semibold tracking-tight">Sources</h2>
      <ul class="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {#each sources as source (source.url ?? source.name)}
          <li class="border border-line bg-panel px-3 py-3 text-sm" class:opacity-60={source.ok === false}>
            <div class="font-medium">{source.name ?? source.url}</div>
            <div class="mt-1 text-xs text-muted">
              {source.ok === false ? "failed" : "ok"}
              {#if source.kind}
                · {source.kind}
              {/if}
            </div>
            {#if source.url}
              <a class="mt-2 inline-block text-xs text-accent underline-offset-2 hover:underline" href={source.url} target="_blank" rel="noreferrer">open</a>
            {/if}
          </li>
        {/each}
      </ul>
    </section>
  {/if}
</div>
