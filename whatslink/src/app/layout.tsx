import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ווטסלינק — קבוצות וואטסאפ ישראליות לפי קטגוריות",
  description:
    "אינדקס של קישורי הזמנה לקבוצות וואטסאפ ישראליות שפורסמו בפומבי, מסודר לפי קטגוריות עם חיפוש חופשי.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="he" dir="rtl">
      <body>
        {children}
        <footer className="site-footer">
          <div className="container">
            <p>
              ווטסלינק מרכז קישורי הזמנה שפורסמו בפומבי באתרי אינדקס. הקבוצות אינן בבעלותנו
              ואיננו אחראים לתוכן שמתפרסם בהן. מפעיל קבוצה שמעוניין בהסרה מוזמן לפתוח issue.
            </p>
            <p>
              WhatsApp הוא סימן מסחרי של Meta Platforms, Inc. לאתר זה אין קשר או שיוך אליה.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
