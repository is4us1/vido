/**
 * פרסור robots.txt מינימלי אך נאמן למה שחשוב לנו:
 * קבוצות User-agent, Disallow/Allow עם התאמת התחילית הארוכה ביותר,
 * ו-Crawl-delay. אתר שאוסר — לא נזחל בו.
 */

export interface RobotsRules {
  rules: Array<{ allow: boolean; path: string }>;
  crawlDelayMs: number | null;
}

export function parseRobots(body: string, userAgent: string): RobotsRules {
  const ua = userAgent.toLowerCase();
  const groups: Array<{ agents: string[]; rules: RobotsRules["rules"]; delay: number | null }> = [];
  let current: (typeof groups)[number] | null = null;
  let lastLineWasAgent = false;

  for (const rawLine of body.split(/\r?\n/)) {
    const line = rawLine.split("#")[0].trim();
    if (!line) continue;
    const idx = line.indexOf(":");
    if (idx === -1) continue;
    const field = line.slice(0, idx).trim().toLowerCase();
    const value = line.slice(idx + 1).trim();

    if (field === "user-agent") {
      if (!current || !lastLineWasAgent) {
        current = { agents: [], rules: [], delay: null };
        groups.push(current);
      }
      current.agents.push(value.toLowerCase());
      lastLineWasAgent = true;
      continue;
    }
    lastLineWasAgent = false;
    if (!current) continue;

    if (field === "disallow") current.rules.push({ allow: false, path: value });
    else if (field === "allow") current.rules.push({ allow: true, path: value });
    else if (field === "crawl-delay") {
      const secs = Number.parseFloat(value);
      if (Number.isFinite(secs)) current.delay = secs * 1000;
    }
  }

  // קבוצה ספציפית ל-UA שלנו גוברת על ‎*‎.
  const specific = groups.find((g) => g.agents.some((a) => a !== "*" && ua.includes(a)));
  const wildcard = groups.find((g) => g.agents.includes("*"));
  const chosen = specific ?? wildcard;

  return { rules: chosen?.rules ?? [], crawlDelayMs: chosen?.delay ?? null };
}

/** התאמת התחילית הארוכה ביותר; שוויון — Allow מנצח, כמו במפרט של גוגל. */
export function isAllowed(rules: RobotsRules, pathname: string): boolean {
  let best: { allow: boolean; length: number } | null = null;

  for (const rule of rules.rules) {
    if (rule.path === "") continue; // "Disallow:" ריק = מותר הכול
    const pattern = rule.path;
    if (!matchesPattern(pattern, pathname)) continue;
    const length = pattern.length;
    if (!best || length > best.length || (length === best.length && rule.allow)) {
      best = { allow: rule.allow, length };
    }
  }

  return best ? best.allow : true;
}

/** תומך ב-* ו-$ כמקובל ב-robots.txt. */
function matchesPattern(pattern: string, pathname: string): boolean {
  if (!pattern.includes("*") && !pattern.endsWith("$")) {
    return pathname.startsWith(pattern);
  }
  const anchored = pattern.endsWith("$");
  const body = anchored ? pattern.slice(0, -1) : pattern;
  const regex = new RegExp(
    "^" + body.split("*").map((p) => p.replace(/[.+?^${}()|[\]\\]/g, "\\$&")).join(".*") +
      (anchored ? "$" : ""),
  );
  return regex.test(pathname);
}

export const ALLOW_ALL: RobotsRules = { rules: [], crawlDelayMs: null };
