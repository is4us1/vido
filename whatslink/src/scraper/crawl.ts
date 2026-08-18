import { fetchPage } from "./fetcher";
import { extractGroups, extractLinks } from "./extract";
import { classify } from "../lib/classify";
import { scoreIsraeli } from "../lib/israeli";
import { cleanText, inviteUrl } from "../lib/normalize";
import type { Group, ScrapeStats, Source } from "../lib/types";

export interface CrawlResult {
  groups: Group[];
  stats: ScrapeStats;
}

export interface CrawlOptions {
  maxPages?: number;
  /** מקבל דיווח התקדמות אחרי כל עמוד. */
  onPage?: (url: string, index: number, total: number) => void;
  /** מאפשר להזריק fetch אחר בבדיקות. */
  fetcher?: typeof fetchPage;
}

/**
 * זוחל על מקור אחד: BFS מעמודי הפתיחה, נשאר באותו דומיין,
 * ממשיך רק לקישורים שתואמים ל-followPatterns.
 */
export async function crawlSource(source: Source, options: CrawlOptions = {}): Promise<CrawlResult> {
  const fetcher = options.fetcher ?? fetchPage;
  const maxPages = options.maxPages ?? source.maxPages ?? Number(process.env.SCRAPER_MAX_PAGES ?? 120);
  const follow = source.followPatterns.map((p) => new RegExp(p, "i"));
  const ignore = (source.ignorePatterns ?? []).map((p) => new RegExp(p, "i"));

  const allowedHosts = new Set(source.startUrls.map((u) => new URL(u).host));
  const queue = [...source.startUrls];
  const visited = new Set<string>();
  const byCode = new Map<string, Group>();
  const now = new Date().toISOString();

  const stats: ScrapeStats = {
    source: source.id,
    pagesFetched: 0,
    pagesSkippedByRobots: 0,
    linksFound: 0,
    uniqueGroups: 0,
    israeliKept: 0,
    nonIsraeliDropped: 0,
    errors: [],
  };

  while (queue.length && visited.size < maxPages) {
    const url = queue.shift() as string;
    if (visited.has(url)) continue;
    visited.add(url);

    const res = await fetcher(url);
    if (res.blockedByRobots) {
      stats.pagesSkippedByRobots++;
      continue;
    }
    if (!res.ok || !res.html) {
      stats.errors.push(`${url}: ${res.error ?? "כשל לא ידוע"}`);
      continue;
    }
    stats.pagesFetched++;
    options.onPage?.(url, visited.size, maxPages);

    for (const raw of extractGroups(res.html, url)) {
      stats.linksFound++;
      const title = cleanText(raw.title, 140);
      const description = cleanText(raw.description, 400);
      const verdict = scoreIsraeli(`${title} ${description}`, source.assumeIsraeli ?? false);

      if (!verdict.israeli) {
        if (!byCode.has(raw.code)) stats.nonIsraeliDropped++;
        continue;
      }

      const cls = classify(title, description);
      byCode.set(raw.code, {
        id: raw.code,
        url: inviteUrl(raw.code),
        title,
        description,
        category: cls.category,
        categoryScore: cls.score,
        tags: cls.tags,
        israeli: true,
        israeliScore: verdict.score,
        israeliSignals: verdict.signals,
        source: source.id,
        sourceUrl: url,
        firstSeen: now,
        lastSeen: now,
      });
    }

    if (!follow.length) continue;
    for (const link of extractLinks(res.html, url)) {
      if (visited.has(link) || queue.includes(link)) continue;
      const parsed = new URL(link);
      if (!allowedHosts.has(parsed.host)) continue;
      if (ignore.some((re) => re.test(link))) continue;
      if (!follow.some((re) => re.test(link))) continue;
      queue.push(link);
    }
  }

  stats.uniqueGroups = byCode.size;
  stats.israeliKept = byCode.size;

  return { groups: [...byCode.values()], stats };
}
