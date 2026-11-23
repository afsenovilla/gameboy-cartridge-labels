# A page for browsing the downloaded labels: published-labels/index.html (made by download_published.py), one file with
# its data inside, opened from the folder in a browser: search, system and region filters, sorting, pages, a viewer.
#
#   python run.py py src/build_site.py [folder] [--issues https://github.com/owner/repo] [--upload URL]
#   python run.py py src/build_site.py --remote out.html [--base https://geon.github.io/gameboy-cartridge-labels/] [--issues URL] [--viewer 3d/]
# --remote makes the page published sites use: it reads index.json, wanted.json and prints/ from --base (beside the page if none).
# --viewer names the 3D viewer page (docs/3d/ in this repository): "View on a cartridge" then shows that page's models inside the dialog.
#
# With --issues, each label has a "Report a problem" button: a form that opens a prefilled new issue of that repository.
# --issues local keeps the reports for a local copy instead: in screenscraper-labels/reports.json when the page is
# served by serve_catalogue.py (which also writes them into ignore.txt), else in the browser.
import html, json, os, sys, time

FOLDER = "published-labels"
SOURCE = "https://geon.github.io/gameboy-cartridge-labels/"
CARTRIDGE = "cartridge.json"  # optional, from make_cartridge.py: with it, a label can be viewed on a 3D cartridge
UPLOAD = "https://www.dropbox.com/request/9pv35ozb0iieahq3z3uf"  # where the project asks for photos (its wanted.html)

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{
  --page:#cfcdc6; --shell:#dedcd5; --well:#bdbbb3; --ink:#22241f; --muted:#5b5e53; --line:#aeaca4;
  --lcd:#8bac0f; --lcd-ink:#0f380f; --on:#306230; --on-ink:#e9ecdc; --focus:#0f380f;
  --gb:#5f7d0c; --gbc:#c8600a; --gba:#3d4fc4;
  --font:"Segoe UI Variable Text","Segoe UI",system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif;
}
@media (prefers-color-scheme:dark){:root{
  --page:#1c201a; --shell:#262b23; --well:#303629; --ink:#e4e6da; --muted:#9ea493; --line:#3c4235;
  --on:#4b7a2c; --on-ink:#f2f5e6; --focus:#b7d84a;
  --gb:#a9c93a; --gbc:#ff9f4d; --gba:#8d9bff;
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
.bar-in>*{min-width:0}
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
.stackwrap{display:block;position:relative;margin-top:14px}
.stack .stackwrap{margin:16px 14px 6px}
.layer{position:absolute;inset:0;border-radius:3px;overflow:hidden;background:var(--well);box-shadow:0 1px 6px rgba(0,0,0,.28);transform-origin:50% 90%}
.layer img{display:block;width:100%;height:100%;object-fit:cover}
.layer.l1{transform:rotate(-5deg)}
.layer.l2{transform:rotate(5deg)}
.stack.two .layer.l1{transform:rotate(5deg)}
.item.stack:hover .layer.l1,.item.stack:focus-visible .layer.l1{transform:rotate(-10deg) translateX(-4%)}
.item.stack:hover .layer.l2,.item.stack:focus-visible .layer.l2{transform:rotate(10deg) translateX(4%)}
.item.stack.two:hover .layer.l1,.item.stack.two:focus-visible .layer.l1{transform:rotate(10deg) translateX(4%)}
.stackwrap .pic{position:relative;z-index:1;box-shadow:0 1px 6px rgba(0,0,0,.28)}
.badge{position:absolute;z-index:2;right:8px;bottom:8px;white-space:nowrap;background:var(--ink);color:var(--page);border-radius:5px;padding:2px 8px;font:700 12px var(--font)}
.sys{display:inline-block;border:2px solid currentColor;border-radius:999px;padding:0 7px;margin-right:6px;font:700 11px/1.5 var(--font);vertical-align:1px}
.sys-dmg{color:var(--gb)}.sys-cgb{color:var(--gbc)}.sys-agb{color:var(--gba)}
.thumbs{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;justify-content:center}
.thumbs button{width:64px;padding:0;border:2px solid transparent;border-radius:4px;background:var(--well);cursor:pointer;overflow:hidden}
.thumbs button[aria-current=true]{border-color:var(--on)}
.thumbs img{display:block;width:100%;height:auto;max-height:64px;object-fit:contain}
.rep{display:flex;flex-direction:column;gap:8px;border:1.5px solid var(--line);border-radius:8px;padding:12px}
.rep[hidden]{display:none}
.rep label{display:flex;gap:8px;align-items:center;font-size:14px}
.rep input[type=checkbox]{width:16px;height:16px;accent-color:var(--on)}
.rep textarea{width:100%;min-height:64px;resize:none;overflow:hidden;border:1.5px solid var(--ink);border-radius:6px;background:var(--page);color:var(--ink);font:14px var(--font);padding:8px}
.rep .row{display:flex;gap:8px;flex-wrap:wrap}
.reported{margin:0;padding:8px 10px;border-radius:6px;background:var(--well);font-size:14px}
.repbar{position:sticky;bottom:0;display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:10px 20px;background:var(--shell);border-top:1.5px solid var(--line)}
.repbar button{font:14px var(--font)}.repstate{color:var(--muted);font-size:13px}
.rep button,.rep a{border:1.5px solid var(--ink);background:transparent;color:var(--ink);border-radius:8px;padding:8px 12px;font:600 14px var(--font);cursor:pointer;text-decoration:none}
.rep button.main{background:var(--on);border-color:var(--on);color:var(--on-ink)}

.opt[hidden]{display:none}
.opt{display:inline-flex;gap:8px;align-items:center;color:var(--ink);font-weight:600;cursor:pointer}
.opt input{width:17px;height:17px;accent-color:var(--on)}
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
.view .big{background:var(--well);display:flex;flex-direction:column;align-items:center;justify-content:center;padding:20px}
.view .big img{max-width:100%;max-height:78vh;height:auto;display:block}
.view .big img[hidden]{display:none}
.vsw{display:flex;gap:8px;flex-wrap:wrap;justify-content:center;margin-top:14px}
.view .big.both #vimg{max-height:24vh;margin-top:14px}
.view .big.both .scene{height:min(46vh,380px)}
.tdbtn{border:1.5px solid var(--ink);background:transparent;color:var(--ink);border-radius:8px;padding:7px 14px;font:600 14px var(--font);cursor:pointer}
.tdbtn[aria-pressed=true]{background:var(--ink);color:var(--page)}
.scene{position:relative;width:100%;height:min(70vh,520px);touch-action:none;cursor:grab;user-select:none;-webkit-user-select:none;overflow:hidden}
.scene[hidden]{display:none}
.scene:active{cursor:grabbing}
.scene canvas{position:absolute;inset:0;width:100%;height:100%}
.scene img{position:absolute;left:0;top:0;transform-origin:0 0;pointer-events:none;display:block}
.scene iframe{position:absolute;inset:0;width:100%;height:100%;border:0;background:transparent}
.view .info{padding:22px;display:flex;flex-direction:column;gap:14px}
.view h2{margin:0;font:750 22px/1.15 var(--font);letter-spacing:-.01em}
.view dl{margin:0;display:grid;grid-template-columns:auto 1fr;gap:6px 14px}
.view dt{color:var(--muted)} .view dd{margin:0;overflow-wrap:anywhere}
.acts{display:flex;gap:8px;flex-wrap:wrap;margin-top:auto}
.acts a,.acts button{border:1.5px solid var(--ink);background:transparent;color:var(--ink);border-radius:8px;padding:9px 14px;font:600 14px var(--font);cursor:pointer;text-decoration:none}
.acts a.main{background:var(--on);border-color:var(--on);color:var(--on-ink)}
.grid[hidden],.wlist[hidden]{display:none}
.lede{display:flex;gap:10px 20px;align-items:center;flex-wrap:wrap;margin-top:8px}
.lede p{margin:0;max-width:62ch}
.cta{display:inline-block;background:var(--on);color:var(--on-ink);border-radius:8px;padding:10px 16px;font:700 15px var(--font);text-decoration:none;white-space:nowrap}
.cta[hidden]{display:none}
.tabs{display:flex;gap:6px;margin-top:20px;border-bottom:2px solid var(--ink)}
.tabs button{border:2px solid var(--ink);border-bottom:0;border-radius:10px 10px 0 0;background:transparent;color:var(--ink);padding:10px 18px;font:700 16px var(--font);cursor:pointer;margin-bottom:-2px}
.tabs button[aria-selected=true]{background:var(--ink);color:var(--page)}
.tabs small{font-weight:500;opacity:.8;margin-left:6px}
.wlist{display:flex;flex-direction:column;border-top:1.5px solid var(--ink)}
.wrow{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px 24px;padding:14px 0;border-bottom:1px solid var(--line);align-items:center}
.wrow h3{margin:0;font:650 17px/1.25 var(--font)}
.wrow .s{display:block;color:var(--muted);font-size:13px;margin-top:3px;overflow-wrap:anywhere}
.need{display:inline-block;background:var(--lcd);color:var(--lcd-ink);border-radius:5px;padding:2px 9px;font:700 13px var(--font);margin-right:8px;white-space:nowrap}
.wlinks{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}
.addl{font:600 14px var(--font);border:1.5px solid var(--ink);background:var(--on);color:var(--on-ink);border-radius:999px;padding:6px 14px;cursor:pointer}
.wlinks a{border:1.5px solid var(--ink);border-radius:8px;padding:6px 11px;font:600 13px var(--font);text-decoration:none;white-space:nowrap}
.wlinks a:hover{background:var(--well)}
@media (max-width:700px){.wrow{grid-template-columns:1fr}.wlinks{justify-content:flex-start}}
@media (max-width:900px){.bar-in{grid-template-columns:1fr 1fr}.lcd{grid-column:1/-1}.view{grid-template-columns:1fr}}
@media (max-width:560px){.bar-in{grid-template-columns:1fr}.seg{overflow-x:auto}.grid{grid-template-columns:repeat(2,1fr);gap:20px 14px}}
@media (prefers-reduced-motion:no-preference){.item .pic{transition:outline-offset .12s}.layer{transition:transform .18s ease-out}}
</style>
</head>
<body>
<header>
  <h1 id="h1">Cartridge labels</h1>
  <div class="lede"><p id="lede"></p><a class="cta" id="send" href="__UPLOAD__" target="_blank" rel="noopener" hidden>Send photos</a></div>
  <div class="tabs" role="tablist" aria-label="What to show"><button type="button" role="tab" id="tab-w"></button><button type="button" role="tab" id="tab-l"></button></div>
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
  <div class="meta"><span id="range"></span><span style="display:flex;gap:16px;align-items:center;flex-wrap:wrap"><label class="opt">Per page <select id="per" aria-label="Items per page"></select></label><label class="opt"><input type="checkbox" id="stack"> Stack versions of the same game</label><label class="opt" id="lowopt" hidden><input type="checkbox" id="low"> Only low resolution <span id="lowcount"></span></label></span></div>
  <div class="grid" id="grid"></div>
  <div class="wlist" id="wlist" hidden></div>
  <div class="empty" id="empty" hidden>Nothing matches. Clear the search or choose another system or region.<br><button id="clear">Clear filters</button></div>
  <nav class="pages" id="pages" aria-label="Pages"></nav>
</main>
<div class="repbar" id="repbar" hidden><span id="repcount"></span><button type="button" id="rep-apply" hidden>Leave these out (write to ignore.txt)</button><button type="button" id="rep-copy">Copy for ignore.txt</button><button type="button" id="rep-list">Download reports</button><button type="button" id="refresh" hidden>Refresh</button><a id="revlink" href="/review" hidden>Labels to review</a><span id="repstate" class="repstate"></span></div>
<footer>__CREDIT__</footer>
<dialog id="view"><div class="view">
  <div class="big"><div class="scene" id="scene" hidden></div><img id="vimg" alt=""><div class="vsw" role="group" aria-label="What to show"><button type="button" class="tdbtn" id="vflat" aria-pressed="true">Label</button><button type="button" class="tdbtn" id="v3d" aria-pressed="false">On a cartridge</button></div><div class="thumbs" id="thumbs"></div></div>
  <div class="info">
    <h2 id="vtitle"></h2>
    <dl id="vdl"></dl>
    <form class="rep" id="rep" hidden>
      <strong>What's wrong with this label?</strong>
      <div id="reasons"></div>
      <textarea id="note" placeholder="Anything else? (optional)" aria-label="Details"></textarea>
      <div class="row"><a id="rep-issue" class="main" target="_blank" rel="noopener">Open as GitHub issue</a><button type="button" id="rep-save" class="main" hidden>Save report</button><button type="button" id="rep-drop" hidden>Remove report</button><button type="button" id="rep-cancel">Cancel</button></div>
    </form>
    <p class="reported" id="reported" hidden></p>
    <div class="acts"><button id="report">Report a problem</button><button id="prev">Previous game</button><button id="next">Next game</button><a id="vdl-link" class="main" download>Download</a><button id="close">Close</button></div>
  </div>
</div></dialog>
<script type="application/json" id="data">__DATA__</script>
<script type="application/json" id="wanted">__WANTED__</script>
<script type="application/json" id="text">__TEXT__</script>
<script type="application/json" id="cart-data">__CART__</script>
<script>
__LOAD_START__
const FOLDER = "__FOLDER__";
const enc = f => f.split("/").map(encodeURIComponent).join("/");
const ISSUES = "__ISSUES__";
const VIEWER = "__VIEWER__";  // the 3D viewer page (--viewer): "View on a cartridge" shows it here, in a frame, turning by itself; empty = the built-in mesh
const REASONS = ["Blurry or low resolution", "Glare or reflections", "Dirt, scratches or damage", "Crooked or badly cropped", "Wrong colours", "Wrong title or serial", "Not a label", "Other"];
const SYSTEMS = [["", "All"], ["dmg", "Game Boy"], ["cgb", "Game Boy Color"], ["agb", "Game Boy Advance"]];
const SYSTEM_NAME = {dmg: "Game Boy", cgb: "Game Boy Color", agb: "Game Boy Advance"}, SYSTEM_SHORT = {dmg: "GB", cgb: "GBC", agb: "GBA"};
const PER_CHOICES = [24, 48, 96, 200];
const fold = s => (s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
const regionOf = s => { const m = /-([A-Z]{3})(?:-\d)?$/.exec(s || ""); return m ? m[1] : "other"; };
const letterOf = t => { const c = fold(t).replace(/[^\p{L}\p{N}]/gu, "")[0] || ""; return /[a-z]/.test(c) ? c.toUpperCase() : /[0-9]/.test(c) ? "#" : "…"; };
const UPLOAD = "__UPLOAD__";
const WANTED = WANTED_RAW.filter(w => w.print).map((w, i) => { const serial = (w.serials || []).join(", ") || w.release || "", title = w.title || serial || w.print;
  return {id: w.print, rank: i, title, serial, release: w.release || "", system: w.system, region: w.region || "other", needed: w.needed, photos: w.photos || 0, search: w.search || [],
    letter: "", hay: fold([title, serial, w.release].join(" "))}; });
for (const w of WANTED) w.letter = letterOf(w.title);
const HOME = WANTED.length ? "w" : "l";
const SORTS = {w: [["rank", "Closest to done first"], ["title", "Title A to Z"], ["photos", "Most photos already"]], l: [["title", "Title A to Z"], ["serial", "Serial"], ["photos", "Most photos first"]]};
const defaultSort = v => SORTS[v][0][0];
for (const l of LABELS) { l.letter = letterOf(l.title); l.region = regionOf(l.serial); l.hay = fold([l.title, l.serial, l.release].join(" ")); }
const $ = id => document.getElementById(id);
let state = {q: "", s: "", r: "", l: "", g: "1", o: "title", p: 1, v: HOME, n: 48}, shown = [], groups = [];

function readHash() {
  const h = new URLSearchParams(location.hash.slice(1));
  const v = h.get("v") === "l" || h.get("v") === "w" ? h.get("v") : HOME, o = h.get("o");
  state = {q: h.get("q") || "", s: h.get("s") || "", r: h.get("r") || "", l: h.get("l") || "", g: h.get("g") === "0" ? "0" : "1", o: SORTS[v].some(x => x[0] === o) ? o : defaultSort(v), p: parseInt(h.get("p")) || 1, v, n: PER_CHOICES.includes(+h.get("n")) ? +h.get("n") : 48, z: h.get("z") === "1" ? "1" : ""};
}
function writeHash(push) {
  const h = new URLSearchParams();
  if (state.q) h.set("q", state.q); if (state.s) h.set("s", state.s); if (state.r) h.set("r", state.r); if (state.l) h.set("l", state.l); if (state.g === "0") h.set("g", "0"); if (state.z) h.set("z", "1");
  if (state.v !== HOME) h.set("v", state.v); if (state.o !== defaultSort(state.v)) h.set("o", state.o); if (state.p > 1) h.set("p", state.p); if (state.n !== 48) h.set("n", state.n);
  const url = location.pathname + (h.toString() ? "#" + h : "");
  push ? history.pushState(null, "", url) : history.replaceState(null, "", url);
}
function filtered(ignoreSystem, ignoreLetter) {
  const words = fold(state.q).split(/\s+/).filter(Boolean);
  return (state.v === "w" ? WANTED : LABELS).filter(l => (ignoreSystem || !state.s || l.system === state.s) && (ignoreLetter || !state.l || l.letter === state.l) &&
    (!state.r || l.region === state.r) && (!state.z || state.v === "w" || l.lowres) &&
    words.every(w => l.hay.includes(w)));
}
const sorters = {
  title: (a, b) => a.title.localeCompare(b.title, undefined, {sensitivity: "base", numeric: true}) || a.serial.localeCompare(b.serial),
  serial: (a, b) => a.serial.localeCompare(b.serial, undefined, {numeric: true}),
  photos: (a, b) => b.photos - a.photos || sorters.title(a, b),
  rank: (a, b) => a.rank - b.rank,
};
const groupKey = l => l.system + "|" + fold(l.title).replace(/[^\p{L}\p{N}]/gu, "");
function groupUp(labels) {
  if (state.g === "0" || state.v === "w") return labels.map(l => ({title: l.title, labels: [l], rep: l}));
  const by = new Map();
  for (const l of labels) { const k = groupKey(l); if (!by.has(k)) by.set(k, []); by.get(k).push(l); }
  return [...by.values()].map(ls => ({title: ls[0].title, labels: ls, rep: ls.reduce((a, b) => b.photos > a.photos ? b : a)}));
}
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
  for (const l of (state.v === "w" ? WANTED : LABELS).filter(l => !state.s || l.system === state.s)) counts[l.region] = (counts[l.region] || 0) + 1;
  const keep = state.r;
  $("region").innerHTML = '<option value="">All regions</option>' + Object.keys(counts).sort().map(r =>
    '<option value="' + r + '">' + (r === "other" ? "No region" : r) + " (" + counts[r] + ")</option>").join("");
  $("region").value = keep;
}
function update(push) {
  const matched = filtered(false).sort(sorters[state.o]);
  shown = groupUp(matched);
  const pages = Math.max(1, Math.ceil(shown.length / state.n));
  state.p = Math.min(Math.max(1, state.p), pages);
  build();
  const wv = state.v === "w";
  $("sort").innerHTML = SORTS[state.v].map(([k, n]) => '<option value="' + k + '">' + n + "</option>").join("");
  $("per").value = state.n; $("q").value = state.q; $("sort").value = state.o; $("stack").checked = state.g === "1"; $("low").checked = !!state.z; $("lowopt").hidden = !LABELS.some(l => l.lowres) || state.v === "w";
  $("stack").parentElement.hidden = wv; $("grid").hidden = wv; $("wlist").hidden = !wv; $("send").hidden = !wv || !UPLOAD;
  $("tab-w").innerHTML = esc(TEXT.wantedTab) + "<small>" + WANTED.length + "</small>"; $("tab-l").innerHTML = esc(TEXT.labelsTab) + "<small>" + LABELS.length + "</small>";
  $("tab-w").setAttribute("aria-selected", String(wv)); $("tab-l").setAttribute("aria-selected", String(!wv));
  $("lede").textContent = wv ? WANTED.length + TEXT.wantedLede : TEXT.labelsLede;
  $("count").textContent = matched.length + (wv ? " cartridges" : " labels");
  const from = (state.p - 1) * state.n, slice = shown.slice(from, from + state.n);
  $("range").textContent = shown.length ? "Showing " + (from + 1) + " to " + (from + slice.length) + " of " + shown.length + (wv ? " cartridges" : state.g === "1" ? " games" : " labels") : "";
  $("empty").hidden = shown.length > 0;
  $("grid").innerHTML = ""; $("wlist").innerHTML = "";
  if (wv) slice.forEach(g => {
    const w = g.rep, n = w.needed, row = document.createElement("div"); row.className = "wrow";
    const links = w.search.filter(x => /^https:\/\//.test(x.url)).map(x => '<a href="' + esc(x.url) + '" target="_blank" rel="noopener noreferrer">' + esc(x.label) + "</a>").join("");
    row.innerHTML = "<div><h3>" + esc(w.title) + '</h3><span class="s">' + (TEXT.photos ? '<span class="need">' + n + " more photo" + (n === 1 ? "" : "s") + " needed</span>" : "") +
      esc([SYSTEM_NAME[w.system] || w.system, w.region === "other" ? "" : w.region, w.serial].filter(Boolean).join(" · ")) + (TEXT.photos ? " · " + w.photos + " photo" + (w.photos === 1 ? "" : "s") + " so far" : "") + '</span></div><div class="wlinks">' + links +
      (SERVED ? '<button type="button" class="addl">Add label</button>' : "") + "</div>";
    if (SERVED) row.querySelector(".addl").onclick = () => addLabel(w, row);
    $("wlist").append(row);
  });
  else slice.forEach((g, i) => {
    const l = g.rep, many = g.labels.length > 1;
    const a = document.createElement("a");
    a.className = "item" + (many ? " stack" : "") + (g.labels.length === 2 ? " two" : ""); a.href = "#"; a.dataset.i = from + i;
    const behind = g.labels.filter(x => x !== l).slice(0, 2).map((x, j) => '<span class="layer l' + (j + 1) + '"><img loading="lazy" alt="" src="' + FOLDER + "/" + enc(x.file) + '"></span>').join("");
    const [w, h] = l.size || [4, 3];
    const regions = [...new Set(g.labels.map(x => x.region === "other" ? "—" : x.region))].join(", ");
    a.innerHTML = '<span class="stackwrap">' + behind + '<span class="pic" style="aspect-ratio:' + w + "/" + h + '"><img loading="lazy" decoding="async" width="' + w + '" height="' + h +
      '" alt="' + esc(l.title) + '" src="' + FOLDER + "/" + enc(l.file) + '"></span>' +
      (many ? '<span class="badge">' + g.labels.length + " labels</span>" : "") + "</span><b>" + esc(l.title) +
      '</b><span class="s">' + (SYSTEM_SHORT[l.system] ? '<span class="sys sys-' + l.system + '" title="' + esc(SYSTEM_NAME[l.system]) + '">' + SYSTEM_SHORT[l.system] + "</span>" : "") + esc(many ? regions : l.serial) + "</span>";
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
$("reasons").innerHTML = REASONS.map(r => '<label><input type="checkbox" value="' + esc(r) + '"> ' + esc(r) + "</label>").join("");
function issueLink() {  // the new-issue link carries what is ticked and typed now
  const l = shown[current].labels[inGroup], reasons = [...$("reasons").querySelectorAll("input:checked")].map(c => c.value), note = $("note").value.trim();
  const img = /^https?:/.test(FOLDER) ? FOLDER + "/" + l.file : l.file;
  const info = [["Label", l.title], ["Serial", l.serial], ["Release", l.release], ["System", SYSTEM_NAME[l.system] || l.system],
    ["Region", l.region === "other" ? "not in the serial" : l.region], l.source ? ["Source", l.source + (l.lowres ? " · low resolution" : "")] : ["Restored from", l.photos ? l.photos + " photos" : "unknown"],
    ["Size", l.size ? l.size[0] + " x " + l.size[1] + " px" : "unknown"], ["Image", img]];
  const body = info.map(([k, v]) => "**" + k + ":** " + v).join("\n") + "\n\n**What's wrong:** " + (reasons.join("; ") || "not specified") + "\n\n**More info:** " + (note || "none") + "\n";
  $("rep-issue").href = ISSUES.replace(/\/$/, "") + "/issues/new?title=" + encodeURIComponent("Label problem: " + l.title + " (" + l.serial + ")") + "&body=" + encodeURIComponent(body);
}
const grow = () => { $("note").style.height = "auto"; $("note").style.height = $("note").scrollHeight + 2 + "px"; };
$("rep").addEventListener("input", () => { grow(); issueLink(); });
var openReportForm = function () {
  $("reasons").querySelectorAll("input").forEach(c => c.checked = false);
  $("note").value = ""; $("rep").hidden = false; grow(); issueLink();
  $("reasons").querySelector("input").focus();
};
$("report").onclick = openReportForm; $("rep-cancel").onclick = () => { $("rep").hidden = true; };
// ISSUES = "local": reports for the person keeping these labels. Served by serve_catalogue.py, they're saved to its
// file (screenscraper-labels/reports.json) and "Leave these out" writes them into ignore.txt; opened as a file, they
// stay in this browser and "Copy for ignore.txt" gives the lines.
const LOCAL = ISSUES === "local", API = LOCAL && /^https?:$/.test(location.protocol) ? "/api/" : "";
let REPORTS = {}, SERVED = false; try { REPORTS = JSON.parse(localStorage.getItem("label-reports") || "{}"); } catch (e) {}
function saveReports() {
  if (SERVED) fetch(API + "reports", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(REPORTS)})
    .then(r => { if (!r.ok) throw new Error(r.status); $("repstate").textContent = "Saved to reports.json"; })
    .catch(e => { $("repstate").textContent = "Not saved (" + e.message + "): is serve_catalogue.py still running?"; });
  else try { localStorage.setItem("label-reports", JSON.stringify(REPORTS)); } catch (e) {}
  repBar();
}
function repBar() { const n = Object.keys(REPORTS).length; $("repbar").hidden = !LOCAL || (!n && !SERVED); $("repcount").textContent = n + " label" + (n === 1 ? "" : "s") + " reported";
  $("rep-apply").hidden = !SERVED || !n; $("refresh").hidden = !SERVED; $("revlink").hidden = !SERVED; $("rep-copy").hidden = SERVED || !n; $("rep-list").hidden = !n; }
// Served, a Missing cartridge can be given its label: an image file (a scan or a straight photo), with its serial;
// serve_catalogue saves it in screenscraper-labels/added/ and builds the page again, where it is then a label.
function addLabel(w, row) {
  const pick = document.createElement("input"); pick.type = "file"; pick.accept = "image/png,image/jpeg,image/webp,image/avif";
  pick.onchange = () => {
    const f = pick.files[0]; if (!f) return;
    const serial = (prompt("Serial printed on this label (like " + (w.serial || "DMG-XXXX-USA") + "):", w.serial || "") || "").trim().toUpperCase();
    if (!serial) return;
    const st = row.querySelector(".s"); st.textContent = "Saving " + f.name + "…";
    const q = new URLSearchParams({serial, release: w.release || "", title: w.title, system: w.system});
    fetch(API + "add?" + q, {method: "POST", headers: {"Content-Type": f.type || "application/octet-stream"}, body: f})
      .then(r => r.json().then(d => r.ok ? d : Promise.reject(new Error(d.error || r.status))))
      .then(d => { st.textContent = "Added as " + d.file + (d.rebuilt ? ". Reloading…" : ", but rebuilding the page failed: see the server's window."); if (d.rebuilt) setTimeout(() => location.reload(), 800); })
      .catch(e => { st.textContent = "Not added: " + e.message; });
  };
  pick.click();
}
// Served, the page reloads itself when serve_catalogue builds it again (a label added, some left out), unless a
// report is being written; then it waits for the form to close.
if (API) $("refresh").onclick = () => { $("repstate").textContent = "Building the page again…";
  fetch(API + "refresh", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"}).then(r => r.json())
    .then(d => d.rebuilt ? location.reload() : $("repstate").textContent = "Building failed: see the server's window.")
    .catch(e => $("repstate").textContent = "Couldn't refresh (" + e.message + "): is serve_catalogue.py running?"); };
if (API) fetch(API + "version").then(r => r.json()).then(v0 => setInterval(() => fetch(API + "version").then(r => r.json()).then(v => {
  if (v.n !== v0.n && $("rep").hidden) location.reload();
}).catch(() => {}), 3000)).catch(() => {});
if (API) fetch(API + "reports").then(r => r.ok ? r.json() : Promise.reject()).then(data => {
  const local = REPORTS; REPORTS = {...local, ...data}; SERVED = true; update(false); $("repstate").textContent = "Reports are saved to screenscraper-labels/reports.json";
  if (Object.keys(local).some(k => !(k in data))) saveReports(); else repBar();  // the browser's earlier ones go to the file too
  try { localStorage.removeItem("label-reports"); } catch (e) {}
}).catch(() => {});
const reportLines = () => Object.entries(REPORTS).map(([file, r]) => file + "  # " + r.title + " (" + r.serial + "): " + (r.reasons.join("; ") || "") + (r.note ? " - " + r.note.replace(/\s+/g, " ") : ""));
function showReported(l) { const r = LOCAL && REPORTS[l.file]; $("reported").hidden = !r; if (r) $("reported").textContent = "Reported: " + (r.reasons.join("; ") || "") + (r.note ? " - " + r.note : ""); }
if (LOCAL) {
  $("rep-issue").hidden = true; $("rep-save").hidden = false;
  $("rep-save").onclick = () => {
    const l = shown[current].labels[inGroup], reasons = [...$("reasons").querySelectorAll("input:checked")].map(c => c.value), note = $("note").value.trim();
    if (!reasons.length && !note) { $("reasons").querySelector("input").focus(); return; }
    REPORTS[l.file] = {id: l.id, title: l.title, serial: l.serial, reasons, note}; saveReports(); $("rep").hidden = true; showReported(l);
  };
  $("rep-drop").onclick = () => { const l = shown[current].labels[inGroup]; delete REPORTS[l.file]; saveReports(); $("rep").hidden = true; showReported(l); };
  $("rep-copy").onclick = async () => { const t = reportLines().join("\n"); try { await navigator.clipboard.writeText(t); $("rep-copy").textContent = "Copied"; setTimeout(() => $("rep-copy").textContent = "Copy for ignore.txt", 1500); } catch (e) { prompt("Copy these lines:", t); } };
  $("rep-apply").onclick = () => { $("repstate").textContent = "Leaving them out…"; return fetch(API + "apply", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"}).then(r => r.json()).then(d => {
    REPORTS = {}; repBar();
    if (d.rebuilt) { $("repstate").textContent = d.added + " left out. Reloading…"; setTimeout(() => location.reload(), 800); }
    else $("repstate").textContent = d.added + " written to ignore.txt, but rebuilding failed: see the server's window.";
  }).catch(e => { $("repstate").textContent = "Couldn't write ignore.txt (" + e.message + ")"; }); };
  $("rep-list").onclick = () => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([reportLines().join("\n") + "\n"], {type: "text/plain"})); a.download = "reports.txt"; a.click(); };
  const open0 = openReportForm;
  openReportForm = function () { open0(); const l = shown[current].labels[inGroup], r = REPORTS[l.file]; $("rep-drop").hidden = !r;
    if (r) { $("reasons").querySelectorAll("input").forEach(c => c.checked = r.reasons.includes(c.value)); $("note").value = r.note; grow(); } };
  $("report").onclick = () => openReportForm();
}
repBar();
$("rep-issue").onclick = e => { if (!$("reasons").querySelector("input:checked") && !$("note").value.trim()) { e.preventDefault(); $("reasons").querySelector("input").focus(); } };
let current = -1, inGroup = 0;
// A label on a cartridge you can turn. The cartridge is a mesh (cartridge.json, made by make_cartridge.py) drawn with WebGL;
// the label is an <img> placed over the cartridge's label recess with a CSS matrix3d that follows the same camera.
// (A WebGL texture would need the image to be readable by script, which a page opened from a folder can't do.)
const CART = (() => { const el = document.getElementById("cart-data"); try { return el ? JSON.parse(el.textContent) : null; } catch (e) { return null; } })();
// DMG grey: #888C88, a colorimeter reading of a filament sold as a match for classic Nintendo gray (filamentcolors.xyz/swatch/228); no official value is published.
const PX_PER_MM = 20, COLORS = {dmg: [0.57, 0.58, 0.57], cgb: [0.24, 0.24, 0.27]};
let three = false, gl = null, G = null, spin = {rx: -12, ry: -28, drag: null, raf: 0, touched: false};
const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
const m4 = {
  mul: (a, b) => { const o = new Float32Array(16); for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) { let t = 0; for (let k = 0; k < 4; k++) t += a[k * 4 + r] * b[c * 4 + k]; o[c * 4 + r] = t; } return o; },
  persp: (f, a, n, fa) => { const t = 1 / Math.tan(f / 2), o = new Float32Array(16); o[0] = t / a; o[5] = t; o[10] = (fa + n) / (n - fa); o[11] = -1; o[14] = 2 * fa * n / (n - fa); return o; },
  move: (x, y, z) => { const o = new Float32Array([1,0,0,0, 0,1,0,0, 0,0,1,0, x,y,z,1]); return o; },
  rotx: a => { const c = Math.cos(a), s = Math.sin(a); return new Float32Array([1,0,0,0, 0,c,s,0, 0,-s,c,0, 0,0,0,1]); },
  roty: a => { const c = Math.cos(a), s = Math.sin(a); return new Float32Array([c,0,-s,0, 0,1,0,0, s,0,c,0, 0,0,0,1]); },
};
function b64(str, T) { const b = atob(str), u = new Uint8Array(b.length); for (let i = 0; i < b.length; i++) u[i] = b.charCodeAt(i); return new T(u.buffer); }
function initGL() {  // once: the mesh with smoothed normals (sharp edges stay sharp), the shaders, the buffers
  if (G) return G;
  const cv = document.createElement("canvas"); gl = cv.getContext("webgl", {antialias: true, alpha: true}); if (!gl) return null;
  const v = b64(CART.v, Int16Array), t = b64(CART.t, Uint16Array), nT = t.length / 3, fn = new Float32Array(nT * 3), vn = new Float32Array(v.length);
  for (let i = 0; i < nT; i++) {
    const [a, b, c] = [t[i * 3] * 3, t[i * 3 + 1] * 3, t[i * 3 + 2] * 3], ux = v[b] - v[a], uy = v[b + 1] - v[a + 1], uz = v[b + 2] - v[a + 2], wx = v[c] - v[a], wy = v[c + 1] - v[a + 1], wz = v[c + 2] - v[a + 2];
    const x = uy * wz - uz * wy, y = uz * wx - ux * wz, z = ux * wy - uy * wx;  // length = twice the area
    fn[i * 3] = x; fn[i * 3 + 1] = y; fn[i * 3 + 2] = z;
    for (const q of [a, b, c]) { vn[q] += x; vn[q + 1] += y; vn[q + 2] += z; }
  }
  const pos = new Float32Array(nT * 9), nor = new Float32Array(nT * 9), cosCrease = Math.cos(38 * Math.PI / 180);
  const unit = (x, y, z) => { const l = Math.hypot(x, y, z) || 1; return [x / l, y / l, z / l]; };
  for (let i = 0; i < nT; i++) {
    const f = unit(fn[i * 3], fn[i * 3 + 1], fn[i * 3 + 2]);
    for (let k = 0; k < 3; k++) {
      const q = t[i * 3 + k] * 3, s = unit(vn[q], vn[q + 1], vn[q + 2]), n = f[0] * s[0] + f[1] * s[1] + f[2] * s[2] > cosCrease ? s : f;
      pos.set([v[q] / 100, v[q + 1] / 100, v[q + 2] / 100], i * 9 + k * 3); nor.set(n, i * 9 + k * 3);
    }
  }
  const sh = (type, src) => { const o = gl.createShader(type); gl.shaderSource(o, src); gl.compileShader(o); return o; }, pr = gl.createProgram();
  gl.attachShader(pr, sh(gl.VERTEX_SHADER, "attribute vec3 p,n;uniform mat4 mvp;uniform mat4 rot;varying vec3 vn;void main(){vn=(rot*vec4(n,0.)).xyz;gl_Position=mvp*vec4(p,1.);}"));
  gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, "precision mediump float;varying vec3 vn;uniform vec3 col;void main(){vec3 n=normalize(vn);float d=max(dot(n,normalize(vec3(-.35,.55,.8))),0.);float r=pow(max(dot(reflect(vec3(.35,-.55,-.8)*.0+normalize(vec3(.35,-.55,-.8)),n),vec3(0.,0.,1.)),0.),24.);gl_FragColor=vec4(col*(.38+.72*d)+vec3(.12)*r,1.);}"));
  gl.linkProgram(pr); gl.useProgram(pr);
  for (const [name, data] of [["p", pos], ["n", nor]]) { const b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW); const loc = gl.getAttribLocation(pr, name); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 3, gl.FLOAT, false, 0, 0); }
  gl.enable(gl.DEPTH_TEST);
  G = {cv, pr, count: nT * 3, mvp: gl.getUniformLocation(pr, "mvp"), rot: gl.getUniformLocation(pr, "rot"), col: gl.getUniformLocation(pr, "col"), center: [CART.size[0] / 2, CART.size[1] / 2, CART.size[2] / 2]};
  return G;
}
let lab = null;  // the label's size in mm and its <img>
function draw() {
  if (!G || !three) return;
  const box = $("scene"), dpr = window.devicePixelRatio || 1, W = box.clientWidth, H = box.clientHeight;
  if (G.cv.width !== Math.round(W * dpr) || G.cv.height !== Math.round(H * dpr)) { G.cv.width = Math.round(W * dpr); G.cv.height = Math.round(H * dpr); }
  gl.viewport(0, 0, G.cv.width, G.cv.height); gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
  const rot = m4.mul(m4.rotx(spin.rx * Math.PI / 180), m4.roty(spin.ry * Math.PI / 180)), fit = Math.min(W / H, 1) ;
  const model = m4.mul(rot, m4.move(-G.center[0], -G.center[1], -G.center[2])), dist = 150 / Math.max(fit, 0.55);
  const mvp = m4.mul(m4.persp(30 * Math.PI / 180, W / H, 20, 600), m4.mul(m4.move(0, 0, -dist), model));
  gl.uniformMatrix4fv(G.mvp, false, mvp); gl.uniformMatrix4fv(G.rot, false, rot); gl.uniform3fv(G.col, COLORS[three] || COLORS.dmg);
  gl.drawArrays(gl.TRIANGLES, 0, G.count);
  if (lab) {  // the label: its four corners through the same camera, then the CSS matrix that maps the <img> onto them
    const z = CART.recess.z + 0.03, [x0, y0, x1, y1] = lab.rect, P = [[x0, y1], [x1, y1], [x1, y0], [x0, y0]].map(([x, y]) => {
      const c = [0, 1, 2, 3].map(r => mvp[r] * x + mvp[4 + r] * y + mvp[8 + r] * z + mvp[12 + r]); return [(c[0] / c[3] * .5 + .5) * W, (1 - (c[1] / c[3] * .5 + .5)) * H]; });
    const facing = rot[10] > 0.02;  // the front's normal points at the camera
    lab.img.style.display = facing ? "block" : "none";
    const [[ax, ay], [bx, by], [cx, cy], [dx, dy]] = P, dx1 = bx - cx, dx2 = dx - cx, dx3 = ax - bx + cx - dx, dy1 = by - cy, dy2 = dy - cy, dy3 = ay - by + cy - dy;
    const den = dx1 * dy2 - dx2 * dy1, g = (dx3 * dy2 - dx2 * dy3) / den, h = (dx1 * dy3 - dx3 * dy1) / den;
    const a = bx - ax + g * bx, b = dx - ax + h * dx, d = by - ay + g * by, e = dy - ay + h * dy, w = lab.w, hh = lab.h;
    lab.img.style.transform = "matrix3d(" + [a / w, d / w, 0, g / w, b / hh, e / hh, 0, h / hh, 0, 0, 1, 0, ax, ay, 0, 1].join(",") + ")";
  }
}
function buildScene(l) {
  if (!initGL()) return false;
  if (G.cv.parentNode !== $("scene")) { $("scene").prepend(G.cv); }
  $("scene").querySelectorAll("img").forEach(i => i.remove());
  const r = CART.recess, rw = r.x[1] - r.x[0], rh = r.y[1] - r.y[0];
  let lw = (l.size ? l.size[0] : 830) / PX_PER_MM, lh = (l.size ? l.size[1] : 725) / PX_PER_MM;
  const fit = Math.min(1, (rw - 1) / lw, (rh - 1) / lh); lw *= fit; lh *= fit;  // the sticker sits inside the recess
  const cx = (r.x[0] + r.x[1]) / 2, cy = (r.y[0] + r.y[1]) / 2, img = document.createElement("img");
  img.alt = ""; img.src = FOLDER + "/" + enc(l.file); img.style.width = "100px"; img.style.height = (100 * lh / lw) + "px";
  $("scene").append(img); lab = {img, w: 100, h: 100 * lh / lw, rect: [cx - lw / 2, cy - lh / 2, cx + lw / 2, cy + lh / 2]};
  draw(); return true;
}
function sway(t) { if (!three || !$("view").open) { spin.raf = 0; return; } if (!spin.drag && !spin.touched) { spin.ry = -28 + Math.sin(t / 1400) * 24; spin.rx = -12 + Math.sin(t / 2100) * 4; } draw(); spin.raf = requestAnimationFrame(sway); }
const hasCart = l => !!CART && (l.system === "dmg" || l.system === "cgb");  // the Game Boy Advance has no model yet
const inViewer = l => !!VIEWER && ["dmg", "cgb", "agb"].includes(l.system);  // the viewer page has a model of this cartridge
function showThree(on) {
  const l = shown[current].labels[inGroup], ext = inViewer(l), can = ext || hasCart(l); on = on && can;
  $("v3d").hidden = !can;
  let fr = $("scene").querySelector("iframe");
  if (fr && !(on && ext)) { fr.remove(); fr = null; }
  three = on && !ext ? l.system : false; $("scene").hidden = !on; $("v3d").setAttribute("aria-pressed", String(on));
  $("vimg").hidden = on && !wantFlat; $("vflat").hidden = !can; $("vflat").setAttribute("aria-pressed", String(!on || wantFlat));  // the flat label stays under the cartridge unless switched off
  $("vimg").parentElement.classList.toggle("both", on && wantFlat);
  if (on && ext) {  // the viewer page in a frame, told which cartridge and which image; a new label only changes the part after #
    if (G && G.cv.parentNode) G.cv.remove(); $("scene").querySelectorAll("img").forEach(i => i.remove()); lab = null;
    if (!fr) { fr = document.createElement("iframe"); fr.title = "The label on a 3D cartridge"; $("scene").append(fr); }
    const src = VIEWER + "?v=__STAMP__#embed&sys=" + l.system + "&img=" + encodeURIComponent(new URL(FOLDER + "/" + enc(l.file), location.href).href);
    if (fr.getAttribute("src") !== src) fr.src = src;
    return;
  }
  if (on) { if (!buildScene(l)) { three = false; $("vimg").hidden = false; $("scene").hidden = true; $("v3d").hidden = true; $("vflat").hidden = true; $("vimg").parentElement.classList.remove("both"); return; } if (!still && !spin.raf) spin.raf = requestAnimationFrame(sway); }
}
let want3d = false, wantFlat = true;  // two switches side by side; one of them is always on
$("v3d").onclick = () => { spin.touched = false; want3d = !want3d; if (!want3d) wantFlat = true; showThree(want3d); };
$("vflat").onclick = () => { wantFlat = !wantFlat; if (!wantFlat) want3d = true; showThree(want3d); };
$("scene").addEventListener("pointerdown", e => { spin.drag = {x: e.clientX, y: e.clientY}; spin.touched = true; $("scene").setPointerCapture(e.pointerId); });
$("scene").addEventListener("pointermove", e => { const d = spin.drag; if (!d) return; spin.ry += (e.clientX - d.x) * 0.6; spin.rx = Math.max(-80, Math.min(80, spin.rx - (e.clientY - d.y) * 0.6)); d.x = e.clientX; d.y = e.clientY; draw(); });
$("scene").addEventListener("pointerup", () => { spin.drag = null; });
function openView(i, k = 0) {
  if (i < 0 || i >= shown.length) return;
  current = i; inGroup = k; const g = shown[i], l = g.labels[k], file = FOLDER + "/" + enc(l.file);
  $("vimg").src = file; $("vimg").alt = l.title; $("vtitle").textContent = l.title;
  $("thumbs").innerHTML = "";
  if (g.labels.length > 1) g.labels.forEach((x, j) => {
    const b = document.createElement("button"); b.type = "button"; b.title = x.serial; b.setAttribute("aria-label", x.serial);
    if (j === k) b.setAttribute("aria-current", "true");
    b.innerHTML = '<img alt="" src="' + FOLDER + "/" + enc(x.file) + '">';
    b.onclick = () => openView(current, j);
    $("thumbs").append(b);
  });
  $("vdl").innerHTML = [["Serial", l.serial], ["Release", l.release], ["System", SYSTEM_NAME[l.system] || l.system],
    ["Region", l.region === "other" ? "Not in the serial" : l.region], l.source ? ["Source", l.source + (l.lowres ? " · low resolution" : "")] : ["Restored from", l.photos ? l.photos + " photos" : "—"],
    ["Size", l.size ? l.size[0] + " × " + l.size[1] + " px" : "—"]].map(([k, v]) => "<dt>" + k + "</dt><dd>" + esc(v) + "</dd>").join("");
  if (g.labels.length > 1) $("vdl").insertAdjacentHTML("afterbegin", "<dt>Version</dt><dd>" + (k + 1) + " of " + g.labels.length + "</dd>");
  $("vdl-link").href = file; $("vdl-link").download = l.file.split("/").pop();
  $("rep").hidden = true; $("report").hidden = !ISSUES; showReported(l);
  $("prev").disabled = i === 0; $("next").disabled = i === shown.length - 1;
  if (!$("view").open) $("view").showModal();
  showThree(want3d);
}
$("prev").onclick = () => openView(current - 1); $("next").onclick = () => openView(current + 1);
$("close").onclick = () => $("view").close();
$("view").addEventListener("click", e => { if (e.target === $("view")) $("view").close(); });
$("view").addEventListener("close", () => { const fr = $("scene").querySelector("iframe"); if (fr) fr.remove(); });
$("view").addEventListener("keydown", e => { if (e.target.closest("textarea,input,select")) return; if (e.key === "ArrowLeft") openView(current - 1); if (e.key === "ArrowRight") openView(current + 1); });
let timer; $("q").addEventListener("input", e => { clearTimeout(timer); timer = setTimeout(() => { state.q = e.target.value; state.p = 1; update(false); }, 150); });
$("region").onchange = e => { state.r = e.target.value; state.p = 1; update(true); };
// Labels marked lowres (a small source image: worth replacing with a better one) can be shown alone, for a second pass.
const NLOW = LABELS.filter(l => l.lowres).length;
$("lowopt").hidden = !NLOW; $("lowcount").textContent = "(" + NLOW + ")";
$("low").onchange = e => { state.z = e.target.checked ? "1" : ""; state.p = 1; update(true); };
$("stack").onchange = e => { state.g = e.target.checked ? "1" : "0"; state.p = 1; update(true); };
$("per").innerHTML = PER_CHOICES.map(n => "<option>" + n + "</option>").join("");
$("per").onchange = e => { const first = (state.p - 1) * state.n; state.n = +e.target.value; state.p = Math.floor(first / state.n) + 1; update(true); };
$("sort").onchange = e => { state.o = e.target.value; state.p = 1; update(true); };
$("clear").onclick = () => { state = {q: "", s: "", r: "", l: "", g: state.g, o: defaultSort(state.v), p: 1, v: state.v, n: state.n, z: ""}; update(true); };
for (const v of ["w", "l"]) $("tab-" + v).onclick = () => { if (state.v === v) return; state = {...state, v, s: "", r: "", l: "", o: defaultSort(v), p: 1}; update(true); scrollTo({top: 0}); };
addEventListener("hashchange", () => { readHash(); update(false); });
readHash(); update(false);
__LOAD_END__
</script>
</body>
</html>
"""


LOCAL_LOAD = 'const LABELS = JSON.parse(document.getElementById("data").textContent), WANTED_RAW = JSON.parse(document.getElementById("wanted").textContent), TEXT = JSON.parse(document.getElementById("text").textContent); document.getElementById("h1").textContent = TEXT.heading;'
REMOTE_LOAD = """const fromIndex = index => Object.entries(index.prints).filter(([, p]) => p.image).map(([id, p]) => ({id, serial: p.serial || p.release || id,
    release: p.release || p.serial || id, title: p.title || p.serial || p.release || id, system: p.shape, file: p.image, size: p.size,
    photos: (p.label_photos || []).length}));
const getJson = (url, fallback) => fetch(url).then(r => { if (!r.ok) throw new Error(url + ": HTTP " + r.status); return r.json(); }).catch(e => { if (fallback) return fallback; throw e; });
Promise.all([getJson("__BASE__index.json"), getJson("__BASE__wanted.json", [])]).then(([index, WANTED_RAW]) => {
const LABELS = fromIndex(index), TEXT = JSON.parse(document.getElementById("text").textContent);"""
REMOTE_END = """}).catch(e => { document.getElementById("grid").textContent = "Could not load the data (" + e.message + "). Open this page from the site, next to index.json."; });"""


def cartridge():
    """The 3D cartridge mesh as the page embeds it, or nothing if cartridge.json isn't there (then there is no 3D button)."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), CARTRIDGE)
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read().replace("</", "<\\/")


def build_remote(out, issues="", upload=UPLOAD, base="", viewer=""):
    """A copy of the page that reads index.json beside it and the images at prints/<id>.avif: for the published site."""
    base = base.replace('"', "")
    base = base + "/" if base and not base.endswith("/") else base  # "" = beside the page; else the site's URL
    page = (PAGE.replace("__LOAD_START__", REMOTE_LOAD.replace("__BASE__", base)).replace("__LOAD_END__", REMOTE_END).replace("__TITLE__", "Browse the labels")
            .replace("__CREDIT__", f'<a href="{base}index.html">The plain list of all labels</a> · <a href="{base}wanted.html">Wanted photos</a>'
                     + (f' · <a href="{html.escape(viewer)}">Labels on 3D cartridges</a>' if viewer else "")).replace("__VIEWER__", viewer.replace('"', "")).replace("__STAMP__", str(int(time.time())))  # the stamp makes browsers fetch the viewer page again after each build
            .replace("__FOLDER__", base.rstrip("/") or ".").replace("__ISSUES__", issues.replace('"', "")).replace("__UPLOAD__", upload.replace('"', ""))
            .replace('<script type="application/json" id="data">__DATA__</script>\n<script type="application/json" id="wanted">__WANTED__</script>\n', "").replace("__CART__", cartridge())
            .replace("__TEXT__", json.dumps(TEXT, ensure_ascii=False).replace("</", "<\\/")))
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    return out


TEXT = {  # the restoration project's words; a catalogue (screenscraper_site) passes its own
    "heading": "Cartridge labels", "labelsTab": "Restored labels", "wantedTab": "Wanted", "photos": True,
    "labelsLede": "Restored labels of Game Boy, Game Boy Color and Game Boy Advance cartridges. Search by title or serial, then open one to see it large.",
    "wantedLede": " cartridges are only a photo or two short of a restored label. Find one, photograph the label straight on in good light, and send it with the serial printed on the cartridge (like DMG-A2XP-SCN) in the file name."}


def build(folder=FOLDER, issues="", upload=UPLOAD, credit=None, title="Cartridge labels", text=None):
    with open(os.path.join(folder, "labels.json"), encoding="utf-8") as f:
        labels = json.load(f)
    for l in labels:  # a release with no title in the database shows under its serial
        l["title"] = l.get("title") or l.get("serial") or l.get("release") or l["id"]
        l["serial"] = l.get("serial") or l.get("release") or l["id"]
        l["release"] = l.get("release") or l["serial"]
    data = json.dumps([{k: l.get(k) for k in ("id", "serial", "release", "title", "system", "file", "size", "photos", "source", "lowres")}
                       for l in labels], ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    wanted = []
    if os.path.exists(os.path.join(folder, "wanted.json")):
        with open(os.path.join(folder, "wanted.json"), encoding="utf-8") as f:
            wanted = json.load(f)
    wanted_data = json.dumps([{k: w.get(k) for k in ("print", "release", "title", "system", "region", "serials", "needed", "photos", "search")}
                              for w in wanted], ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    credit = credit or (f'Images restored by geon from photos found online and sent in by contributors: '
              f'<a href="{SOURCE}">{html.escape(SOURCE)}</a>. This page is only a way to browse them.')
    page = PAGE.replace("__LOAD_START__", LOCAL_LOAD).replace("__LOAD_END__", "").replace("__TITLE__", html.escape(title)).replace("__CREDIT__", credit).replace("__VIEWER__", "").replace("__STAMP__", "0").replace("__FOLDER__", ".").replace("__ISSUES__", issues.replace('"', "")).replace("__UPLOAD__", upload.replace('"', "")).replace("__DATA__", data).replace("__WANTED__", wanted_data).replace("__CART__", cartridge()).replace("__TEXT__", json.dumps({**TEXT, **(text or {})}, ensure_ascii=False).replace("</", "<\\/"))
    out = os.path.join(folder, "index.html")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    return out, len(labels), len(wanted)


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--remote" in args:  # --remote <output file>: the page for the published site
        i = args.index("--remote")
        issues = args[args.index("--issues") + 1] if "--issues" in args else ""
        print(build_remote(args[i + 1], issues, args[args.index("--upload") + 1] if "--upload" in args else UPLOAD,
                           args[args.index("--base") + 1] if "--base" in args else "",
                           args[args.index("--viewer") + 1] if "--viewer" in args else ""))
        sys.exit(0)
    issues = args[args.index("--issues") + 1] if "--issues" in args else ""
    upload = args[args.index("--upload") + 1] if "--upload" in args else UPLOAD
    folders = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] not in ("--issues", "--upload"))]
    out, n, w = build(folders[0] if folders else FOLDER, issues, upload)
    print(n, "labels,", w, "wanted:", os.path.abspath(out))
