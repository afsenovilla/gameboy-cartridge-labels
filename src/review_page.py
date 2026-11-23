# review_page: the page serve_catalogue shows at /review, for the label photos waiting in the inbox (src/inbox.py).
PAGE = r"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Labels to review</title>
<style>
:root{--bg:#f4f4f1;--card:#fff;--ink:#1d1f22;--muted:#666a70;--line:#d8d8d2;--ok:#2f7d32;--no:#b3261e;--warn:#a15c00;--accent:#3d4fc4}
@media (prefers-color-scheme:dark){:root{--bg:#16181b;--card:#202327;--ink:#e9e8e4;--muted:#9a9ea5;--line:#34383e;--ok:#6cc070;--no:#ef6a60;--warn:#e0a23c;--accent:#8d9bff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,sans-serif}
header{position:sticky;top:0;z-index:2;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 20px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
h1{font-size:18px;margin:0}a{color:var(--accent)}button,input{font:inherit}
button{border:1.5px solid var(--ink);background:transparent;color:var(--ink);border-radius:999px;padding:6px 16px;cursor:pointer}
button.ok{background:var(--ok);border-color:var(--ok);color:#fff}button.no{border-color:var(--no);color:var(--no)}
button:focus-visible,input:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
#drop{border:2px dashed var(--line);border-radius:10px;padding:10px 16px;color:var(--muted)}#drop.over{border-color:var(--accent);color:var(--ink)}
main{padding:20px;display:grid;gap:20px;max-width:1300px;margin:0 auto}
.cand{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr) 300px;gap:16px;align-items:start}
.photo{position:relative;user-select:none;touch-action:none}.photo img{display:block;width:100%;border-radius:6px}
.photo svg{position:absolute;inset:0;width:100%;height:100%;overflow:visible}
.photo polygon{fill:rgba(61,79,196,.12);stroke:#ff3b30;stroke-width:2}.photo circle{fill:#fff;stroke:#ff3b30;stroke-width:2.5;cursor:grab}
.prev img{display:block;width:100%;border-radius:6px;background:repeating-conic-gradient(#ccc 0 25%,#eee 0 50%) 0/16px 16px}
.cap{color:var(--muted);font-size:13px;margin-top:6px}
.side label{display:block;font-size:13px;color:var(--muted);margin-bottom:4px}
.side input{width:100%;padding:7px 10px;border:1.5px solid var(--line);border-radius:8px;background:transparent;color:var(--ink);font:600 16px ui-monospace,monospace}
.title{margin:8px 0 10px;font-weight:600}.badges{display:flex;flex-direction:column;gap:6px;margin-bottom:14px;font-size:14px}
.b-ok{color:var(--ok)}.b-warn{color:var(--warn)}.b-no{color:var(--no)}.row{display:flex;gap:8px;flex-wrap:wrap}
.empty{color:var(--muted);text-align:center;padding:60px 20px}.state{font-size:13px;color:var(--muted);margin-top:8px}
#loupe{position:fixed;z-index:9;pointer-events:none;width:240px;height:240px;border-radius:50%;border:3px solid #ff3b30;box-shadow:0 4px 16px rgba(0,0,0,.4);background:#000;display:none}
@media (max-width:900px){.cand{grid-template-columns:1fr}}
</style>
<header><h1>Labels to review <span id="n"></span></h1><a href="/screenscraper-labels/index.html">Back to the catalogue</a>
<label id="drop">Drop label photos here, or <input type="file" id="pick" accept="image/*" multiple></label><span id="up" class="state"></span></header>
<main id="list"></main><canvas id="loupe" width="240" height="240" aria-hidden="true"></canvas>
<script>
const $ = id => document.getElementById(id), esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const post = (url, data) => fetch(url, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)})
  .then(r => r.json().then(d => r.ok ? d : Promise.reject(new Error(d.error || r.status))));
let CANDS = [];
function badges(c) {
  const out = [];
  if (!c.serial) out.push('<span class="b-no">No serial read: type it from the label</span>');
  else if (!c.known && c.suggest) out.push('<span class="b-no">The database has no ' + esc(c.serial) + ": did you mean " + esc(c.suggest) + "? Check the label</span>");
  else if (!c.known && c.fetched_as) out.push('<span class="b-warn">Fetched for ' + esc(c.fetched_as) + ", but the label says " + esc(c.serial) + ". If that's what the label reads, it's a variant the database doesn't have: accepting adds it as a new label" + (c.title ? " of " + esc(c.title) : "") + ", and " + esc(c.fetched_as) + " stays in Missing</span>");
  else if (!c.known) out.push('<span class="b-no">The database has no ' + esc(c.serial) + ": check it against the label</span>");
  else if (c.fetched_as && !c.missing) out.push('<span class="b-warn">Fetched for ' + esc(c.fetched_as) + ", but the label says " + esc(c.serial) + "</span>");
  else if (c.missing) out.push('<span class="b-ok">In Missing: this completes it</span>');
  else if (!c.existing.length) out.push('<span class="b-ok">New: no label of this serial yet</span>');
  for (const e of c.existing) {
    const better = c.width > (e.width || 0) * 1.1;
    out.push('<span class="' + (better ? "b-ok" : "b-warn") + '">Already there: ' + esc(e.id) + " (" + (e.width || "?") + " px)" + (better ? ", this one is sharper" : ", this one isn't sharper") + "</span>");
  }
  out.push("<span>" + c.width + " px wide in the photo" + (c.width < 450 ? ' <span class="b-warn">(low resolution)</span>' : "") + "</span>");
  return out.join("");
}
function card(c) {
  const el = document.createElement("section"); el.className = "cand"; el.id = "c-" + c.id;
  el.innerHTML = '<div><div class="photo"><img alt="Photo ' + esc(c.file) + '" src="/screenscraper-labels/' + esc(c.photo) + '"><svg><polygon/></svg></div>' +
    '<div class="cap">' + esc(c.file) + ": drag the corners onto the label's corners, then fine-tune the last one with the arrow keys (Shift for 10 px)</div></div>" +
    '<div class="prev"><img alt="Straightened label" src="/screenscraper-labels/' + esc(c.preview) + "?v=" + c.v + '"><div class="cap">As it will be added</div></div>' +
    '<div class="side"><label for="s-' + c.id + '">Serial printed on the label</label><input id="s-' + c.id + '" value="' + esc(c.serial) + '" spellcheck="false">' +
    '<div class="title">' + esc(c.title || "Unknown title") + '</div><div class="badges">' + badges(c) + '</div>' +
    '<div class="row"><button class="ok" data-a="accept">Accept</button><button class="no" data-a="reject">Reject</button></div><div class="state"></div></div>';
  const img = el.querySelector(".photo img"), svg = el.querySelector("svg"), poly = el.querySelector("polygon");
  let quad = c.quad.map(p => p.slice());
  const draw = () => {
    const k = img.clientWidth / c.size[0];
    poly.setAttribute("points", quad.map(([x, y]) => x * k + "," + y * k).join(" "));
    svg.querySelectorAll("circle").forEach((h, i) => { h.setAttribute("cx", quad[i][0] * k); h.setAttribute("cy", quad[i][1] * k); });
  };
  quad.forEach((_, i) => {
    const h = document.createElementNS("http://www.w3.org/2000/svg", "circle"); h.setAttribute("r", 9); svg.append(h);
    h.addEventListener("pointerdown", e => {
      h.setPointerCapture(e.pointerId); const box = img.getBoundingClientRect(), k = img.clientWidth / c.size[0];
      const move = ev => { quad[i] = [Math.max(0, Math.min(c.size[0], (ev.clientX - box.left) / k)), Math.max(0, Math.min(c.size[1], (ev.clientY - box.top) / k))]; draw(); loupe(img, c, quad, i, ev); };
      const up = () => { h.removeEventListener("pointermove", move); h.removeEventListener("pointerup", up); $("loupe").style.display = "none"; active = i; recrop(); };
      loupe(img, c, quad, i, e);
      h.addEventListener("pointermove", move); h.addEventListener("pointerup", up);
    });
  });
  const state = el.querySelector(".state");
  const input = el.querySelector("input");
  let typed = false;  // a serial typed by hand is kept; otherwise it's read again on every new crop
  const show = d => { Object.assign(c, d); el.querySelector(".title").textContent = c.title || "Unknown title";
    el.querySelector(".badges").innerHTML = badges(c); if (!typed) input.value = c.serial || ""; };
  const recrop = () => { state.textContent = "Straightening and reading the serial…";
    post("/api/candidates/recrop", {id: c.id, quad, typed: typed ? input.value : ""}).then(d => { el.querySelector(".prev img").src = "/screenscraper-labels/" + d.preview + "?v=" + d.v;
      show(d); state.textContent = d.serial ? "" : "No serial read: type it from the label."; }).catch(e => state.textContent = "Couldn't straighten it: " + e.message); };
  input.addEventListener("input", () => { typed = !!input.value.trim(); });
  input.addEventListener("change", () => { if (input.value.trim()) post("/api/candidates/serial", {id: c.id, serial: input.value}).then(show).catch(() => {}); });
  img.onload = draw; window.addEventListener("resize", draw);
  // the corner last dragged can be nudged with the arrow keys, 1 photo pixel at a time (10 with Shift)
  let active = -1, nudgeTimer = null;
  el.tabIndex = -1;
  el.addEventListener("pointerdown", () => el.focus({preventScroll: true}));
  el.addEventListener("keydown", e => {
    if (active < 0 || e.target.tagName === "INPUT") return;
    const d = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]}[e.key];
    if (!d) return;
    e.preventDefault(); const step = e.shiftKey ? 10 : 1;
    quad[active] = [Math.max(0, Math.min(c.size[0], quad[active][0] + d[0] * step)), Math.max(0, Math.min(c.size[1], quad[active][1] + d[1] * step))];
    draw(); loupe(img, c, quad, active, null);
    clearTimeout(nudgeTimer); nudgeTimer = setTimeout(() => { $("loupe").style.display = "none"; recrop(); }, 700);
  });
  el.querySelector('[data-a="accept"]').onclick = () => { const serial = el.querySelector("input").value.trim().toUpperCase();
    if (!serial) { el.querySelector("input").focus(); state.textContent = "Type the serial first."; return; }
    state.textContent = "Adding it…";
    post("/api/candidates/accept", {id: c.id, serial, title: c.title}).then(d => { state.textContent = "Added as " + d.file; setTimeout(load, 600); })
      .catch(e => state.textContent = "Not added: " + e.message); };
  el.querySelector('[data-a="reject"]').onclick = () => post("/api/candidates/reject", {id: c.id}).then(load);
  return el;
}
// While a corner is dragged: the photo around it, 4 times larger, with a crosshair on the corner.
// While a corner is dragged (or nudged with the arrow keys): the photo around it, enlarged, with its contrast pushed
// so dark edges on dark cartridges show, the label's outline in red and a crosshair on the corner. The area shown is
// about 60 px of the photo as it's displayed, so a small photo isn't blown up into blocks.
function loupe(img, c, quad, i, ev) {
  const cv = $("loupe"), g = cv.getContext("2d"), W = cv.width, [x, y] = quad[i];
  const shownPx = 60 * c.size[0] / img.clientWidth, half = Math.max(12, shownPx / 2);   // in photo pixels
  cv.style.display = "block";
  const box = img.getBoundingClientRect(), k0 = img.clientWidth / c.size[0];
  const cx = ev ? ev.clientX : box.left + x * k0, cy = ev ? ev.clientY : box.top + y * k0;
  cv.style.left = (cx + (i === 1 || i === 2 ? 50 : -50 - W)) + "px"; cv.style.top = (cy + (i >= 2 ? 30 : -30 - W)) + "px";
  g.save(); g.fillStyle = "#000"; g.fillRect(0, 0, W, W);
  g.imageSmoothingEnabled = true; g.imageSmoothingQuality = "high"; g.filter = "contrast(1.8) brightness(1.25) saturate(1.2)";
  const sx = x * img.naturalWidth / c.size[0], sy = y * img.naturalHeight / c.size[1], sk = img.naturalWidth / c.size[0];
  g.drawImage(img, sx - half * sk, sy - half * sk, half * 2 * sk, half * 2 * sk, 0, 0, W, W);
  g.restore();
  const k = W / (half * 2), pts = quad.map(([px, py]) => [(px - x + half) * k, (py - y + half) * k]);
  g.strokeStyle = "#000"; g.lineWidth = 4; g.beginPath(); pts.forEach(([px, py], j) => j ? g.lineTo(px, py) : g.moveTo(px, py)); g.closePath(); g.stroke();
  g.strokeStyle = "#ff3b30"; g.lineWidth = 2; g.stroke();
  const m = W / 2; g.strokeStyle = "#000"; g.lineWidth = 3; g.beginPath(); g.moveTo(m, m - 22); g.lineTo(m, m + 22); g.moveTo(m - 22, m); g.lineTo(m + 22, m); g.stroke();
  g.strokeStyle = "#fff"; g.lineWidth = 1; g.stroke();
}
function load() {
  fetch("/api/candidates").then(r => r.json()).then(cs => {
    CANDS = cs; $("n").textContent = "(" + cs.length + ")"; const list = $("list"); list.innerHTML = "";
    if (!cs.length) list.innerHTML = '<p class="empty">Nothing to review. Drop photos of cartridges above, or into screenscraper-labels/inbox/.</p>';
    cs.forEach(c => list.append(card(c)));
  });
}
function upload(files) {
  const fs = [...files].filter(f => f.type.startsWith("image/")); let done = 0;
  if (!fs.length) return; $("up").textContent = "Reading " + fs.length + " photo" + (fs.length > 1 ? "s" : "") + "…";
  fs.reduce((p, f) => p.then(() => fetch("/api/inbox?name=" + encodeURIComponent(f.name), {method: "POST", body: f})
    .then(() => { done++; $("up").textContent = done + " of " + fs.length + " read"; })), Promise.resolve()).then(() => { $("up").textContent = ""; load(); });
}
$("pick").onchange = e => upload(e.target.files);
const drop = $("drop");
["dragover", "dragenter"].forEach(t => document.addEventListener(t, e => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach(t => document.addEventListener(t, e => { e.preventDefault(); drop.classList.remove("over"); }));
document.addEventListener("drop", e => upload(e.dataTransfer.files));
let seen = null;
setInterval(() => fetch("/api/version").then(r => r.json()).then(v => { if (seen !== null && v.review !== seen && !document.querySelector(".state:not(:empty)")) load(); seen = v.review; }).catch(() => {}), 3000);
load();
</script></html>"""
