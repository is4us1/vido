import { NextResponse } from "next/server";
import { loadDataset } from "../../../lib/store";
import { CATEGORY_BY_SLUG } from "../../../lib/categories";

export const revalidate = 3600;

/**
 * GET /api/groups?category=jobs&q=תל+אביב&limit=50&offset=0
 * מחזיר JSON של הקבוצות — נוח לשילוב באתר אחר או בבוט.
 */
export async function GET(request: Request) {
  const url = new URL(request.url);
  const category = url.searchParams.get("category");
  const q = (url.searchParams.get("q") ?? "").trim().toLowerCase();
  const limit = Math.min(Number(url.searchParams.get("limit") ?? 100) || 100, 500);
  const offset = Math.max(Number(url.searchParams.get("offset") ?? 0) || 0, 0);

  if (category && !CATEGORY_BY_SLUG.has(category)) {
    return NextResponse.json({ error: "קטגוריה לא קיימת" }, { status: 400 });
  }

  const { groups, updatedAt } = await loadDataset();
  const terms = q.split(/\s+/).filter(Boolean);

  const filtered = groups.filter((group) => {
    if (category && group.category !== category) return false;
    if (!terms.length) return true;
    const haystack = `${group.title} ${group.description} ${group.tags.join(" ")}`.toLowerCase();
    return terms.every((term) => haystack.includes(term));
  });

  return NextResponse.json({
    updatedAt,
    total: filtered.length,
    offset,
    limit,
    groups: filtered.slice(offset, offset + limit),
  });
}
