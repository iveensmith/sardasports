/**
 * The results strip's own copy of its last good answer.
 *
 * The strip is the home page's proof, and it used to disappear whenever anything
 * upstream hiccuped: a slow engine, a failed request, a restart. The engine now
 * keeps its own last good answer, but the website cannot assume the engine is
 * reachable at all, so it keeps one too, in memory and on disk. The disk copy
 * means a website restart during an engine outage does not blank the strip either.
 *
 * Server-side only. Every read and write is wrapped: a missing or unwritable file
 * must never be the reason the page fails.
 */

import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import type { RecentSettled } from "@/lib/api";

const FILE = path.join(os.tmpdir(), "uniquepredict-recent-settled.json");

let inMemory: RecentSettled | null = null;

export async function rememberRecent(value: RecentSettled): Promise<void> {
  inMemory = value;
  try {
    await fs.writeFile(FILE, JSON.stringify(value), "utf8");
  } catch {
    // The in-memory copy still stands.
  }
}

export async function recallRecent(): Promise<RecentSettled | null> {
  if (inMemory) return inMemory;
  try {
    const parsed = JSON.parse(await fs.readFile(FILE, "utf8")) as RecentSettled;
    if (Array.isArray(parsed?.rows)) {
      inMemory = parsed;
      return parsed;
    }
  } catch {
    // Nothing saved yet, or unreadable: there is simply no fallback.
  }
  return null;
}
