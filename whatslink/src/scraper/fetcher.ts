import { parseRobots, isAllowed, ALLOW_ALL, type RobotsRules } from "./robots";

const CONTACT = process.env.SCRAPER_CONTACT_URL ?? "https://github.com/is4us1/whatslink";
export const USER_AGENT = `WhatsLinkBot/1.0 (+${CONTACT})`;

const MIN_DELAY_MS = Number(process.env.SCRAPER_MIN_DELAY_MS ?? 1500);
const TIMEOUT_MS = 20_000;

const robotsCache = new Map<string, Promise<RobotsRules>>();
const lastRequestAt = new Map<string, number>();

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** משהה כדי לכבד את ההשהיה המינימלית לכל דומיין (או Crawl-delay של האתר). */
async function throttle(host: string, delayMs: number): Promise<void> {
  const last = lastRequestAt.get(host);
  const now = Date.now();
  if (last !== undefined) {
    const wait = last + delayMs - now;
    if (wait > 0) await sleep(wait);
  }
  lastRequestAt.set(host, Date.now());
}

async function getRobots(origin: string): Promise<RobotsRules> {
  const cached = robotsCache.get(origin);
  if (cached) return cached;

  const promise = (async () => {
    try {
      const res = await fetch(`${origin}/robots.txt`, {
        headers: { "user-agent": USER_AGENT },
        signal: AbortSignal.timeout(TIMEOUT_MS),
      });
      // 4xx = אין robots.txt = מותר. 5xx = ספק — נהיה שמרנים ונאסור.
      if (res.status >= 500) return { rules: [{ allow: false, path: "/" }], crawlDelayMs: null };
      if (!res.ok) return ALLOW_ALL;
      return parseRobots(await res.text(), USER_AGENT);
    } catch {
      return ALLOW_ALL;
    }
  })();

  robotsCache.set(origin, promise);
  return promise;
}

export interface FetchResult {
  ok: boolean;
  html?: string;
  status?: number;
  blockedByRobots?: boolean;
  error?: string;
}

/**
 * מוריד עמוד HTML בנימוס: בודק robots.txt, מגביל קצב לכל דומיין,
 * מנסה שוב על שגיאות זמניות ומוותר על תשובות שאינן HTML.
 */
export async function fetchPage(url: string, retries = 2): Promise<FetchResult> {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return { ok: false, error: "כתובת לא תקינה" };
  }

  const robots = await getRobots(parsed.origin);
  if (!isAllowed(robots, parsed.pathname + parsed.search)) {
    return { ok: false, blockedByRobots: true };
  }

  const delay = Math.max(MIN_DELAY_MS, robots.crawlDelayMs ?? 0);

  for (let attempt = 0; attempt <= retries; attempt++) {
    await throttle(parsed.host, delay);
    try {
      const res = await fetch(url, {
        headers: {
          "user-agent": USER_AGENT,
          accept: "text/html,application/xhtml+xml",
          "accept-language": "he-IL,he;q=0.9,en;q=0.6",
        },
        redirect: "follow",
        signal: AbortSignal.timeout(TIMEOUT_MS),
      });

      if (res.status === 429 || res.status >= 500) {
        if (attempt < retries) {
          await sleep(delay * 2 ** (attempt + 1));
          continue;
        }
        return { ok: false, status: res.status, error: `HTTP ${res.status}` };
      }
      if (!res.ok) return { ok: false, status: res.status, error: `HTTP ${res.status}` };

      const type = res.headers.get("content-type") ?? "";
      if (!type.includes("html")) return { ok: false, status: res.status, error: "לא HTML" };

      return { ok: true, html: await res.text(), status: res.status };
    } catch (err) {
      if (attempt < retries) {
        await sleep(delay * 2 ** (attempt + 1));
        continue;
      }
      return { ok: false, error: err instanceof Error ? err.message : String(err) };
    }
  }

  return { ok: false, error: "כשל לא ידוע" };
}
