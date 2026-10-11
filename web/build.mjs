// Builds the browser version of LARIS into dist/ for Vercel.
// The Streamlit app runs inside the visitor's browser with stlite (Streamlit on WebAssembly), so the
// deployment is a static site plus one small function (api/ai) that holds the assistant's API key.
//
//   node web/build.mjs            -> dist/index.html and dist/app/** (the Python app and its data)
//
// Forecast data comes from web/outputs/ (refresh it with: python web/export_outputs.py <outputs folder>).

import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const DIST = join(ROOT, "dist");
const APP = join(DIST, "app");

// Offline-only scripts that the app never imports (they need scikit-learn and the raw data).
const SKIP_PY = new Set(["pipeline.py", "make_mock_data.py", "budget_sim.py"]);

rmSync(DIST, { recursive: true, force: true });
mkdirSync(APP, { recursive: true });

const files = []; // paths inside the app, relative to its working directory

function add(src, dest) {
  mkdirSync(dirname(join(APP, dest)), { recursive: true });
  cpSync(join(ROOT, src), join(APP, dest));
  files.push(dest.split("\\").join("/"));
}

function addDir(dir, filter, destDir = dir) {
  for (const name of readdirSync(join(ROOT, dir)).sort()) {
    const p = join(dir, name);
    if (statSync(join(ROOT, p)).isFile() && filter(name)) add(p, join(destDir, name));
  }
}

addDir(".", (n) => n.endsWith(".py") && !SKIP_PY.has(n));
addDir("views", (n) => n.endsWith(".py"));
addDir("workspace", (n) => n.endsWith(".py"));
addDir("assets", () => true);
add("product_settings.csv", "product_settings.csv");
if (!existsSync(join(ROOT, "web/outputs/metrics.json"))) {
  throw new Error("web/outputs/ is missing. Run: python web/export_outputs.py outputs");
}
addDir("web/outputs", () => true, "outputs");

// .streamlit/config.toml -> flat "section.key" settings, which is the form stlite accepts.
const streamlitConfig = { "client.toolbarMode": "viewer", "server.fileWatcherType": "none" };
let section = "";
for (const line of readFileSync(join(ROOT, ".streamlit/config.toml"), "utf8").split(/\r?\n/)) {
  const s = line.trim();
  if (!s || s.startsWith("#")) continue;
  const head = s.match(/^\[(.+)\]$/);
  if (head) { section = head[1].trim(); continue; }
  const kv = s.match(/^([A-Za-z0-9_]+)\s*=\s*(.+)$/);
  if (!kv) continue;
  let v = kv[2].replace(/\s+#.*$/, "").trim();
  if (/^".*"$/.test(v)) v = v.slice(1, -1);
  else if (v === "true" || v === "false") v = v === "true";
  else if (!Number.isNaN(Number(v))) v = Number(v);
  streamlitConfig[section ? `${section}.${kv[1]}` : kv[1]] = v;
}

// A theme font given as "Name:https://stylesheet" crashes stlite's renderer (it has no Helmet provider), so the
// stylesheet is linked from index.html instead and Streamlit only gets the font name.
const fontLinks = new Set();
for (const [k, v] of Object.entries(streamlitConfig)) {
  const m = typeof v === "string" && v.match(/^([^:]+):(https:\/\/.+)$/);
  if (m && /font/i.test(k)) {
    streamlitConfig[k] = m[1];
    fontLinks.add(m[2]);
  }
}

// stlite and Pyodide load from the jsDelivr CDN; both can be pointed elsewhere for offline testing.
const STLITE = process.env.STLITE_BASE || "https://cdn.jsdelivr.net/npm/@stlite/browser@1.11.0/build";
const PYODIDE = process.env.PYODIDE_URL || null;

const template = readFileSync(join(ROOT, "web/index.html"), "utf8");
const html = template
  .replaceAll("__STLITE__", STLITE)
  .replace("__PYODIDE_URL__", JSON.stringify(PYODIDE))
  .replace("__FONTS__", [...fontLinks].map((u) => `<link rel="stylesheet" href="${u}" />`).join("\n  "))
  .replace("__FILES__", JSON.stringify(files))
  .replace("__STREAMLIT_CONFIG__", JSON.stringify(streamlitConfig))
  .replace("__BUILD__", new Date().toISOString().slice(0, 16).replace("T", " "));
writeFileSync(join(DIST, "index.html"), html);
cpSync(join(ROOT, "assets/laris_logo.svg"), join(DIST, "logo.svg"));

console.log(`Built dist/ with ${files.length} app files:`);
for (const f of files) console.log("  " + f);
