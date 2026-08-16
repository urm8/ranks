import type { RankPage } from "./types";

const CHUNK = 200;

export async function* iterateRankings(
  listId: string,
  cursor: string | null,
  signal?: AbortSignal,
): AsyncGenerator<RankPage, void, void> {
  let next = cursor;
  while (next != null) {
    const params = new URLSearchParams({
      list: listId,
      cursor: next,
      limit: String(CHUNK),
    });
    const res = await fetch(`/api/rankings?${params}`, { signal });
    if (!res.ok) throw new Error(`API ${res.status}`);
    const page = (await res.json()) as RankPage;
    yield page;
    next = page.next_cursor;
  }
}
