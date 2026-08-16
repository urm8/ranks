import type { Snapshot } from "./types";

const KEY = "ranks.snapshot.v1";
const MAX_BYTES = 400_000;

export function readSnapshotCache(): Snapshot | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw || raw.length > MAX_BYTES) return null;
    const parsed = JSON.parse(raw) as Snapshot;
    if (!parsed || typeof parsed !== "object") return null;
    return parsed;
  } catch {
    return null;
  }
}

export function writeSnapshotCache(snap: Snapshot): void {
  try {
    const raw = JSON.stringify(snap);
    if (raw.length > MAX_BYTES) {
      localStorage.removeItem(KEY);
      return;
    }
    localStorage.setItem(KEY, raw);
  } catch {
    // quota / private mode
  }
}
