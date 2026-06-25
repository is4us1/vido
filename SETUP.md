# הקמת הדשבורד וה-CRM של vido

הכל כבר בקוד. נשאר רק לחבר בסיס נתונים (Supabase) ולהגדיר 3 משתני סביבה ב-Vercel. ~5 דקות.

## 1. Supabase
1. היכנס ל-supabase.com → New project (שם חופשי, שמור את הסיסמה).
2. Project → **SQL Editor** → New query → הדבק את כל התוכן של `schema.sql` → **Run**.
3. Project → **Settings → API**, קח שני ערכים:
   - **Project URL** (למשל `https://abcd.supabase.co`)
   - **service_role** key (תחת Project API keys — זה הסודי, לא ה-anon).

## 2. משתני סביבה ב-Vercel
Vercel → הפרויקט `vido` → **Settings → Environment Variables** → הוסף שלושה:

| Name | Value |
|------|-------|
| `SUPABASE_URL` | ה-Project URL מ-Supabase |
| `SUPABASE_SERVICE_KEY` | מפתח ה-service_role |
| `ADMIN_TOKEN` | סיסמה שתמציא — לכניסה לדשבורד |

(אם הסוכן ב-vido עובד, כבר יש לך גם `ANTHROPIC_API_KEY` — משאירים.)

## 3. Redeploy
Vercel → Deployments → הפריסה האחרונה → ⋯ → **Redeploy** (כדי שהמשתנים ייכנסו לתוקף).

## 4. שימוש
- **הדשבורד:** `https://vido-cyan.vercel.app/dashboard.html` → הזן את `ADMIN_TOKEN`.
- **לידים** נכנסים אוטומטית כשמישהו משאיר אימייל ב-vido, או ידנית מהדשבורד.
- **שימוש** נרשם אוטומטית בכל פעם שמישהו מייצר/עורך וידאו.

## אבטחה
- ה-service key חי רק בצד השרת (בפונקציות `/api`), לא נחשף בדפדפן.
- הדשבורד מוגן ב-`ADMIN_TOKEN`. שמור אותו פרטי.
- הטבלאות עם RLS פעיל — אי אפשר לגשת אליהן בלי המפתח הסודי.
