import * as cheerio from "cheerio";
import type { AnyNode } from "domhandler";
import { INVITE_RE, cleanText, extractInviteCode, isJunkTitle } from "../lib/normalize";

export interface RawGroup {
  code: string;
  title: string;
  description: string;
}

const HEADING_SELECTOR = "h1, h2, h3, h4, h5, .title, .group-title, [class*='title'], [class*='name']";

/**
 * מוצא בעמוד את כל קישורי ההזמנה ואוסף לכל אחד כותרת ותיאור.
 *
 * שני מסלולים: קישור בתוך <a> (הנפוץ בספריות קבוצות), וקישור שכתוב
 * כטקסט חופשי בתוך פסקה — שם ההקשר הוא הפסקה עצמה.
 */
export function extractGroups(html: string, pageUrl: string): RawGroup[] {
  const $ = cheerio.load(html);
  const pageTitle = cleanText($("title").first().text(), 120);
  const found = new Map<string, RawGroup>();

  $("a[href]").each((_, el) => {
    const href = $(el).attr("href") ?? "";
    const absolute = toAbsolute(href, pageUrl);
    const code = absolute && extractInviteCode(absolute);
    if (!code) return;

    const { title, description } = contextFor($, el, pageTitle);
    upsert(found, { code, title, description });
  });

  // קישורים שמופיעים כטקסט ולא כעוגן.
  const bodyText = $("body").text();
  for (const match of bodyText.matchAll(new RegExp(INVITE_RE.source, "gi"))) {
    const code = match[1];
    if (found.has(code)) continue;
    const at = match.index ?? 0;
    const around = cleanText(bodyText.slice(Math.max(0, at - 300), at), 300);
    upsert(found, {
      code,
      title: lastSentence(around) || pageTitle,
      description: around,
    });
  }

  return [...found.values()];
}

/** מעדכן רק אם המידע החדש עשיר יותר — עמוד יכול להזכיר קבוצה פעמיים. */
function upsert(map: Map<string, RawGroup>, group: RawGroup): void {
  const prev = map.get(group.code);
  if (!prev) {
    map.set(group.code, group);
    return;
  }
  map.set(group.code, {
    code: group.code,
    title: group.title.length > prev.title.length ? group.title : prev.title,
    description:
      group.description.length > prev.description.length ? group.description : prev.description,
  });
}

/**
 * מטפס במעלה העץ עד "כרטיס" סביר ומחלץ ממנו כותרת ותיאור.
 * עוצר אחרי 5 רמות כדי לא לגלוש לכל העמוד.
 */
function contextFor(
  $: cheerio.CheerioAPI,
  el: AnyNode,
  pageTitle: string,
): { title: string; description: string } {
  const anchorText = cleanText($(el).text(), 120);
  let title = isJunkTitle(anchorText) ? "" : anchorText;
  let description = "";

  let node = $(el).parent();
  for (let depth = 0; depth < 5 && node.length; depth++) {
    if (!title) {
      const heading = cleanText(node.find(HEADING_SELECTOR).first().text(), 120);
      if (heading && !isJunkTitle(heading)) title = heading;
    }
    if (!description) {
      const para = cleanText(node.find("p, .description, [class*='desc']").first().text(), 400);
      // תיאור חייב להוסיף מידע מעבר לכותרת.
      if (para && para !== title && para.length > 15) description = para;
    }
    if (title && description) break;
    node = node.parent();
  }

  if (!description) {
    const block = cleanText($(el).closest("li, article, .card, div").first().text(), 400);
    if (block && block !== title) description = block;
  }

  return { title: title || pageTitle, description };
}

function lastSentence(text: string): string {
  const parts = text.split(/[.!?\n•|–—-]/).map((p) => p.trim()).filter(Boolean);
  const last = parts.at(-1) ?? "";
  return last.length >= 3 ? cleanText(last, 120) : "";
}

/** ממיר href יחסי לכתובת מלאה; מחזיר null לסכמות שאינן http(s). */
export function toAbsolute(href: string, base: string): string | null {
  try {
    const url = new URL(href, base);
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    url.hash = "";
    return url.toString();
  } catch {
    return null;
  }
}

/** כל הקישורים הפנימיים בעמוד — לזחילה. */
export function extractLinks(html: string, pageUrl: string): string[] {
  const $ = cheerio.load(html);
  const out = new Set<string>();
  $("a[href]").each((_, el) => {
    const abs = toAbsolute($(el).attr("href") ?? "", pageUrl);
    if (abs) out.add(abs);
  });
  return [...out];
}
