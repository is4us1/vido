/**
 * מסווג מחדש את כל המאגר הקיים בלי לזחול שוב.
 * שימושי אחרי עריכת מילות המפתח ב-src/lib/categories.ts.
 */
import { classify } from "../lib/classify";
import { scoreIsraeli } from "../lib/israeli";
import { loadDataset, saveDataset } from "../lib/store";
import { categoryName } from "../lib/categories";

const dropNonIsraeli = process.argv.includes("--drop-non-israeli");

async function main(): Promise<void> {
  const dataset = await loadDataset();
  let changed = 0;
  let dropped = 0;

  const groups = dataset.groups.flatMap((group) => {
    const text = `${group.title} ${group.description}`;
    const verdict = scoreIsraeli(text);
    if (dropNonIsraeli && !verdict.israeli) {
      dropped++;
      return [];
    }
    const cls = classify(group.title, group.description);
    if (cls.category !== group.category) changed++;
    return [{
      ...group,
      category: cls.category,
      categoryScore: cls.score,
      tags: cls.tags,
      israeli: verdict.israeli,
      israeliScore: verdict.score,
      israeliSignals: verdict.signals,
    }];
  });

  await saveDataset({ updatedAt: new Date().toISOString(), groups });

  const byCategory = new Map<string, number>();
  for (const g of groups) byCategory.set(g.category, (byCategory.get(g.category) ?? 0) + 1);
  for (const [slug, count] of [...byCategory].sort((a, b) => b[1] - a[1])) {
    console.log(`  ${categoryName(slug).padEnd(22)} ${count}`);
  }
  console.log(`\nשונו קטגוריה: ${changed} | הוסרו: ${dropped} | סה"כ: ${groups.length}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
