import Link from "next/link";
import { notFound } from "next/navigation";
import GroupBrowser, { type CategoryOption } from "../../GroupBrowser";
import { CATEGORIES, CATEGORY_BY_SLUG } from "../../../lib/categories";
import { loadDataset } from "../../../lib/store";

export const revalidate = 3600;

export function generateStaticParams() {
  return CATEGORIES.map((cat) => ({ slug: cat.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const cat = CATEGORY_BY_SLUG.get(slug);
  return {
    title: cat ? `${cat.name} — קבוצות וואטסאפ ישראליות | ווטסלינק` : "ווטסלינק",
  };
}

export default async function CategoryPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const category = CATEGORY_BY_SLUG.get(slug);
  if (!category) notFound();

  const { groups } = await loadDataset();
  const inCategory = groups.filter((g) => g.category === slug);

  const options: CategoryOption[] = CATEGORIES.map((cat) => ({
    slug: cat.slug,
    name: cat.name,
    emoji: cat.emoji,
    count: groups.filter((g) => g.category === cat.slug).length,
  }));

  return (
    <>
      <header className="site-header">
        <div className="container">
          <h1>
            {category.emoji} {category.name}
          </h1>
          <p>
            {inCategory.length.toLocaleString("he-IL")} קבוצות וואטסאפ ישראליות בקטגוריה הזו.
          </p>
        </div>
      </header>

      <main className="container">
        <p className="breadcrumb">
          <Link href="/">ווטסלינק</Link> ← {category.name}
        </p>
        {inCategory.length === 0 ? (
          <div className="empty">
            <h2>אין עדיין קבוצות בקטגוריה הזו</h2>
            <p>
              הרץ <code>npm run scrape</code> כדי לאסוף עוד, או <Link href="/">חזור לכל הקבוצות</Link>.
            </p>
          </div>
        ) : (
          <GroupBrowser groups={inCategory} categories={options} lockedCategory={slug} />
        )}
      </main>
    </>
  );
}
