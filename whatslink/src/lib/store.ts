import { promises as fs } from "node:fs";
import path from "node:path";
import type { Dataset, Group, Source } from "./types";

const DATA_DIR = path.join(process.cwd(), "data");
const GROUPS_FILE = path.join(DATA_DIR, "groups.json");
const SOURCES_FILE = path.join(DATA_DIR, "sources.json");

export async function loadDataset(): Promise<Dataset> {
  try {
    const raw = await fs.readFile(GROUPS_FILE, "utf8");
    const parsed = JSON.parse(raw) as Dataset;
    return { updatedAt: parsed.updatedAt ?? "", groups: parsed.groups ?? [] };
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") {
      return { updatedAt: "", groups: [] };
    }
    throw err;
  }
}

export async function saveDataset(dataset: Dataset): Promise<void> {
  await fs.mkdir(DATA_DIR, { recursive: true });
  const sorted = [...dataset.groups].sort((a, b) => a.id.localeCompare(b.id));
  const payload: Dataset = { updatedAt: dataset.updatedAt, groups: sorted };
  await fs.writeFile(GROUPS_FILE, JSON.stringify(payload, null, 2) + "\n", "utf8");
}

export async function loadSources(): Promise<Source[]> {
  const raw = await fs.readFile(SOURCES_FILE, "utf8");
  return JSON.parse(raw) as Source[];
}

/**
 * ממזג קבוצות חדשות לתוך המאגר הקיים לפי מזהה.
 * שומר על firstSeen המקורי ומעדכן lastSeen ומטא-דאטה שהשתפרה.
 */
export function mergeGroups(existing: Group[], incoming: Group[]): {
  groups: Group[];
  added: number;
  updated: number;
} {
  const byId = new Map(existing.map((g) => [g.id, g]));
  let added = 0;
  let updated = 0;

  for (const group of incoming) {
    const prev = byId.get(group.id);
    if (!prev) {
      byId.set(group.id, group);
      added++;
      continue;
    }
    // כותרת ארוכה ואינפורמטיבית יותר מנצחת; firstSeen לעולם לא משתנה.
    const betterTitle = group.title.length > prev.title.length ? group.title : prev.title;
    const betterDesc =
      group.description.length > prev.description.length ? group.description : prev.description;
    byId.set(group.id, {
      ...prev,
      ...group,
      title: betterTitle,
      description: betterDesc,
      firstSeen: prev.firstSeen,
      lastSeen: group.lastSeen,
    });
    updated++;
  }

  return { groups: [...byId.values()], added, updated };
}
