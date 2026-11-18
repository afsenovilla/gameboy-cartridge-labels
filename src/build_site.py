# A page for browsing the downloaded labels: published-labels/index.html (made by download_published.py), one file with
# its data inside, opened from the folder in a browser: search, system and region filters, sorting, pages, a viewer.
#
#   python run.py py src/build_site.py [folder]
import html, json, os, sys

FOLDER = "published-labels"
SOURCE = "https://geon.github.io/gameboy-cartridge-labels/"

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cartridge labels</title>
<style>
:root{
  --page:#cfcdc6; --shell:#dedcd5; --well:#bdbbb3; --ink:#22241f; --muted:#5b5e53; --line:#aeaca4;
  --lcd:#8bac0f; --lcd-ink:#0f380f; --on:#306230; --on-ink:#e9ecdc; --focus:#0f380f;
  --font:"Segoe UI Variable Text","Segoe UI",system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif;
}
@media (prefers-color-scheme:dark){:root{
  --page:#1c201a; --shell:#262b23; --well:#303629; --ink:#e4e6da; --muted:#9ea493; --line:#3c4235;
  --on:#4b7a2c; --on-ink:#f2f5e6; --focus:#b7d84a;
}}
*{box-sizing:border-box}
html{scroll-padding-top:190px}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.45 var(--font)}
a{color:inherit}
:focus-visible{outline:3px solid var(--focus);outline-offset:2px}
header{padding:28px 20px 8px;max-width:1500px;margin:0 auto}
h1{margin:0;font:800 clamp(30px,5vw,52px)/1 var(--font);letter-spacing:-.03em}
header p{margin:8px 0 0;color:var(--muted);max-width:60ch}
.bar{position:sticky;top:0;z-index:5;background:var(--page);border-bottom:1px solid var(--line);padding:14px 20px}
.az{max-width:1500px;margin:12px auto 0;display:flex;gap:3px;overflow-x:auto;padding-bottom:2px}
.az button{flex:0 0 auto;min-width:32px;height:34px;border:0;border-radius:6px;background:transparent;color:var(--ink);font:650 14px var(--font);cursor:pointer;padding:0 8px}
.az button:hover:not(:disabled){background:var(--well)}
.az button[aria-pressed=true],.az button[aria-pressed=true]:hover:not(:disabled){background:var(--on);color:var(--on-ink)}
.az button:disabled{opacity:.3;cursor:default}
.bar-in{max-width:1500px;margin:0 auto;display:grid;gap:12px;grid-template-columns:minmax(240px,1fr) auto auto auto;align-items:center}
.lcd{display:flex;align-items:center;gap:12px;background:var(--lcd);color:var(--lcd-ink);border-radius:6px 6px 22px 6px;padding:9px 16px;
  box-shadow:inset 0 0 0 3px rgba(15,56,15,.35),inset 3px 3px 0 rgba(15,56,15,.25)}
.lcd input{flex:1;min-width:0;background:none;border:0;color:inherit;font:600 17px/1.2 ui-monospace,"Cascadia Mono",Consolas,monospace;outline:0}
.lcd input::placeholder{color:rgba(15,56,15,.62)}
.lcd:focus-within{outline:3px solid var(--focus);outline-offset:2px}
.lcd output{font:600 14px ui-monospace,"Cascadia Mono",Consolas,monospace;white-space:nowrap}
.seg{display:flex;border:1.5px solid var(--ink);border-radius:8px;overflow:hidden}
.seg button{border:0;background:transparent;color:var(--ink);padding:9px 13px;font:600 14px var(--font);cursor:pointer;white-space:nowrap}
.seg button+button{border-left:1.5px solid var(--ink)}
.seg button[aria-pressed=true]{background:var(--on);color:var(--on-ink)}
.seg small{font-weight:400;opacity:.8;margin-left:4px}
select{appearance:auto;background:var(--shell);color:var(--ink);border:1.5px solid var(--ink);border-radius:8px;padding:9px 10px;font:600 14px var(--font)}
main{max-width:1500px;margin:0 auto;padding:16px 20px 40px}
.meta{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:16px;color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:26px 20px;align-items:start}
.item{display:block;text-decoration:none;min-width:0;border-radius:4px}
.item .pic{display:block;background:var(--well);border-radius:3px;overflow:hidden}
.item img{display:block;width:100%;height:auto}
.item:hover .pic,.item:focus-visible .pic{outline:3px solid var(--on);outline-offset:3px}
.item b{display:block;margin-top:8px;font-weight:650;line-height:1.25;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.item span.s{display:block;color:var(--muted);font-size:13px;margin-top:2px}
.pages{display:flex;gap:6px;flex-wrap:wrap;align-items:center;justify-content:center;margin:34px 0 0}
.pages button{min-width:40px;height:40px;border:1.5px solid var(--ink);border-radius:8px;background:transparent;color:var(--ink);font:600 14px var(--font);cursor:pointer;padding:0 10px}
.pages button[aria-current=page]{background:var(--on);color:var(--on-ink);border-color:var(--on)}
.pages button:disabled{opacity:.35;cursor:default}
.pages i{font-style:normal;color:var(--muted);padding:0 4px}
.empty{padding:60px 0;text-align:center;color:var(--muted)}
.empty button{margin-top:12px;border:1.5px solid var(--ink);background:transparent;color:var(--ink);border-radius:8px;padding:9px 14px;font:600 14px var(--font);cursor:pointer}
footer{max-width:1500px;margin:0 auto;padding:0 20px 40px;color:var(--muted);font-size:13px}
dialog{border:0;padding:0;background:var(--shell);color:var(--ink);border-radius:10px;width:min(1000px,94vw);max-height:92vh;overflow:auto;box-shadow:0 20px 60px rgba(0,0,0,.45)}
dialog::backdrop{background:rgba(10,14,8,.72)}
.view{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(240px,1fr)}
.view .big{background:var(--well);display:flex;align-items:center;justify-content:center;padding:20px}
.view .big img{max-width:100%;max-height:78vh;height:auto;display:block}
.view .info{padding:22px;display:flex;flex-direction:column;gap:14px}
.view h2{margin:0;font:750 22px/1.15 var(--font);letter-spacing:-.01em}
.view dl{margin:0;display:grid;grid-template-columns:auto 1fr;gap:6px 14px}
.view dt{color:var(--muted)} .view dd{margin:0;overflow-wrap:anywhere}
.acts{display:flex;gap:8px;flex-wrap:wrap;margin-top:auto}
.acts a,.acts button{border:1.5px solid var(--ink);background:transparent;color:var(--ink);border-radius:8px;padding:9px 14px;font:600 14px var(--font);cursor:pointer;text-decoration:none}
.acts a.main{background:var(--on);border-color:var(--on);color:var(--on-ink)}
@media (max-width:900px){.bar-in{grid-template-columns:1fr 1fr}.lcd{grid-column:1/-1}.view{grid-template-columns:1fr}}
@media (max-width:560px){.bar-in{grid-template-columns:1fr}.seg{overflow-x:auto}.grid{grid-template-columns:repeat(2,1fr);gap:20px 14px}}
@media (prefers-reduced-motion:no-preference){.item .pic{transition:outline-offset .12s}}
</style>
</head>
<body>
<header>
  <h1>Cartridge labels</h1>
  <p>Restored labels of Game Boy, Game Boy Color and Game Boy Advance cartridges. Search by title or serial, then open one to see it large.</p>
</header>
<div class="bar"><div class="bar-in">
  <label class="lcd"><input id="q" type="search" placeholder="Title or serial" autocomplete="off" aria-label="Search title or serial"><output id="count" aria-live="polite"></output></label>
  <div class="seg" id="systems" role="group" aria-label="System"></div>
  <select id="region" aria-label="Region"></select>
  <select id="sort" aria-label="Sort by">
    <option value="title">Title A to Z</option>
    <option value="serial">Serial</option>
    <option value="photos">Most photos first</option>
  </select>
</div>
  <div class="az" id="az" role="group" aria-label="Starts with"></div>
</div>
<main>
  <div class="meta"><span id="range"></span></div>
  <div class="grid" id="grid"></div>
  <div class="empty" id="empty" hidden>No labels match. Clear the search or choose another system or region.<br><button id="clear">Clear filters</button></div>
  <nav class="pages" id="pages" aria-label="Pages"></nav>
</main>
<footer>__CREDIT__</footer>
<dialog id="view"><div class="view">
  <div class="big"><img id="vimg" alt=""></div>
  <div class="info">
    <h2 id="vtitle"></h2>
    <dl id="vdl"></dl>
    <div class="acts"><button id="prev">Previous</button><button id="next">Next</button><a id="vdl-link" class="main" download>Download</a><button id="close">Close</button></div>
  </div>
</div></dialog>
<script type="application/json" id="data">__DATA__</script>
<script>
const LABELS = JSON.parse(document.getElementById("data").textContent);
const FOLDER = "__FOLDER__";
const SYSTEMS = [["", "All"], ["dmg", "Game Boy"], ["cgb", "Game Boy Color"], ["agb", "Game Boy Advance"]];
const SYSTEM_NAME = {dmg: "Game Boy", cgb: "Game Boy Color", agb: "Game Boy Advance"};
const PER_PAGE = 48;
const fold = s => (s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
const regionOf = s => { const m = /-([A-Z]{3})(?:-\d)?$/.exec(s || ""); return m ? m[1] : "other"; };
const letterOf = t => { const c = fold(t).replace(/[^\p{L}\p{N}]/gu, "")[0] || ""; return /[a-z]/.test(c) ? c.toUpperCase() : /[0-9]/.test(c) ? "#" : "…"; };
for (const l of LABELS) { l.letter = letterOf(l.title); l.region = regionOf(l.serial); l.hay = fold([l.title, l.serial, l.release].join(" ")); }
const $ = id => document.getElementById(id);
let state = {q: "", s: "", r: "", l: "", o: "title", p: 1}, shown = [];

function readHash() {
  const h = new URLSearchParams(location.hash.slice(1));
  state = {q: h.get("q") || "", s: h.get("s") || "", r: h.get("r") || "", l: h.get("l") || "", o: h.get("o") || "title", p: parseInt(h.get("p")) || 1};
}
function writeHash(push) {
  const h = new URLSearchParams();
  if (state.q) h.set("q", state.q); if (state.s) h.set("s", state.s); if (state.r) h.set("r", state.r); if (state.l) h.set("l", state.l);
  if (state.o !== "title") h.set("o", state.o); if (state.p > 1) h.set("p", state.p);
  const url = location.pathname + (h.toString() ? "#" + h : "");
  push ? history.pushState(null, "", url) : history.replaceState(null, "", url);
}
function filtered(ignoreSystem, ignoreLetter) {
  const words = fold(state.q).split(/\s+/).filter(Boolean);
  return LABELS.filter(l => (ignoreSystem || !state.s || l.system === state.s) && (ignoreLetter || !state.l || l.letter === state.l) &&
    (!state.r || l.region === state.r) &&
    words.every(w => l.hay.includes(w)));
}
const sorters = {
  title: (a, b) => a.title.localeCompare(b.title, undefined, {sensitivity: "base", numeric: true}) || a.serial.localeCompare(b.serial),
  serial: (a, b) => a.serial.localeCompare(b.serial, undefined, {numeric: true}),
  photos: (a, b) => b.photos - a.photos || sorters.title(a, b),
};
function build() {
  const base = filtered(true);
  $("systems").innerHTML = "";
  for (const [key, name] of SYSTEMS) {
    const n = key ? base.filter(l => l.system === key).length : base.length;
    const b = document.createElement("button");
    b.type = "button"; b.setAttribute("aria-pressed", String(state.s === key));
    b.innerHTML = name + "<small>" + n + "</small>";
    b.onclick = () => { state.s = key; state.p = 1; update(true); };
    $("systems").append(b);
  }
  const has = new Set(filtered(false, true).map(l => l.letter));
  $("az").innerHTML = "";
  for (const k of ["", ..."ABCDEFGHIJKLMNOPQRSTUVWXYZ", "#", "…"]) {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = k || "All"; b.disabled = k !== "" && !has.has(k);
    b.setAttribute("aria-pressed", String(state.l === k));
    if (k === "#") b.title = "Starts with a number"; if (k === "…") b.title = "Starts with another script";
    b.onclick = () => { state.l = k; state.p = 1; update(true); };
    $("az").append(b);
  }
  const counts = {};
  for (const l of LABELS.filter(l => !state.s || l.system === state.s)) counts[l.region] = (counts[l.region] || 0) + 1;
  const keep = state.r;
  $("region").innerHTML = '<option value="">All regions</option>' + Object.keys(counts).sort().map(r =>
    '<option value="' + r + '">' + (r === "other" ? "No region" : r) + " (" + counts[r] + ")</option>").join("");
  $("region").value = keep;
}
function update(push) {
  shown = filtered(false).sort(sorters[state.o]);
  const pages = Math.max(1, Math.ceil(shown.length / PER_PAGE));
  state.p = Math.min(Math.max(1, state.p), pages);
  build();
  $("q").value = state.q; $("sort").value = state.o;
  $("count").textContent = shown.length + " labels";
  const from = (state.p - 1) * PER_PAGE, slice = shown.slice(from, from + PER_PAGE);
  $("range").textContent = shown.length ? "Showing " + (from + 1) + " to " + (from + slice.length) + " of " + shown.length : "";
  $("empty").hidden = shown.length > 0;
  $("grid").innerHTML = "";
  slice.forEach((l, i) => {
    const a = document.createElement("a");
    a.className = "item"; a.href = "#"; a.dataset.i = from + i;
    const [w, h] = l.size || [4, 3];
    a.innerHTML = '<span class="pic" style="aspect-ratio:' + w + "/" + h + '"><img loading="lazy" decoding="async" width="' + w + '" height="' + h +
      '" alt="' + esc(l.title) + '" src="' + FOLDER + "/" + encodeURIComponent(l.file) + '"></span><b>' + esc(l.title) +
      '</b><span class="s">' + esc(l.serial) + "</span>";
    a.onclick = e => { e.preventDefault(); openView(from + i); };
    $("grid").append(a);
  });
  paging(pages);
  writeHash(push);
}
function esc(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c])); }
function paging(pages) {
  const nav = $("pages"); nav.innerHTML = ""; if (pages < 2) return;
  const add = (label, p, opts = {}) => {
    const b = document.createElement("button"); b.type = "button"; b.textContent = label;
    if (opts.disabled) b.disabled = true;
    if (p === state.p && !opts.nav) b.setAttribute("aria-current", "page");
    b.onclick = () => { state.p = p; update(true); scrollTo({top: 0}); };
    if (opts.aria) b.setAttribute("aria-label", opts.aria);
    nav.append(b);
  };
  add("Previous", state.p - 1, {disabled: state.p === 1, nav: true});
  const set = new Set([1, pages, state.p - 1, state.p, state.p + 1]); let last = 0;
  for (const p of [...set].filter(p => p >= 1 && p <= pages).sort((a, b) => a - b)) {
    if (p - last > 1) nav.insertAdjacentHTML("beforeend", "<i>…</i>");
    add(String(p), p, {aria: "Page " + p}); last = p;
  }
  add("Next", state.p + 1, {disabled: state.p === pages, nav: true});
}
let current = -1;
function openView(i) {
  if (i < 0 || i >= shown.length) return;
  current = i; const l = shown[i], file = FOLDER + "/" + encodeURIComponent(l.file);
  $("vimg").src = file; $("vimg").alt = l.title; $("vtitle").textContent = l.title;
  $("vdl").innerHTML = [["Serial", l.serial], ["Release", l.release], ["System", SYSTEM_NAME[l.system] || l.system],
    ["Region", l.region === "other" ? "Not in the serial" : l.region], ["Restored from", l.photos ? l.photos + " photos" : "—"],
    ["Size", l.size ? l.size[0] + " × " + l.size[1] + " px" : "—"]].map(([k, v]) => "<dt>" + k + "</dt><dd>" + esc(v) + "</dd>").join("");
  $("vdl-link").href = file; $("vdl-link").download = l.file;
  $("prev").disabled = i === 0; $("next").disabled = i === shown.length - 1;
  if (!$("view").open) $("view").showModal();
}
$("prev").onclick = () => openView(current - 1); $("next").onclick = () => openView(current + 1);
$("close").onclick = () => $("view").close();
$("view").addEventListener("click", e => { if (e.target === $("view")) $("view").close(); });
$("view").addEventListener("keydown", e => { if (e.key === "ArrowLeft") openView(current - 1); if (e.key === "ArrowRight") openView(current + 1); });
let timer; $("q").addEventListener("input", e => { clearTimeout(timer); timer = setTimeout(() => { state.q = e.target.value; state.p = 1; update(false); }, 150); });
$("region").onchange = e => { state.r = e.target.value; state.p = 1; update(true); };
$("sort").onchange = e => { state.o = e.target.value; state.p = 1; update(true); };
$("clear").onclick = () => { state = {q: "", s: "", r: "", l: "", o: "title", p: 1}; update(true); };
addEventListener("hashchange", () => { readHash(); update(false); });
readHash(); update(false);
</script>
</body>
</html>
"""


def build(folder=FOLDER):
    with open(os.path.join(folder, "labels.json"), encoding="utf-8") as f:
        labels = json.load(f)
    for l in labels:  # a release with no title in the database shows under its serial
        l["title"] = l.get("title") or l.get("serial") or l.get("release") or l["id"]
        l["serial"] = l.get("serial") or l.get("release") or l["id"]
        l["release"] = l.get("release") or l["serial"]
    data = json.dumps([{k: l.get(k) for k in ("id", "serial", "release", "title", "system", "file", "size", "photos")}
                       for l in labels], ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    credit = (f'Images restored by geon from photos found online and sent in by contributors: '
              f'<a href="{SOURCE}">{html.escape(SOURCE)}</a>. This page is only a way to browse them.')
    page = PAGE.replace("__CREDIT__", credit).replace("__FOLDER__", ".").replace("__DATA__", data)
    out = os.path.join(folder, "index.html")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    return out, len(labels)


if __name__ == "__main__":
    out, n = build(sys.argv[1] if len(sys.argv) > 1 else FOLDER)
    print(n, "labels:", os.path.abspath(out))
