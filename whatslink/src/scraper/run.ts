/**
 * CLI לאיסוף קבוצות.
 *
 *   npm run scrape                 — כל המקורות הפעילים
 *   npm run scrape -- --source=id  — מקור אחד
 *   npm run scrape -- --max-pages=30
 *   npm run scrape:dry             — מריץ בלי לכתוב לקובץ
 */
import { crawlSource } from "./crawl";
import { loadDataset, loadSources, mergeGroups, saveDataset } from "../lib/store";
import { categoryName } from "../lib/categories";
import type { Group } from "../lib/types";

function arg(name: string): string | undefined {
  const prefix = `--${name}=`;
  return process.argv.find((a) => a.startsWith(prefix))?.slice(prefix.length);
}

const hasFlag = (name: string) => process.argv.includes(`--${name}`);

async function main(): Promise<void> {
  const dryRun = hasFlag("dry-run");
  const onlySource = arg("source");
  const maxPages = arg("max-pages") ? Number(arg("max-pages")) : undefined;

  const sources = (await loadSources()).filter(
    (s) => s.enabled && (!onlySource || s.id === onlySource),
  );

  if (!sources.length) {
    console.error("לא נמצאו מקורות פעילים. ערוך את data/sources.json.");
    process.exitCode = 1;
    return;
  }

  console.log(`מתחיל איסוף מ-${sources.length} מקורות${dryRun ? " (הרצה יבשה)" : ""}\n`);

  const collected: Group[] = [];

  for (const source of sources) {
    console.log(`▶ ${source.name} (${source.id})`);
    const { groups, stats } = await crawlSource(source, {
      maxPages,
      onPage: (url, i, total) => {
        process.stdout.write(`  [${i}/${total}] ${url.slice(0, 90)}\n`);
      },
    });
    collected.push(...groups);
    console.log(
      `  עמודים: ${stats.pagesFetched} | נחסמו ב-robots: ${stats.pagesSkippedByRobots} | ` +
        `קישורים: ${stats.linksFound} | ישראליות: ${stats.israeliKept} | ` +
        `נפסלו: ${stats.nonIsraeliDropped} | שגיאות: ${stats.errors.length}`,
    );
    for (const err of stats.errors.slice(0, 5)) console.log(`  ! ${err}`);
    console.log("");
  }

  const dataset = await loadDataset();
  const { groups, added, updated } = mergeGroups(dataset.groups, collected);

  const byCategory = new Map<string, number>();
  for (const g of groups) byCategory.set(g.category, (byCategory.get(g.category) ?? 0) + 1);

  console.log("סיכום לפי קטגוריה:");
  for (const [slug, count] of [...byCategory].sort((a, b) => b[1] - a[1])) {
    console.log(`  ${categoryName(slug).padEnd(22)} ${count}`);
  }
  console.log(`\nחדשות: ${added} | עודכנו: ${updated} | סה"כ במאגר: ${groups.length}`);

  if (dryRun) {
    console.log("\nהרצה יבשה — לא נכתב כלום ל-data/groups.json");
    return;
  }

  await saveDataset({ updatedAt: new Date().toISOString(), groups });
  console.log("\nנשמר ל-data/groups.json");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
