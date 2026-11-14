# review-prints: a tool, not a step: a local page for splitting and joining prints (the user, 2026-11-14), the decisions
# kept in print-corrections.json (src/print_corrections.py) and applied by the next make prints. The page shows the
# prints as that run will make them: the prints step's own grouping (<generated>/prints/automatic.json; prints.json
# before the prints step wrote it) with the decisions applied. A print as prints.json has it shows its id and restored
# image; one the decisions changed shows the ids it's made from (its image comes with make prints restore).
# Three tabs, and the decisions:
#   - Same serial: the serials (or releases, where no serial was read) of several prints, the most prints first,
#     SERIALS_PER_PAGE at a time: join some, or "All different", which hides the serial while its prints are these.
#   - Every print, worst first, PRINTS_PER_PAGE at a time: the most label photos whose serial read isn't the print's
#     first, then the most differing tiles between two of its label photos (the prints step's pair cache).
#   - Search: a serial, a stem or an id (its start), up to SEARCH_MAX prints.
#   - Decisions: every decision, the latest first, each to undo.
# Each print: its label photos (straighten's image as is: full resolution and uncropped, for pinch-zooming; the user,
# 2026-11-14), each with its serial read and a tick box: "Split off ticked" makes the ticked a print of their own. A
# print's own tick box marks it for joining: "Join ticked" in the bar at the bottom joins the ticked prints, from any tab. Frozen prints (src/frozen.py) can't be split, and two
# can't be joined. Buttons only, no keys (the user: keys next to S are too easy to hit).
# Usage: review_prints.py [port]
import json, os, sys, threading, urllib.parse
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import photos, straighten, print_corrections, prints as prints_step

GEN = photos.generated(False)
SERIALS_PER_PAGE = 10
PRINTS_PER_PAGE = 20
SEARCH_MAX = 50
lock = threading.Lock()


def pair_tiles(gen):
    """{(key, key): differing tiles} from the prints step's pair cache (pairs within a family)."""
    path = os.path.join(gen, "prints", "pairs.npz")
    if not os.path.exists(path):
        return {}
    z = np.load(path)
    bits = np.unpackbits(z["bits"]).astype(np.int32)
    ends = z["starts"] * 8
    sums = np.add.reduceat(bits, ends[:-1]) if len(bits) else np.zeros(0, int)
    sums = np.where(ends[1:] > ends[:-1], sums, 0)  # an empty entry: reduceat gives the next one's first bit
    out = {}
    for name, n in zip(z["names"], sums):
        a, b = str(name).split("|")[:2]
        out[a, b] = out[b, a] = int(n)
    return out


class Tool:
    def __init__(self):
        P = os.path.join(GEN, "prints")
        self.result = json.load(open(os.path.join(P, "prints.json")))
        auto_file = os.path.join(P, "automatic.json")
        self.auto = json.load(open(auto_file))["prints"] if os.path.exists(auto_file) else [p for p in self.result["prints"] if p["keys"]]
        self.serials = json.load(open(os.path.join(GEN, "read-serials", "serials.json")))
        self.solved = json.load(open(os.path.join(GEN, "solve", "solve.json")))["label_photos"]
        found = json.load(open(os.path.join(GEN, "find", "label-photos.json")))["label_photos"]
        self.outlines = {lp["key"]: lp["outline"] for lp in found}
        self.frozen_of = {k: p["frozen"] for p in self.result["prints"] if p.get("frozen") for k in p["keys"]}
        self.by_keys = {frozenset(p["keys"]): p for p in self.result["prints"] if p["keys"]}
        self.id_of_key = {k: p["id"] for p in self.result["prints"] for k in p["keys"]}
        self.tiles = pair_tiles(GEN)
        self.compute()

    def mapper(self, decisions):
        keys = {k for p in self.auto for k in p["keys"]}
        old = {k for d in decisions for k in d.get("keys", []) + [k for g in d.get("prints", []) for k in g]} - keys
        return print_corrections.key_mapper(keys, self.outlines, prints_step.photo_sizes({k.split("@")[0] for k in old}, GEN))

    def compute(self):
        self.decisions = print_corrections.load()["decisions"]
        mapped = self.mapper(self.decisions)
        groups, self.applied = print_corrections.apply([p["keys"] for p in self.auto], self.decisions, mapped, self.frozen_of)
        out = []
        for g in groups:
            g = sorted(g)
            read = lambda k, f: (self.serials.get(k) or {}).get(f)
            ser = Counter(read(k, "serial") for k in g if read(k, "serial"))
            rel = Counter(read(k, "release") for k in g if read(k, "release"))
            serial = ser.most_common(1)[0][0] if ser else None
            p = self.by_keys.get(frozenset(g))
            frozen = {self.frozen_of[k] for k in g if k in self.frozen_of}
            image = p and os.path.exists(os.path.join(GEN, "restore", straighten.file_name(p["id"])))
            disagree = sum(1 for k in g if read(k, "serial") and read(k, "serial") != serial)
            tiles = max((self.tiles.get((a, b), 0) for i, a in enumerate(g) for b in g[i + 1:]), default=0)
            out.append({"keys": [{"key": k, "serial": read(k, "serial"), "release": read(k, "release")} for k in g],
                        "id": p["id"] if p else None,
                        "from": sorted({self.id_of_key[k] for k in g if k in self.id_of_key}) if not p else [],
                        "serial": serial, "release": rel.most_common(1)[0][0] if rel else None,
                        "shape": self.solved[g[0]]["shape"] if g[0] in self.solved else None,
                        "families": len({self.solved[k]["family"] for k in g if k in self.solved}),
                        "frozen": sorted(frozen), "image": bool(image), "disagree": disagree, "tiles": tiles})
        # the same serial (or release): several prints; hidden where an "apart" decision has these prints
        by_serial = {}
        for i, p in enumerate(out):
            s = p["serial"] or p["release"]
            if s:
                by_serial.setdefault(s, []).append(i)
        apart = {}
        for d in self.decisions:
            if d["kind"] == "apart":
                apart.setdefault(d["serial"], []).append({frozenset(mapped(k) for k in g) - {None} for g in d["prints"]})
        same = []
        for s, idx in by_serial.items():
            if len(idx) < 2:
                continue
            now = {frozenset(k["key"] for k in out[i]["keys"]) for i in idx}
            same.append({"serial": s, "prints": idx, "looked_at": now in apart.get(s, [])})
        same.sort(key=lambda e: (-len(e["prints"]), -sum(len(out[i]["keys"]) for i in e["prints"]), e["serial"]))
        worst = sorted(range(len(out)), key=lambda i: (-out[i]["disagree"], -out[i]["tiles"], -len(out[i]["keys"])))
        self.state_json = {"prints": out, "same": same, "worst": worst,
                           "decisions": [{**d, "index": n, "applied": a} for n, (d, a) in enumerate(zip(self.decisions, self.applied))],
                           "per_page": {"serials": SERIALS_PER_PAGE, "prints": PRINTS_PER_PAGE, "search": SEARCH_MAX}}
        self.groups = {frozenset(k["key"] for k in p["keys"]): p for p in out}

    def group_of(self, keys):
        return self.groups.get(frozenset(keys))

    def decide(self, decision):
        """A decision added (checked against the prints as shown): None, or why not."""
        kind = decision.get("kind")
        if kind == "join":
            gs = [self.group_of(g) for g in decision.get("prints", [])]
            if len(gs) < 2 or any(g is None for g in gs):
                return "Tick two or more prints (the page may be out of date: reload)."
            if sum(1 for g in gs if g["frozen"]) > 1:
                return "Two frozen prints can't be joined: unfreeze one first (remove-photos)."
            d = {"kind": "join", "prints": decision["prints"]}
        elif kind == "split":
            keys, rest = decision.get("keys", []), decision.get("rest", [])
            g = self.group_of(keys + rest)
            if g is None or not keys or not rest:
                return "Tick some of a print's label photos, not all (the page may be out of date: reload)."
            if g["frozen"]:
                return "A frozen print can't be split: unfreeze it first (remove-photos)."
            d = {"kind": "split", "keys": keys, "rest": rest}
        elif kind == "apart":
            if not decision.get("serial") or any(self.group_of(g) is None for g in decision.get("prints", [])):
                return "The page may be out of date: reload."
            d = {"kind": "apart", "serial": decision["serial"], "prints": decision["prints"]}
        else:
            return "Unknown decision."
        data = print_corrections.load()
        data["decisions"].append({**d, "datetime": print_corrections.now()})
        print_corrections.save(data)
        self.compute()
        return None

    def undo(self, index, when):
        data = print_corrections.load()
        if not (0 <= index < len(data["decisions"])) or data["decisions"][index]["datetime"] != when:
            return "The decisions changed: reload."
        del data["decisions"][index]
        print_corrections.save(data)
        self.compute()
        return None


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>review prints</title>
<style>
body{font:14px system-ui;margin:0 0 70px;background:#2b2b2b;color:#eee}
header{position:sticky;top:0;background:#1d1d1d;padding:8px 16px;z-index:2;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
header button.tab.on{background:#5a8;color:#000}
main{padding:8px 16px}
button{font:inherit;padding:4px 10px;border-radius:4px;border:1px solid #777;background:#444;color:#eee;cursor:pointer}
button:disabled{opacity:.4;cursor:default}
.serial{margin:12px 0 24px;padding:8px;border:1px solid #555;border-radius:6px}
.serial h2{font-size:16px;margin:0 0 6px}
.print{display:inline-block;vertical-align:top;margin:4px 8px 8px 0;padding:6px;border:1px solid #666;border-radius:6px;background:#333;max-width:100%}
.print.ticked{border-color:#5a8;box-shadow:0 0 0 2px #5a8}
.print .head{display:flex;gap:8px;align-items:center;margin-bottom:4px;flex-wrap:wrap}
.print .restored{width:220px;display:block;margin-bottom:4px}
.lps{display:flex;flex-wrap:wrap;gap:4px;max-width:860px}
.lp{width:160px;font-size:11px;position:relative}
.lp img{width:160px;display:block}
.lp.ticked img{outline:3px solid #fa0}
.lp .odd{color:#f96}
.frozen{color:#6bf}
.note{color:#aaa;font-size:12px}
#bar{position:fixed;bottom:0;left:0;right:0;background:#1d1d1d;padding:10px 16px;display:flex;gap:10px;align-items:center;z-index:2}
#msg{color:#fa0}
.pager{margin:8px 0}
</style></head><body>
<header>
<button class="tab" data-tab="same">Same serial</button>
<button class="tab" data-tab="worst">Every print, worst first</button>
<button class="tab" data-tab="search">Search</button>
<button class="tab" data-tab="decisions">Decisions</button>
<span id="searchbox" style="display:none"><input id="q" placeholder="serial, stem or id" size="24"> <button id="go">Search</button></span>
<label id="lookedbox" style="display:none"><input type="checkbox" id="looked"> show serials looked at</label>
</header>
<main id="main">loading…</main>
<div id="bar"><span id="count">No prints ticked for joining.</span><button id="join" disabled>Join ticked</button><button id="clear" disabled>Clear</button><span id="msg"></span></div>
<script>
let S = null, tab = "same", page = 0, query = "";
const joinTicks = new Map();  // print handle (its first key) -> its keys
const lpTicks = new Set();    // label photo keys ticked for splitting
const $ = id => document.getElementById(id);
const handle = p => p.keys[0].key;

async function load() {
  const r = await fetch("/state");
  if (r.status === 503) { setTimeout(load, 1000); return; }
  S = await r.json();
  const now = new Set(S.prints.map(handle));
  for (const h of [...joinTicks.keys()]) if (!now.has(h)) joinTicks.delete(h);
  lpTicks.clear();
  render();
}

async function post(path, body) {
  $("msg").textContent = "";
  const r = await fetch(path, {method: "POST", body: JSON.stringify(body)});
  if (!r.ok) { $("msg").textContent = await r.text(); return false; }
  await load();
  return true;
}

function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) { if (k === "class") e.className = v; else if (k.startsWith("on")) e[k] = v; else e.setAttribute(k, v); }
  for (const k of kids) e.append(k);
  return e;
}

function printCard(p) {
  const keys = p.keys.map(k => k.key);
  const card = el("div", {class: "print" + (joinTicks.has(handle(p)) ? " ticked" : "")});
  const tick = el("input", {type: "checkbox"});
  tick.checked = joinTicks.has(handle(p));
  tick.onchange = () => { if (tick.checked) joinTicks.set(handle(p), keys); else joinTicks.delete(handle(p)); card.classList.toggle("ticked", tick.checked); bar(); };
  const name = p.id ? p.id : "new print, from " + (p.from.join(" + ") || "?");
  const head = el("div", {class: "head"}, el("label", {}, tick, " join"), el("b", {}, name),
    el("span", {class: "note"}, `${p.serial || p.release || "no serial"} · ${p.keys.length} label photos` + (p.families > 1 ? ` · ${p.families} families` : "") +
      (p.disagree ? ` · ${p.disagree} read another serial` : "") + (p.tiles ? ` · up to ${p.tiles} tiles differ` : "")));
  if (p.frozen.length) head.append(el("span", {class: "frozen"}, "frozen"));
  card.append(head);
  if (p.image) card.append(el("img", {class: "restored", loading: "lazy", src: "/print/" + encodeURIComponent(p.id)}));
  else if (p.keys.length >= 3) card.append(el("div", {class: "note"}, p.id ? "no restored image" : "restored after make prints restore"));
  const lps = el("div", {class: "lps"});
  for (const k of p.keys) {
    const box = el("input", {type: "checkbox"});
    box.checked = lpTicks.has(k.key);
    const lp = el("label", {class: "lp" + (box.checked ? " ticked" : "")},
      el("img", {loading: "lazy", src: "/label/" + encodeURIComponent(k.key)}),
      box, el("span", {class: (k.serial && k.serial !== p.serial) ? "odd" : ""}, " " + (k.serial || k.release || "no serial read")));
    box.onchange = () => { if (box.checked) lpTicks.add(k.key); else lpTicks.delete(k.key); lp.classList.toggle("ticked", box.checked); split.disabled = !canSplit(); };
    lps.append(lp);
  }
  const canSplit = () => { const n = keys.filter(k => lpTicks.has(k)).length; return n > 0 && n < keys.length && !p.frozen.length; };
  const split = el("button", {onclick: () => {
    const ticked = keys.filter(k => lpTicks.has(k));
    post("/decide", {kind: "split", keys: ticked, rest: keys.filter(k => !lpTicks.has(k))});
  }}, "Split off ticked");
  split.disabled = !canSplit();
  if (p.frozen.length) split.title = "frozen: can't be split";
  card.append(lps, el("div", {style: "margin-top:4px"}, split));
  return card;
}

function pager(n, per) {
  const pages = Math.max(1, Math.ceil(n / per));
  page = Math.min(page, pages - 1);
  const prev = el("button", {onclick: () => { page--; render(); scrollTo(0, 0); }}, "Previous");
  const next = el("button", {onclick: () => { page++; render(); scrollTo(0, 0); }}, "Next");
  prev.disabled = page === 0; next.disabled = page >= pages - 1;
  return el("div", {class: "pager"}, prev, ` page ${page + 1} of ${pages} `, next);
}

function render() {
  document.querySelectorAll(".tab").forEach(b => b.classList.toggle("on", b.dataset.tab === tab));
  $("searchbox").style.display = tab === "search" ? "" : "none";
  $("lookedbox").style.display = tab === "same" ? "" : "none";
  const m = $("main"); m.innerHTML = "";
  if (!S) { m.textContent = "loading…"; return; }
  if (tab === "same") {
    const list = S.same.filter(e => $("looked").checked || !e.looked_at);
    const per = S.per_page.serials;
    m.append(el("p", {class: "note"}, `${list.length} serials (or releases) of several prints` + ($("looked").checked ? "" : `; ${S.same.length - list.length} looked at, hidden`) + ". The most prints first."), pager(list.length, per));
    for (const e of list.slice(page * per, (page + 1) * per)) {
      const ps = e.prints.map(i => S.prints[i]);
      const apart = el("button", {onclick: () => post("/decide", {kind: "apart", serial: e.serial, prints: ps.map(p => p.keys.map(k => k.key))})}, "All different");
      apart.title = "these prints are different prints: hide this serial while its prints are these";
      const box = el("div", {class: "serial"}, el("h2", {}, `${e.serial}: ${ps.length} prints` + (e.looked_at ? " (looked at)" : "")));
      ps.forEach(p => box.append(printCard(p)));
      box.append(el("div", {}, apart));
      m.append(box);
    }
    m.append(pager(list.length, per));
  } else if (tab === "worst") {
    const per = S.per_page.prints;
    m.append(el("p", {class: "note"}, `${S.prints.length} prints: the most label photos reading another serial first, then the most differing tiles between two of its label photos.`), pager(S.worst.length, per));
    for (const i of S.worst.slice(page * per, (page + 1) * per)) m.append(printCard(S.prints[i]));
    m.append(pager(S.worst.length, per));
  } else if (tab === "search") {
    const q = query.trim().toUpperCase();
    if (!q) { m.append(el("p", {class: "note"}, "A serial (DMG-APSJ-JPN), a stem (DMG-APS) or an id (DMG-APSJ-JPN-lisa).")); return; }
    const hits = S.prints.filter(p => [p.serial, p.release, p.id, ...p.from].some(s => s && s.toUpperCase().startsWith(q)));
    m.append(el("p", {class: "note"}, `${hits.length} prints` + (hits.length > S.per_page.search ? `, the first ${S.per_page.search} shown` : "")));
    hits.sort((a, b) => (a.serial || a.release || "").localeCompare(b.serial || b.release || "") || b.keys.length - a.keys.length);
    hits.slice(0, S.per_page.search).forEach(p => m.append(printCard(p)));
  } else {
    m.append(el("p", {class: "note"}, `${S.decisions.length} decisions in print-corrections.json, the latest first; applied by the next make prints.`));
    for (const d of [...S.decisions].reverse()) {
      const what = d.kind === "join" ? `join ${d.prints.length} prints (${d.prints.map(g => g.length).join(" + ")} label photos)` :
                   d.kind === "split" ? `split off ${d.keys.length} label photos (from ${d.keys.length + d.rest.length})` :
                   `${d.serial}: ${d.prints.length} prints all different`;
      const undo = el("button", {onclick: () => post("/undo", {index: d.index, datetime: d.datetime})}, "Undo");
      m.append(el("div", {style: "margin:6px 0"}, `${d.datetime} · ${what}` + (d.applied ? "" : " · (nothing to do now)") + " ", undo));
    }
  }
}

function bar() {
  const n = joinTicks.size;
  $("count").textContent = n ? `${n} prints ticked for joining.` : "No prints ticked for joining.";
  $("join").disabled = n < 2; $("clear").disabled = n === 0;
}
$("join").onclick = async () => { if (await post("/decide", {kind: "join", prints: [...joinTicks.values()]})) { joinTicks.clear(); bar(); render(); } };
$("clear").onclick = () => { joinTicks.clear(); bar(); render(); };
$("go").onclick = () => { query = $("q").value; render(); };
$("q").onkeydown = e => { if (e.key === "Enter") { query = $("q").value; render(); } };
$("looked").onchange = () => { page = 0; render(); };
document.querySelectorAll(".tab").forEach(b => b.onclick = () => { tab = b.dataset.tab; page = 0; render(); });
bar(); load();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def send(self, body, kind="application/json", status=200, cache=False):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        if cache:
            self.send_header("Cache-Control", "max-age=3600")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
        if path == "/":
            return self.send(PAGE.encode(), "text/html; charset=utf-8")
        if tool is None:
            return self.send(b"loading", "text/plain", 503)
        if path == "/state":
            with lock:
                return self.send(tool.state_json)
        part, _, name = path[1:].partition("/")
        if part == "label":
            file = os.path.join(GEN, "straighten", straighten.file_name(name))
            return self.send(open(file, "rb").read(), "image/avif", cache=True) if os.path.exists(file) else self.send_error(404)
        if part == "print":
            file = os.path.join(GEN, "restore", straighten.file_name(name))
            return self.send(open(file, "rb").read(), "image/avif") if os.path.exists(file) else self.send_error(404)
        self.send_error(404)

    def do_POST(self):
        if self.path not in ("/decide", "/undo") or tool is None:
            return self.send_error(404)
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        with lock:
            why = tool.decide(data) if self.path == "/decide" else tool.undo(data.get("index", -1), data.get("datetime"))
        if why:
            return self.send(why.encode(), "text/plain", 409)
        self.send({"ok": True})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8774
    tool = None
    server = ThreadingHTTPServer(("localhost", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"review prints at http://localhost:{PORT}/ (ctrl-C to stop); the page waits until the prints are loaded", flush=True)
    tool = Tool()
    print(f"loaded: {len(tool.state_json['prints'])} prints, {len(tool.decisions)} decisions", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
