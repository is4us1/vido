import Link from "next/link";
import GroupBrowser, { type CategoryOption } from "./GroupBrowser";
import { CATEGORIES } from "../lib/categories";
import { loadDataset } from "../lib/store";

// הדאטה מגיעה מקובץ בדיסק — נטענת מחדש בכל build ואחת לשעה בזמן ריצה.
export const revalidate = 3600;

export default async function HomePage() {
  const { groups, updatedAt } = await loadDataset();

  const counts = new Map<string, number>();
  for (const group of groups) counts.set(group.category, (counts.get(group.category) ?? 0) + 1);

  const categories: CategoryOption[] = CATEGORIES.map((cat) => ({
    slug: cat.slug,
    name: cat.name,
    emoji: cat.emoji,
    count: counts.get(cat.slug) ?? 0,
  }))
    .filter((cat) => cat.count > 0)
    .sort((a, b) => b.count - a.count);

  return (
    <>
      <header className="site-header">
        <div className="container">
          <h1>ווטסלינק</h1>
          <p>
            כל קישורי ההזמנה לקבוצות וואטסאפ ישראליות שפורסמו בפומבי — במקום אחד,
            מסודרים לפי קטגוריות ועם חיפוש חופשי.
          </p>
          <div className="header-stats">
            <div>
              <strong>{groups.length.toLocaleString("he-IL")}</strong>
              קבוצות במאגר
            </div>
            <div>
              <strong>{categories.length}</strong>
              קטגוריות פעילות
            </div>
            <div>
              <strong>
                {updatedAt
                  ? new Date(updatedAt).toLocaleDateString("he-IL", { day: "numeric", month: "long" })
                  : "—"}
              </strong>
              עודכן לאחרונה
            </div>
          </div>
        </div>
      </header>

      <main className="container">
        {groups.length === 0 ? <EmptyState /> : (
          <GroupBrowser groups={groups} categories={categories} />
        )}

        {categories.length > 0 && (
          <nav className="chips" style={{ marginTop: 28 }} aria-label="עמודי קטגוריה">
            {categories.map((cat) => (
              <Link key={cat.slug} className="chip" href={`/category/${cat.slug}`}>
                <span aria-hidden>{cat.emoji}</span> {cat.name}
              </Link>
            ))}
          </nav>
        )}
      </main>
    </>
  );
}

function EmptyState() {
  return (
    <div className="empty">
      <h2>המאגר עדיין ריק</h2>
      <p>
        הוסף מקורות לאיסוף בקובץ <code>data/sources.json</code> והרץ:
      </p>
      <p>
        <code>npm run scrape:dry</code> — לבדיקה ללא כתיבה
        <br />
        <code>npm run scrape</code> — לאיסוף אמיתי
      </p>
      <p>
        לתצוגה מקדימה של הממשק עם נתוני דמו:
        <br />
        <code>cp data/groups.sample.json data/groups.json</code>
      </p>
    </div>
  );
}
