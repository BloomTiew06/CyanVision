// Tells the browser app whether the assistant relay is configured, without revealing the key.
export default function handler(req, res) {
  const enabled = Boolean(process.env.AI_API_KEY && process.env.AI_MODEL);
  res.setHeader("Cache-Control", "no-store");
  res.status(200).json({ enabled, model: enabled ? process.env.AI_MODEL : "" });
}
