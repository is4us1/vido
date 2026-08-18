"use client";

import { useMemo, useState } from "react";
import type { Group } from "../lib/types";

const PAGE_SIZE = 48;

export interface CategoryOption {
  slug: string;
  name: string;
  emoji: string;
  count: number;
}

interface Props {
  groups: Group[];
  categories: CategoryOption[];
  /** כשמוגדר, מסנן הקטגוריות מוסתר (עמוד קטגוריה בודדת). */
  lockedCategory?: string;
}

type SortKey = "newest" | "title" | "relevance";

export default function GroupBrowser({ groups, categories, lockedCategory }: Props) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState(lockedCategory ?? "all");
  const [sort, setSort] = useState<SortKey>("newest");
  const [visible, setVisible] = useState(PAGE_SIZE);

  const filtered = useMemo(() => {
    const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);

    const matches = groups.filter((group) => {
      if (category !== "all" && group.category !== category) return false;
      if (!terms.length) return true;
      const haystack = `${group.title} ${group.description} ${group.tags.join(" ")}`.toLowerCase();
      // כל המילים חייבות להופיע — חיפוש AND, כמו שמשתמשים מצפים.
      return terms.every((term) => haystack.includes(term));
    });

    const sorted = [...matches];
    if (sort === "title") sorted.sort((a, b) => a.title.localeCompare(b.title, "he"));
    else if (sort === "relevance") sorted.sort((a, b) => b.categoryScore - a.categoryScore);
    else sorted.sort((a, b) => b.firstSeen.localeCompare(a.firstSeen));
    return sorted;
  }, [groups, query, category, sort]);

  const shown = filtered.slice(0, visible);

  function pick(slug: string) {
    setCategory(slug);
    setVisible(PAGE_SIZE);
  }

  return (
    <>
      <div className="toolbar">
        <div className="search-row">
          <input
            className="search-input"
            type="search"
            placeholder="חיפוש חופשי — נושא, עיר, מילה מהתיאור…"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setVisible(PAGE_SIZE);
            }}
            aria-label="חיפוש קבוצות"
          />
          <select
            className="select"
            value={sort}
            onChange={(e) => setSort(e.target.value as SortKey)}
            aria-label="מיון"
          >
            <option value="newest">הכי חדשות</option>
            <option value="title">לפי שם</option>
            <option value="relevance">התאמה לקטגוריה</option>
          </select>
        </div>

        {!lockedCategory && (
          <div className="chips" role="group" aria-label="סינון לפי קטגוריה">
            <button className="chip" aria-pressed={category === "all"} onClick={() => pick("all")}>
              הכול <span className="count">{groups.length}</span>
            </button>
            {categories.map((cat) => (
              <button
                key={cat.slug}
                className="chip"
                aria-pressed={category === cat.slug}
                onClick={() => pick(cat.slug)}
              >
                <span aria-hidden>{cat.emoji}</span> {cat.name}{" "}
                <span className="count">{cat.count}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      <p className="result-count">
        {filtered.length === 0
          ? "לא נמצאו קבוצות שמתאימות לחיפוש"
          : `${filtered.length.toLocaleString("he-IL")} קבוצות`}
      </p>

      <div className="grid">
        {shown.map((group) => (
          <GroupCard key={group.id} group={group} categories={categories} />
        ))}
      </div>

      {visible < filtered.length && (
        <button className="btn load-more" onClick={() => setVisible((v) => v + PAGE_SIZE)}>
          הצג עוד {Math.min(PAGE_SIZE, filtered.length - visible)} קבוצות
        </button>
      )}
    </>
  );
}

function GroupCard({ group, categories }: { group: Group; categories: CategoryOption[] }) {
  const [copied, setCopied] = useState(false);
  const cat = categories.find((c) => c.slug === group.category);

  async function copy() {
    try {
      await navigator.clipboard.writeText(group.url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }

  return (
    <article className="card">
      <h3>{group.title}</h3>
      {group.description && <p className="desc">{group.description}</p>}
      <div className="card-meta">
        <span className="badge">
          {cat?.emoji} {cat?.name ?? "כללי"}
        </span>
      </div>
      <div className="card-actions">
        <a className="btn btn-primary" href={group.url} target="_blank" rel="noopener noreferrer nofollow">
          פתח בוואטסאפ
        </a>
        <button className="btn" onClick={copy}>
          {copied ? "הועתק ✓" : "העתק קישור"}
        </button>
      </div>
    </article>
  );
}
