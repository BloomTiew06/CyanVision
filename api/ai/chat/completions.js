// Server-side relay for the LARIS assistant on the Vercel deployment.
// The browser app posts OpenAI-style chat requests here; this function adds the API key from the
// Vercel environment (AI_API_KEY, AI_MODEL, optional AI_BASE_URL), so the key never reaches the browser.

const MAX_BODY = 60_000;      // characters; the assistant's requests are far smaller
const MAX_TOKENS = 800;       // cap per reply, so the shared key can't be drained by long generations

export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return res.status(405).json({ error: "POST only" });
  }
  const key = process.env.AI_API_KEY;
  const model = process.env.AI_MODEL;
  if (!key || !model) {
    return res.status(503).json({ error: "The assistant isn't configured on this deployment." });
  }
  const origin = req.headers.origin;
  const host = req.headers["x-forwarded-host"] || req.headers.host;
  if (origin && host && new URL(origin).host !== host) {
    return res.status(403).json({ error: "Requests must come from the LARIS app." });
  }

  const raw = typeof req.body === "string" ? req.body : JSON.stringify(req.body || {});
  if (raw.length > MAX_BODY) return res.status(413).json({ error: "Request too large." });
  let payload;
  try {
    payload = JSON.parse(raw);
  } catch {
    return res.status(400).json({ error: "Invalid JSON." });
  }
  if (!Array.isArray(payload.messages)) return res.status(400).json({ error: "messages is required." });

  payload.model = model;
  payload.stream = false;
  payload.max_tokens = Math.min(Number(payload.max_tokens) || MAX_TOKENS, MAX_TOKENS);

  const base = (process.env.AI_BASE_URL || "https://api.openai.com/v1").replace(/\/+$/, "");
  try {
    const upstream = await fetch(`${base}/chat/completions`, {
      method: "POST",
      headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(25_000),
    });
    const text = await upstream.text();
    const retryAfter = upstream.headers.get("retry-after");
    if (retryAfter) res.setHeader("Retry-After", retryAfter);
    res.setHeader("Content-Type", "application/json");
    return res.status(upstream.status).send(text);
  } catch {
    return res.status(504).json({ error: "The AI service couldn't be reached or took too long." });
  }
}
