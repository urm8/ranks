<script lang="ts">
  import { iterateRankings } from "./rankings";
  import { rowKey, rowLabel, rowScore, type RankRow } from "./types";

  const TOP_VISIBLE = 5;

  let {
    rows = [],
    total = 0,
    nextCursor = null,
    listId = "",
    metricLabel = "Score",
  }: {
    rows?: RankRow[];
    total?: number;
    nextCursor?: string | null;
    listId?: string;
    metricLabel?: string;
  } = $props();

  let expanded = $state(false);
  let loadingMore = $state(false);
  let loadError = $state<string | null>(null);
  let extra = $state.raw<RankRow[]>([]);
  let fetchedCursor = $state<string | null | undefined>(undefined);

  const loaded = $derived([...rows, ...extra]);
  const cursor = $derived(fetchedCursor === undefined ? nextCursor : fetchedCursor);
  const hidden = $derived(Math.max(0, total - TOP_VISIBLE));
  const visible = $derived(expanded ? loaded : loaded.slice(0, TOP_VISIBLE));

  async function loadRemaining() {
    if (!listId || cursor == null || loadingMore) return;
    loadingMore = true;
    loadError = null;
    try {
      for await (const page of iterateRankings(listId, cursor)) {
        extra = [...extra, ...page.items];
        fetchedCursor = page.next_cursor;
      }
    } catch (err) {
      loadError = err instanceof Error ? err.message : String(err);
    } finally {
      loadingMore = false;
    }
  }

  async function toggle() {
    if (expanded) {
      expanded = false;
      return;
    }
    expanded = true;
    await loadRemaining();
  }
</script>

{#if loaded.length === 0}
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
        {#each visible as row, index (rowKey(row, index))}
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
      class="mt-3 border border-line bg-panel px-3 py-2 text-sm font-medium text-ink transition hover:border-ink disabled:opacity-60"
      onclick={() => void toggle()}
      disabled={loadingMore}
      data-expand-toggle
    >
      {#if expanded && loadingMore}
        Loading {loaded.length} of {total}…
      {:else if expanded}
        Show top {TOP_VISIBLE}
      {:else}
        Show all {total} (+{hidden} more)
      {/if}
    </button>
  {/if}

  {#if loadError}
    <p class="mt-2 text-sm text-muted">Could not load more: {loadError}</p>
    <button
      type="button"
      class="mt-2 border border-line px-3 py-1.5 text-sm font-medium hover:border-ink"
      onclick={() => void loadRemaining()}
    >
      Retry
    </button>
  {/if}
{/if}
