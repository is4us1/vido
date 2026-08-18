/**
 * זיהוי "ישראליות" של קבוצה.
 *
 * המטרה: לשמור רק קבוצות ישראליות. אין דרך ודאית לדעת מי חבר בקבוצה,
 * ולכן זו הערכה מצטברת של סימנים מהטקסט הגלוי: עברית, שמות ערים,
 * מספרי טלפון ישראליים, מונחים מקומיים ומטבע.
 */

const HEBREW_RE = /[֐-׿]/g;
const ARABIC_RE = /[؀-ۿ]/g;

/** ערים, אזורים ויישובים נפוצים בישראל. */
export const ISRAELI_PLACES = [
  "תל אביב", "תל־אביב", "ת\"א", "ירושלים", "חיפה", "באר שבע", "ראשון לציון",
  "פתח תקווה", "אשדוד", "נתניה", "חולון", "בני ברק", "רמת גן", "אשקלון",
  "רחובות", "בת ים", "הרצליה", "כפר סבא", "חדרה", "מודיעין", "רעננה",
  "רמת השרון", "גבעתיים", "לוד", "רמלה", "נצרת", "עכו", "אילת", "טבריה",
  "צפת", "קריית שמונה", "דימונה", "יבנה", "נס ציונה", "קריות", "אור יהודה",
  "ראש העין", "גבעת שמואל", "מעלה אדומים", "ביתר עילית", "אלעד", "יהוד",
  "כרמיאל", "נהריה", "עפולה", "בית שמש", "אריאל", "שדרות", "נתיבות",
  "אופקים", "מגדל העמק", "יקנעם", "זכרון יעקב", "פרדס חנה", "כפר יונה",
  "השרון", "גוש דן", "המרכז", "הצפון", "הדרום", "השפלה", "הגליל", "הנגב",
  "יהודה ושומרון", "עוטף עזה", "מישור החוף", "ישראל", "הארץ",
];

const ISRAELI_TERMS = [
  "ישראל", "ישראלי", "ישראלים", "ישראליות", "עברית", "שקל", "ש\"ח", "שקלים",
  "צה\"ל", "מילואים", "קופת חולים", "כללית", "מכבי שירותי בריאות", "מאוחדת",
  "ביטוח לאומי", "רבנות", "כשרות", "שבת", "חגים", "סוכות", "פסח",
  "בגרות", "פסיכומטרי", "מד\"א", "עיריית", "מועצה אזורית", "רשות מקומית",
  "אגד", "רב קו", "רב־קו", "קופיקס", "רמי לוי", "שופרסל", "יד2", "יד שתיים",
];

/** מדדים שמרמזים שהקבוצה אינה ישראלית. */
const FOREIGN_MARKERS = [
  "india", "pakistan", "nigeria", "indonesia", "brasil", "brazil", "philippines",
  "bangladesh", "usa only", "uk only", "arabic only", "türkiye", "россия",
  "हिंदी", "اردو", "বাংলা",
];

function ratio(text: string, re: RegExp): number {
  const letters = text.replace(/[^\p{L}]/gu, "");
  if (!letters.length) return 0;
  const matches = text.match(re);
  return (matches?.length ?? 0) / letters.length;
}

export interface IsraeliVerdict {
  israeli: boolean;
  score: number;
  signals: string[];
}

/**
 * מחזיר ניקוד ישראליות. סף הקבלה הוא 3.
 *
 * @param text טקסט חופשי — כותרת + תיאור + הקשר מהעמוד.
 * @param assumeIsraeli האם המקור עצמו הוא אתר ישראלי ייעודי.
 */
export function scoreIsraeli(text: string, assumeIsraeli = false): IsraeliVerdict {
  const lower = text.toLowerCase();
  const signals: string[] = [];
  let score = 0;

  const hebRatio = ratio(text, HEBREW_RE);
  if (hebRatio >= 0.5) {
    score += 4;
    signals.push("עברית דומיננטית");
  } else if (hebRatio >= 0.2) {
    score += 3;
    signals.push("עברית");
  } else if (hebRatio > 0.03) {
    score += 1;
    signals.push("מעט עברית");
  }

  const place = ISRAELI_PLACES.find((p) => text.includes(p));
  if (place) {
    score += 3;
    signals.push(`מקום: ${place}`);
  }

  const term = ISRAELI_TERMS.find((t) => text.includes(t));
  if (term) {
    score += 2;
    signals.push(`מונח מקומי: ${term}`);
  }

  // טלפון ישראלי: +972 / 972 / 05X-XXXXXXX
  if (/(?:\+?972[-\s]?|\b0)5\d[-\s]?\d{3}[-\s]?\d{4}\b/.test(text)) {
    score += 3;
    signals.push("טלפון ישראלי");
  }

  if (/\.co\.il\b/.test(lower)) {
    score += 2;
    signals.push("דומיין ‎.co.il");
  }

  if (assumeIsraeli) {
    score += 2;
    signals.push("מקור ישראלי");
  }

  const foreign = FOREIGN_MARKERS.find((m) => lower.includes(m));
  if (foreign) {
    score -= 5;
    signals.push(`סימן זר: ${foreign}`);
  }

  // ערבית ללא עברית כלל — כנראה לא קבוצה ישראלית.
  if (ratio(text, ARABIC_RE) > 0.3 && hebRatio < 0.05) {
    score -= 4;
    signals.push("ערבית ללא עברית");
  }

  return { israeli: score >= 3, score, signals };
}

export const ISRAELI_THRESHOLD = 3;
