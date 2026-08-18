/**
 * בדיקות עצמיות לצינור העיבוד — רצות אופליין מול קבצי HTML לדוגמה.
 * הרצה: npm test
 */
import { promises as fs } from "node:fs";
import path from "node:path";
import { extractGroups } from "./extract";
import { crawlSource } from "./crawl";
import { classify } from "../lib/classify";
import { scoreIsraeli } from "../lib/israeli";
import { parseRobots, isAllowed } from "./robots";
import { mergeGroups } from "../lib/store";
import type { FetchResult } from "./fetcher";
import type { Group, Source } from "../lib/types";

let failures = 0;

function check(name: string, condition: boolean, detail = ""): void {
  if (condition) {
    console.log(`  ✓ ${name}`);
  } else {
    failures++;
    console.log(`  ✗ ${name}${detail ? ` — ${detail}` : ""}`);
  }
}

const FIXTURES = path.join(import.meta.dirname, "fixtures");

async function main(): Promise<void> {
  const page1 = await fs.readFile(path.join(FIXTURES, "directory.html"), "utf8");
  const page2 = await fs.readFile(path.join(FIXTURES, "page2.html"), "utf8");
  const base = "https://example.com/whatsapp-groups";

  console.log("\nחילוץ קישורים:");
  const raw = extractGroups(page1, base);
  check("נמצאו 5 קבוצות ייחודיות", raw.length === 5, `נמצאו ${raw.length}`);
  const jobs = raw.find((g) => g.code.startsWith("AAAA"));
  check("כותרת נלקחה מהכותרת ולא מ'הצטרפו לקבוצה'", jobs?.title === "דרושים הייטק תל אביב", jobs?.title);
  check("תיאור נקלט", (jobs?.description ?? "").includes("משרות הייטק"));
  check("קישור בטקסט חופשי נקלט", raw.some((g) => g.code.startsWith("EEEE")));
  check("קישור כפול לאותה קבוצה מאוחד", new Set(raw.map((g) => g.code)).size === raw.length);

  console.log("\nסיווג לקטגוריות:");
  check("דרושים → jobs", classify("דרושים הייטק תל אביב", "משרות פיתוח").category === "jobs");
  check("דירות → real-estate", classify("דירות להשכרה בירושלים", "שותפים לדירה").category === "real-estate");
  check("קריפטו → finance", classify("קריפטו וביטקוין", "מניות ובורסה").category === "finance");
  check("טיולים → travel", classify("תרמילאים בדרום אמריקה", "טיסות זולות").category === "travel");
  check("אמהות → family", classify("אמהות בחיפה", "הריון ולידה").category === "family");
  check("ללא התאמה → other", classify("קבוצה", "").category === "other");
  check("כותרת שוקלת כפליים", classify("מתכונים", "כדורגל").category === "food");

  console.log("\nזיהוי ישראליות:");
  check("עברית מזוהה", scoreIsraeli("קבוצת דרושים בתל אביב").israeli);
  check("אנגלית הודית נפסלת", !scoreIsraeli("Daily job alerts for candidates across india").israeli);
  check("טלפון ישראלי מוסיף ניקוד", scoreIsraeli("group 054-1234567 tel aviv").score >= 3);
  check("ערבית ללא עברית נפסלת", !scoreIsraeli("مجموعة الأصدقاء للدردشة والترفيه اليومي").israeli);

  console.log("\nrobots.txt:");
  const robots = parseRobots(
    "User-agent: *\nDisallow: /private\nAllow: /private/public\nCrawl-delay: 2\n",
    "WhatsLinkBot/1.0",
  );
  check("Disallow נאכף", !isAllowed(robots, "/private/x"));
  check("Allow ספציפי גובר", isAllowed(robots, "/private/public/y"));
  check("נתיב אחר מותר", isAllowed(robots, "/groups"));
  check("Crawl-delay נקרא", robots.crawlDelayMs === 2000);
  const uaSpecific = parseRobots(
    "User-agent: *\nDisallow:\n\nUser-agent: WhatsLinkBot\nDisallow: /\n",
    "WhatsLinkBot/1.0",
  );
  check("קבוצת UA ייעודית גוברת", !isAllowed(uaSpecific, "/anything"));

  console.log("\nזחילה מקצה לקצה (fetch מדומה):");
  const pages: Record<string, string> = {
    "https://example.com/whatsapp-groups": page1,
    "https://example.com/whatsapp-groups?page=2": page2,
  };
  const fakeFetch = async (url: string): Promise<FetchResult> =>
    pages[url] ? { ok: true, html: pages[url], status: 200 } : { ok: false, error: "404" };

  const source: Source = {
    id: "fixture",
    name: "Fixture",
    startUrls: ["https://example.com/whatsapp-groups"],
    followPatterns: ["/whatsapp-groups(/|\\?page=)"],
    ignorePatterns: ["/login"],
    maxPages: 10,
    enabled: true,
    assumeIsraeli: false,
  };

  const { groups, stats } = await crawlSource(source, { fetcher: fakeFetch });
  check("שני עמודים נזחלו", stats.pagesFetched === 2, String(stats.pagesFetched));
  check("קבוצה לא-ישראלית נפסלה", !groups.some((g) => g.id.startsWith("CCCC")));
  check("6 קבוצות ישראליות נשמרו", groups.length === 6, String(groups.length));
  check("לא יצאנו מהדומיין", !stats.errors.some((e) => e.includes("other-site.com")));
  check("כל קבוצה קיבלה קטגוריה", groups.every((g) => g.category.length > 0));
  check("כתובת ההזמנה מנורמלת", groups.every((g) => g.url.startsWith("https://chat.whatsapp.com/")));

  console.log("\nמיזוג מאגר:");
  const older: Group[] = [{ ...groups[0], title: "כותרת ישנה", firstSeen: "2020-01-01T00:00:00.000Z" }];
  const merged = mergeGroups(older, groups);
  check("firstSeen נשמר", merged.groups.find((g) => g.id === groups[0].id)?.firstSeen === "2020-01-01T00:00:00.000Z");
  check("אין כפילויות", new Set(merged.groups.map((g) => g.id)).size === merged.groups.length);
  check("נספרו חדשות", merged.added === groups.length - 1, String(merged.added));

  console.log(failures === 0 ? "\nכל הבדיקות עברו ✓\n" : `\n${failures} בדיקות נכשלו ✗\n`);
  if (failures) process.exit(1);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
