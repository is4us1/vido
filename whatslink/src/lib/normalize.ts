/** נרמול קישורי הזמנה של וואטסאפ וניקוי טקסט. */

/**
 * קוד הזמנה של קבוצת וואטסאפ הוא 20–24 תווים אלפאנומריים.
 * תומך גם בפורמט הישן ‎/invite/‎.
 */
export const INVITE_RE =
  /https?:\/\/(?:www\.)?chat\.whatsapp\.com\/(?:invite\/)?([0-9A-Za-z]{16,32})/gi;

export function extractInviteCode(url: string): string | null {
  const re = new RegExp(INVITE_RE.source, "i");
  const m = re.exec(url);
  return m ? m[1] : null;
}

export function inviteUrl(code: string): string {
  return `https://chat.whatsapp.com/${code}`;
}

/** מוחק רווחים כפולים, תווי בקרה ואימוג'ים תלויי-כיווניות מיותרים. */
export function cleanText(input: string, maxLen = 400): string {
  const text = input
    .replace(/[‎‏‪-‮]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen).replace(/\s+\S*$/, "") + "…";
}

/** כותרת סבירה: לא ריקה, לא סתם "לחצו כאן", לא הקישור עצמו. */
const JUNK_PREFIX_RE =
  /^(הצטרפ|הצטרף|כניסה|להצטרפות|לחצ|לחץ|קישור|לינק|כאן|join|click|enter|open|link|whatsapp|וואטסאפ|ווצאפ)/i;

export function isJunkTitle(title: string): boolean {
  // מסירים פיסוק ואימוג'ים לפני ההשוואה — "הצטרפו לקבוצה >>" הוא עדיין זבל.
  const t = title.replace(/[^\p{L}\p{N}\s]/gu, " ").replace(/\s+/g, " ").trim();
  if (t.length < 3) return true;
  if (/^https?:\/\//i.test(title.trim())) return true;
  // ביטוי הזמנה קצר ("הצטרפו לקבוצה", "click here") מתאר את הכפתור, לא את הקבוצה.
  return JUNK_PREFIX_RE.test(t) && t.length <= 25;
}

export function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
}
