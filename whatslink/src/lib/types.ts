/** טיפוסי הליבה של ווטסלינק. */

export interface Group {
  /** קוד ההזמנה של הקבוצה — משמש כמזהה ייחודי. */
  id: string;
  url: string;
  title: string;
  description: string;
  /** slug של הקטגוריה מתוך CATEGORIES. */
  category: string;
  /** ניקוד הביטחון בסיווג (0 = ברירת מחדל "כללי"). */
  categoryScore: number;
  /** תתי-נושאים שזוהו בטקסט, לשימוש בחיפוש. */
  tags: string[];
  israeli: boolean;
  israeliScore: number;
  israeliSignals: string[];
  /** מזהה המקור שממנו נאסף הקישור. */
  source: string;
  /** העמוד המדויק שבו נמצא הקישור. */
  sourceUrl: string;
  firstSeen: string;
  lastSeen: string;
}

export interface Source {
  id: string;
  name: string;
  /** עמודי הפתיחה לזחילה. */
  startUrls: string[];
  /**
   * ביטויים רגולריים (כמחרוזות) שקישור חייב להתאים לאחד מהם כדי שנמשיך אליו.
   * ריק = לא זוחלים הלאה, רק עמודי הפתיחה.
   */
  followPatterns: string[];
  /** ביטויים רגולריים לקישורים שלא נזחל אליהם גם אם התאימו למעלה. */
  ignorePatterns?: string[];
  maxPages?: number;
  enabled: boolean;
  /**
   * true כשידוע שהאתר כולו ישראלי — מוסיף ניקוד ישראליות
   * לקבוצות שהטקסט שלהן דל מכדי להכריע לבד.
   */
  assumeIsraeli?: boolean;
  notes?: string;
}

export interface Dataset {
  updatedAt: string;
  groups: Group[];
}

export interface Category {
  slug: string;
  name: string;
  emoji: string;
  /** מילות מפתח עם משקל — ככל שהמשקל גבוה יותר, הסימן חזק יותר. */
  keywords: Array<[string, number]>;
}

export interface ScrapeStats {
  source: string;
  pagesFetched: number;
  pagesSkippedByRobots: number;
  linksFound: number;
  uniqueGroups: number;
  israeliKept: number;
  nonIsraeliDropped: number;
  errors: string[];
}
