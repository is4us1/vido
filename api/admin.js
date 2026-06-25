// /api/admin — נקודת קצה מוגנת לדשבורד. דורשת Bearer ADMIN_TOKEN.
const SB = process.env.SUPABASE_URL;
const KEY = process.env.SUPABASE_SERVICE_KEY;
const ADMIN = process.env.ADMIN_TOKEN;

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
  res.setHeader("Access-Control-Allow-Headers", "Content-Type,Authorization");
  res.setHeader("Access-Control-Allow-Methods", "POST,OPTIONS");
  if (req.method === "OPTIONS") return res.status(204).end();
  if (req.method !== "POST") return res.status(405).json({ error: "POST only" });
  if (!SB || !KEY || !ADMIN) return res.status(500).json({ error: "env vars missing (SUPABASE_URL / SUPABASE_SERVICE_KEY / ADMIN_TOKEN)" });

  const auth = (req.headers.authorization || "").replace(/^Bearer\s+/i, "");
  if (auth !== ADMIN) return res.status(401).json({ error: "unauthorized" });

  const b = typeof req.body === "string" ? JSON.parse(req.body || "{}") : (req.body || {});
  try {
    if (b.action === "load") {
      const [lr, er] = await Promise.all([
        sb("leads?select=*&order=created_at.desc&limit=1000"),
        sb("events?select=type,detail,created_at&order=created_at.desc&limit=3000"),
      ]);
      const leads = lr.ok ? await lr.json() : [];
      const events = er.ok ? await er.json() : [];
      return res.status(200).json({ leads, events });
    }
    if (b.action === "addLead") {
      const row = {
        name: b.name || null, email: b.email || null, phone: b.phone || null,
        source: b.source || "manual", status: b.status || "new", notes: b.notes || "",
      };
      const r = await sb("leads", { method: "POST", headers: { Prefer: "return=representation" }, body: JSON.stringify(row) });
      if (!r.ok) throw new Error("db " + r.status);
      const d = await r.json();
      return res.status(200).json({ ok: true, lead: d[0] });
    }
    if (b.action === "updateLead") {
      const patch = { updated_at: new Date().toISOString() };
      ["name", "email", "phone", "status", "notes", "source"].forEach((k) => { if (b[k] !== undefined) patch[k] = b[k]; });
      const r = await sb(`leads?id=eq.${encodeURIComponent(b.id)}`, { method: "PATCH", body: JSON.stringify(patch) });
      if (!r.ok) throw new Error("db " + r.status);
      return res.status(200).json({ ok: true });
    }
    if (b.action === "deleteLead") {
      const r = await sb(`leads?id=eq.${encodeURIComponent(b.id)}`, { method: "DELETE" });
      if (!r.ok) throw new Error("db " + r.status);
      return res.status(200).json({ ok: true });
    }
    return res.status(400).json({ error: "unknown action" });
  } catch (e) {
    return res.status(500).json({ error: String((e && e.message) || e) });
  }
}
