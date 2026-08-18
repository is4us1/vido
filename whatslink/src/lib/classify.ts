import { CATEGORIES, DEFAULT_CATEGORY } from "./categories";

export interface Classification {
  category: string;
  score: number;
  tags: string[];
  /** כל הקטגוריות שקיבלו ניקוד, ממוינות — שימושי לדיבוג ולסיווג מחדש. */
  ranked: Array<{ slug: string; score: number }>;
}

/**
 * מחזיר גבול-מילה שעובד גם בעברית (ל-\b אין משמעות מול תווים עבריים).
 * מתייחס לכל תו שאינו אות/ספרה כגבול.
 */
function occurrences(haystack: string, needle: string): number {
  if (!needle) return 0;
  let count = 0;
  let from = 0;
  for (;;) {
    const idx = haystack.indexOf(needle, from);
    if (idx === -1) break;
    const before = haystack[idx - 1];
    const after = haystack[idx + needle.length];
    const isLetter = (ch: string | undefined) => ch !== undefined && /[\p{L}\p{N}]/u.test(ch);
    // ביטוי רב-מילים נחשב גם בתוך משפט; מילה בודדת חייבת גבולות.
    if (needle.includes(" ") || (!isLetter(before) && !isLetter(after))) count++;
    from = idx + needle.length;
  }
  return count;
}

/**
 * מסווג קבוצה לפי הטקסט שלה.
 *
 * הניקוד: משקל מילת המפתח × (1 + log של מספר ההופעות). הופעה בכותרת
 * שווה כפליים מהופעה בתיאור, כי כותרת מתארת את הקבוצה עצמה.
 */
export function classify(title: string, description = ""): Classification {
  const t = title.toLowerCase();
  const d = description.toLowerCase();
  const tags: string[] = [];
  const ranked: Array<{ slug: string; score: number }> = [];

  for (const cat of CATEGORIES) {
    let score = 0;
    for (const [keyword, weight] of cat.keywords) {
      const kw = keyword.toLowerCase();
      const inTitle = occurrences(t, kw);
      const inDesc = occurrences(d, kw);
      if (!inTitle && !inDesc) continue;
      const hits = inTitle * 2 + inDesc;
      score += weight * (1 + Math.log2(hits));
      if (!tags.includes(keyword)) tags.push(keyword);
    }
    if (score > 0) ranked.push({ slug: cat.slug, score: Math.round(score * 100) / 100 });
  }

  ranked.sort((a, b) => b.score - a.score);
  const best = ranked[0];

  return {
    category: best?.slug ?? DEFAULT_CATEGORY,
    score: best?.score ?? 0,
    tags: tags.slice(0, 8),
    ranked: ranked.slice(0, 5),
  };
}
