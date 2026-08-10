<script lang="ts">
  import {
    rowLabel,
    rowScore,
    sortByPerformance,
    type RankRow,
  } from "./types";

  const TOP_VISIBLE = 5;

  let {
    rows = [],
    metricLabel = "Score",
  }: {
    rows?: RankRow[];
    metricLabel?: string;
  } = $props();

  let expanded = $state(false);

  const sorted = $derived(sortByPerformance(rows));
  const hidden = $derived(Math.max(0, sorted.length - TOP_VISIBLE));
  const visible = $derived(expanded ? sorted : sorted.slice(0, TOP_VISIBLE));
</script>

{#if sorted.length === 0}
  <p class="text-sm text-muted">No rankings yet.</p>
{:else}
  <div class="overflow-x-auto border border-line bg-panel">
    <table class="w-full min-w-[36rem] border-collapse text-left text-sm">
      <thead>
        <tr class="border-b border-line text-[0.7rem] uppercase tracking-[0.06em] text-muted">
          <th class="px-3 py-2.5 font-semibold">#</th>
          <th class="px-3 py-2.5 font-semibold">Model</th>
          <th class="px-3 py-2.5 font-semibold">{metricLabel}</th>
          <th class="px-3 py-2.5 font-semibold">Note</th>
        </tr>
      </thead>
      <tbody>
        {#each visible as row, index (row.id ?? row.model_id ?? `${rowLabel(row)}-${index}`)}
          <tr class="border-b border-line/80 last:border-0">
            <td class="px-3 py-2.5 font-semibold text-rank tabular-nums">
              {row.rank ?? index + 1}
            </td>
            <td class="px-3 py-2.5">
              <div class="font-medium">{rowLabel(row)}</div>
              {#if row.vendor}
                <div class="text-xs text-muted">{row.vendor}</div>
              {/if}
            </td>
            <td class="px-3 py-2.5 tabular-nums">{rowScore(row)}</td>
            <td class="px-3 py-2.5 text-muted">{row.note ?? ""}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>

  {#if hidden > 0}
    <button
      type="button"
      class="mt-3 border border-line bg-panel px-3 py-2 text-sm font-medium text-ink transition hover:border-ink"
      onclick={() => (expanded = !expanded)}
      data-expand-toggle
    >
      {#if expanded}
        Show top {TOP_VISIBLE}
      {:else}
        Show all {sorted.length} (+{hidden} more)
      {/if}
    </button>
  {/if}
{/if}
