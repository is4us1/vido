# ווטסלינק

אינדקס של קישורי הזמנה לקבוצות וואטסאפ **ישראליות** שפורסמו בפומבי, מסודר אוטומטית
לפי קטגוריות, עם חיפוש חופשי, עמוד לכל קטגוריה ו-API.

<div dir="ltr">

```
data/sources.json  →  crawl  →  זיהוי ישראליות  →  סיווג לקטגוריה  →  data/groups.json  →  אתר Next.js
```

</div>

## מה יש כאן

| רכיב | קובץ | תפקיד |
| --- | --- | --- |
| זחלן | `src/scraper/crawl.ts` | BFS על אתר מקור, נשאר בדומיין, עוקב רק אחרי דפוסים מאושרים |
| הורדה בנימוס | `src/scraper/fetcher.ts` | בודק `robots.txt`, מגביל קצב לכל דומיין, retry עם השהיה מצטברת |
| `robots.txt` | `src/scraper/robots.ts` | פרסור מלא: קבוצות User-agent, Allow/Disallow לפי תחילית ארוכה, Crawl-delay |
| חילוץ | `src/scraper/extract.ts` | מוצא קישורי `chat.whatsapp.com` ואוסף כותרת ותיאור מההקשר |
| סינון ישראליות | `src/lib/israeli.ts` | ניקוד לפי עברית, ערים, טלפון ישראלי, מונחים מקומיים |
| סיווג | `src/lib/classify.ts` + `src/lib/categories.ts` | 23 קטגוריות עם מילות מפתח משוקללות |
| אתר | `src/app/` | Next.js 15, RTL, מצב כהה, חיפוש בצד לקוח |
| API | `src/app/api/groups/route.ts` | `GET /api/groups?category=&q=&limit=&offset=` |

## התקנה והרצה

```bash
npm install
npm run dev            # http://localhost:3000
```

המאגר מגיע ריק. לתצוגה מקדימה עם נתוני דמו:

```bash
cp data/groups.sample.json data/groups.json
```

> קבצי הדמו מכילים קודי הזמנה מזויפים (`DEMO…`) — הם לא מובילים לשום קבוצה אמיתית.

## איסוף קבוצות

1. ערוך את `data/sources.json` והוסף אתרי מקור:

```json
{
  "id": "my-directory",
  "name": "ספריית קבוצות",
  "startUrls": ["https://example.co.il/whatsapp-groups"],
  "followPatterns": ["/whatsapp-groups(/|\\?page=)", "/category/"],
  "ignorePatterns": ["/login", "/search"],
  "maxPages": 60,
  "enabled": true,
  "assumeIsraeli": true
}
```

* `followPatterns` — ביטויים רגולריים; ממשיכים רק לקישורים שתואמים לאחד מהם.
* `assumeIsraeli` — הפעל רק כשהאתר כולו ישראלי; מוסיף ניקוד לקבוצות עם טקסט דל.

2. הרץ:

```bash
npm run scrape:dry                    # בודק הכול, לא כותב כלום
npm run scrape                        # איסוף אמיתי לתוך data/groups.json
npm run scrape -- --source=my-directory --max-pages=30
```

הריצה מדפיסה לכל מקור: כמה עמודים נזחלו, כמה נחסמו ב-`robots.txt`, כמה קישורים
נמצאו, כמה עברו את סינון הישראליות וכמה נפסלו — ואז פירוט לפי קטגוריה.

3. אחרי שינוי מילות מפתח, אפשר לסווג מחדש בלי לזחול שוב:

```bash
npm run reclassify
npm run reclassify -- --drop-non-israeli   # גם מנקה קבוצות שכבר לא עוברות את הסף
```

## בדיקות

```bash
npm test    # 30 בדיקות על החילוץ, הסיווג, סינון הישראליות, robots.txt והמיזוג
npm run lint
```

הבדיקות רצות אופליין מול `src/scraper/fixtures/*.html` — אין צורך ברשת.

## איסוף אוטומטי

`.github/workflows/scrape.yml` מריץ איסוף שבועי ודוחף את `data/groups.json` המעודכן.
מופעל רק אחרי שהפרויקט יושב בריפו משלו ויש בו מקורות פעילים.

## פריסה

הפרויקט הוא Next.js רגיל. ב-Vercel: `npm run build`, ללא הגדרות מיוחדות.
הדאטה נקראת מהקובץ בדיסק, אז אין צורך בדאטהבייס.

## גבולות ואחריות

* **רק מקורות ציבוריים.** הזחלן קורא עמודי אינדקס פתוחים. הוא לא נכנס לוואטסאפ,
  לא מצטרף לקבוצות, לא קורא הודעות ולא נוגע ב-API של WhatsApp.
* **`robots.txt` נאכף.** עמוד אסור פשוט נדלג, וזה נספר בסטטיסטיקה.
* **קצב מרוסן.** ברירת מחדל 1.5 שניות בין בקשות לאותו דומיין, ו-`Crawl-delay` של
  האתר גובר אם הוא גבוה יותר. ה-User-Agent מזהה את עצמו עם כתובת ליצירת קשר.
* לפני הפעלת מקור — בדוק את תנאי השימוש שלו. אתר שאוסר איסוף אוטומטי בתנאים
  שלו לא צריך להיות ב-`sources.json` גם אם ה-`robots.txt` שלו מתיר.
* הקבוצות אינן בבעלות הפרויקט ואין שליטה על התוכן שמתפרסם בהן.
* קישורי הזמנה מתיישנים. `lastSeen` מאפשר לזהות רשומות ישנות; אימות חי של הקישור
  מול וואטסאפ **לא** מיושם בכוונה.
* `robots: noindex` מוגדר בעמודי האתר כדי לא לשכפל את תוכן אתרי המקור לתוצאות חיפוש.

## מבנה התיקיות

```
data/
  sources.json         מקורות לאיסוף
  groups.json          המאגר (נוצר על ידי הזחלן)
  groups.sample.json   נתוני דמו לתצוגה מקדימה
src/
  lib/                 טיפוסים, קטגוריות, סיווג, סינון ישראליות, קריאה/כתיבה
  scraper/             fetcher, robots, extract, crawl, CLI, בדיקות, fixtures
  app/                 עמודי Next.js, קומפוננטת הדפדוף וה-API
```
