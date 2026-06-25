// /api/collect — נקודת קצה ציבורית: מקבלת אירועי שימוש ולידים מ-vido.
// משתמשת ב-service key בצד השרת בלבד (לא נחשף ללקוח).
const SB = process.env.SUPABASE_URL;
const KEY = process.env.SUPABASE_SERVICE_KEY;

function sb(path, opts = {}) {
  return fetch(`${SB}/rest/v1/${path}`, {
    ...opts,
    headers: {
      apikey: KEY,
      Authorization: `Bearer ${KEY}`,
      "Content-Type": "application/json",
      ...(opts.headers || {}),
    },
  });
}

export default async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  res.setHeader("Access-Control-Allow-Methods", "POST,OPTIONS");
  if (req.method === "OPTIONS") return res.status(204).end();
  if (req.method !== "POST") return res.status(405).json({ error: "POST only" });
  if (!SB || !KEY) return res.status(500).json({ error: "Supabase env vars missing" });

  try {
    const b = typeof req.body === "string" ? JSON.parse(req.body || "{}") : (req.body || {});

    if (b.kind === "lead") {
      const row = {
        name: b.name || null,
        email: b.email || null,
        phone: b.phone || null,
        source: (b.source || "vido").slice(0, 60),
        notes: (b.notes || "").slice(0, 500),
      };
      const r = await sb("leads", { method: "POST", body: JSON.stringify(row) });
      if (!r.ok) throw new Error("db " + r.status);
      return res.status(200).json({ ok: true });
    }

    // ברירת מחדל: אירוע שימוש
    const ev = {
      type: String(b.type || "unknown").slice(0, 40),
      detail: String(b.detail || "").slice(0, 120),
      session: String(b.session || "").slice(0, 40),
    };
    const r = await sb("events", { method: "POST", body: JSON.stringify(ev) });
    if (!r.ok) throw new Error("db " + r.status);
    return res.status(200).json({ ok: true });
  } catch (e) {
    return res.status(500).json({ error: String((e && e.message) || e) });
  }
}
