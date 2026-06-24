# vido

עורך + יוצר וידאו שרץ **100% מקומית בדפדפן**. הקבצים לא עוזבים את המכשיר.
מנוע: ffmpeg.wasm (גרסת single-thread, לא דורש headers מיוחדים → רץ ישר על GitHub Pages).

## מה יש
- **עריכה:** חיתוך, אנכי/ריבוע, מהירות, דחיסה, השתקה, חילוץ אודיו, GIF, היפוך, פייד, כיתוב, רזולוציה + סוכן עברית.
- **יצירה:** אודיו → וידאו עם ויזואלייזר וכותרת · תמונות → סליידשואו עם מוזיקה.

## הפעלה (GitHub Pages)
1. Settings → Pages → Branch: `main` → `/ (root)` → Save.
2. הכתובת תהיה: `https://<user>.github.io/vido/`

## הסוכן (העברית → תוכנית עריכה)
בהארחה עצמית קריאה ישירה ל-Anthropic נחסמת (CORS + מפתח).
פתח "הגדרות סוכן" באתר והדבק כתובת Cloudflare Worker שמתווך ל-API.
**שאר הכלים — כל העריכה הידנית וכל היצירה — עובדים בלי זה.**

## פריסה ל-Vercel (כולל סוכן עובד)
1. vercel.com → Add New → Project → Import את `is4us1/vido`.
2. Framework Preset: **Other** · בלי build command. Deploy.
3. Project → Settings → Environment Variables → הוסף:
   `ANTHROPIC_API_KEY` = המפתח שלך מ-console.anthropic.com → Save → Redeploy.
4. הסוכן בעברית יעבוד אוטומטית דרך `/api/agent` (המפתח נשאר בצד השרת, לא נחשף).
