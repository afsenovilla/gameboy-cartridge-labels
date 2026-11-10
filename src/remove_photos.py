# remove-photos: a tool, not a step: a local page for deleting photos from photos/ (the file and its record in
# photo-sources.json, photos.delete). The steps drop what they made from a deleted photo on their next run. Two tabs:
#   - No labels: the photos in which find found no label photo, 5 x 4 at a time, the fewest matched features first
#     (its distinct points among the inliers of its matches with other photos, match's): delete one, delete the page's
#     20, or go on to the next 20. (On the full set, 48 of the 71 matched nothing.)
#   - Bad photos: every print (prints.json) with its label photos, the worst first; prints by the sum of their label
#     photos' badness (many bad label photos, and how bad), label photos within a print by their own badness. Each label
#     photo: "Delete this and worse" (the photos of it and of the print's label photos after it) or "Delete".
# Deleting a photo that also holds label photos of other prints asks first (confirm()).
# Badness of a label photo: 1 - usable x resolution, both 0..1:
#   usable: the share of the label (restore's crop) that is in the photo, inside the sticker's cut, and matches the
#     reference: its straightened image, colours evened to the reference (restore.even_to), both blurred over BLUR_MM,
#     within DAMAGE_DE (Oklab) of it. Damage, glare, dirt, blur and a part off the photo all count against it.
#   resolution: the photo's pixels per mm at the label (from solve's fit) over FULL_PX_PER_MM, at most 1.
# The reference: the restored print of the print with the most label photos in its family (restore's image), its own
#   print on a tie or if it has REFERENCE_MIN or more; none if that is the label photo alone (then only the part off the
#   photo or the cut counts).
# Measured on the full set (25 prints of 4 or more label photos): over DAMAGE_DE, 0.1 % of the label for the cleanest,
#   5 % at the median, 38 % for the worst; at 0.05 the clean ones already differed on 10-20 % (noise, slight blur).
# Computed when the page starts, kept in generated/remove-photos/badness.json until prints.json, solve.json, a restored
# print is newer, or the settings (BLUR_MM, DAMAGE_DE, REFERENCE_MIN) changed.
# Usage: remove_photos.py [port]
import json, os, sys, threading, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cv2, numpy as np
import photos, steps, straighten, cuts, restore, shapes, publish

GEN = "generated"
BLUR_MM = 0.15          # what a slightly misregistered or less sharp label photo still matches
DAMAGE_DE = 0.08        # Oklab distance to the reference over which a pixel is damaged
FULL_PX_PER_MM = 10     # a photo this sharp at the label or more loses nothing by its resolution
REFERENCE_MIN = 3       # a print with this many label photos is its own label photos' reference
THUMB_PX = 600
CACHE = os.path.join(GEN, "remove-photos", "badness.json")
lock = threading.Lock()


def restored(pid):
    return os.path.join(GEN, "restore", straighten.file_name(pid)[:-5])


def badness_of(job):
    """(key, {usable, coverage, damage}) for one label photo against its reference print's restored image."""
    key, shape, ref_id, crop = job
    img = cv2.imread(os.path.join(GEN, "straighten", straighten.file_name(key)))
    if img is None:
        return key, None
    size, px_to_mm = straighten.canvas(shape)
    valid = img.max(2) > 1
    cut = straighten.load_cut(GEN, key)
    if cut is not None:
        valid &= cuts.mask(cut, shape, size, px_to_mm)
    x, y, w, h = publish.crop_box(shape, crop)
    img, valid = img[y:y + h, x:x + w].astype(np.float32) / 255, valid[y:y + h, x:x + w]
    coverage = float(valid.mean())
    damage = 0.0
    ref = cv2.imread(restored(ref_id) + ".avif") if ref_id else None
    if ref is not None and ref.shape[:2] == img.shape[:2] and valid.sum() >= 100:
        ref = ref.astype(np.float32) / 255
        s = BLUR_MM * straighten.PX_PER_MM
        a = restore.to_oklab(cv2.GaussianBlur(restore.even_to(img, ref, valid), (0, 0), s))
        b = restore.to_oklab(cv2.GaussianBlur(ref, (0, 0), s))
        damage = float(((np.linalg.norm(a - b, axis=2) > DAMAGE_DE) & valid).mean())
    else:
        ref_id = None
    return key, {"coverage": round(coverage, 3), "damage": round(damage, 3), "usable": round(coverage - damage, 3),
                 "reference": ref_id}


def references(prints):
    """key -> the id of the print whose restored image it's compared with, or None."""
    by_family = {}
    for p in prints:
        by_family.setdefault(p["family"], []).append(p)
    out = {}
    for p in prints:
        if len(p["keys"]) >= REFERENCE_MIN:
            ref = p
        else:
            ref = max(by_family[p["family"]], key=lambda q: (len(q["keys"]), q is p))
        for k in p["keys"]:
            out[k] = None if ref["keys"] == [k] else ref["id"]
    return out


def crop_of(pid):
    """restore's crop of a print (its family's), or None."""
    path = restored(pid) + ".json"
    return json.load(open(path))["crop"] if os.path.exists(path) else None


def badness(prints):
    """key -> {coverage, damage, usable, reference}, from the cache where it's still good."""
    inputs = [os.path.join(GEN, "prints", "prints.json"), os.path.join(GEN, "solve", "solve.json")]
    settings = [BLUR_MM, DAMAGE_DE, REFERENCE_MIN]
    newest = max(os.path.getmtime(f) for f in inputs)
    restore_dir = os.path.join(GEN, "restore")
    newest = max([newest] + [os.path.getmtime(os.path.join(restore_dir, f)) for f in os.listdir(restore_dir)])
    if os.path.exists(CACHE) and os.path.getmtime(CACHE) >= newest:
        cached = json.load(open(CACHE))
        if cached.get("settings") == settings:
            return cached["badness"]
    refs = references(prints)
    jobs = [(k, p["shape"], refs[k], crop_of(p["id"])) for p in prints for k in p["keys"]]
    out = {}
    print(f"comparing {len(jobs)} label photos with their restored prints", flush=True)
    with Pool(8) as pool:
        for n, (key, b) in enumerate(pool.imap_unordered(badness_of, jobs, chunksize=8), 1):
            if b is not None:
                out[key] = b
            if n % 500 == 0 or n == len(jobs):
                print(f"compared {n} of {len(jobs)}", flush=True)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    steps.write_json(CACHE, {"settings": settings, "badness": out})
    return out


class Tool:
    def __init__(self):
        import solve as solve_step
        self.photos = photos.all_photos()
        found = json.load(open(os.path.join(GEN, "find", "label-photos.json")))["label_photos"]
        with_labels = {lp["photo"] for lp in found}
        no_labels = [s for s in self.photos if s not in with_labels]
        self.matched = matched_features(set(no_labels))
        self.no_labels = sorted(no_labels, key=lambda s: self.matched[s])
        prints = json.load(open(os.path.join(GEN, "prints", "prints.json")))["prints"]
        solved = json.load(open(os.path.join(GEN, "solve", "solve.json")))["label_photos"]
        bad = badness(prints)
        self.crops = {}
        self.prints = []
        for p in prints:
            crop = crop_of(p["id"])
            entries = []
            for k in p["keys"]:
                r = solved.get(k, {})
                lw, lh = shapes.LABEL_MM[p["shape"]]
                ppm = solve_step.local_scale(np.array(r["cut_to_photo"]), [0, 0, lw, lh]) if "cut_to_photo" in r else 0
                b = bad.get(k) or {"coverage": 0, "damage": 0, "usable": 0, "reference": None}
                resolution = min(1.0, ppm / FULL_PX_PER_MM)
                entries.append({"key": k, "photo": k.split("@")[0], "badness": round(1 - b["usable"] * resolution, 3),
                                "damage": b["damage"], "off": round(1 - b["coverage"], 3), "px_per_mm": round(ppm, 1),
                                "compared": b["reference"] is not None,
                                "poor_fit": (r.get("fallback") or "").startswith("a poor")})
                self.crops[k] = (p["shape"], crop)
            entries.sort(key=lambda e: -e["badness"])
            self.prints.append({"id": p["id"], "serial": p.get("serial") or p.get("release") or "?",
                                "has_image": os.path.exists(restored(p["id"]) + ".avif"),
                                "score": round(sum(e["badness"] for e in entries), 3), "label_photos": entries})
        self.prints.sort(key=lambda p: -p["score"])

    def state(self):
        have = set(photos.all_photos())
        photo_prints = {}
        for p in self.prints:
            for e in p["label_photos"]:
                photo_prints.setdefault(e["photo"], []).append(p["id"])
        return {"no_labels": [s for s in self.no_labels if s in have], "matched": self.matched,
                "prints": self.prints, "photo_prints": photo_prints, "deleted": sorted(set(self.photos) - have)}

    def delete(self, sha1s):
        done = []
        with lock:
            have = photos.all_photos()
            for s in sha1s:
                if s in have:
                    photos.delete(s)
                    done.append(s)
        return done


def matched_features(wanted):
    """sha1 -> how many distinct points of the photo are inliers of its matches with other photos, for those wanted."""
    points = {s: [] for s in wanted}
    folder = os.path.join(GEN, "match")
    for f in os.listdir(folder):
        if not f.endswith(".npz"):
            continue
        a = f[:-4]
        z = np.load(os.path.join(folder, f))
        others = z["others"]
        if not len(others) or (a not in wanted and not wanted.intersection(others)):
            continue
        inliers, starts = z["inliers"], z["starts"]
        for i, b in enumerate(others):
            pair = inliers[starts[i]:starts[i + 1]]
            if a in wanted:
                points[a].append(pair[:, :2])
            if b in wanted:
                points[b].append(pair[:, 2:])
    return {s: len(np.unique(np.round(np.concatenate(v)), axis=0)) if v else 0 for s, v in points.items()}


def thumbnail(path, side):
    img = photos.load(path)
    if img is None:
        return None
    f = side / max(img.shape[:2])
    if f < 1:
        img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])[1].tobytes()


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>Remove photos</title><style>
* { box-sizing: border-box }
html, body { margin: 0; height: 100%; font: 14px system-ui, sans-serif; background: #f4f4f4; color: #222 }
header { display: flex; gap: 8px; align-items: center; padding: 8px 12px; height: 48px; background: #fff; border-bottom: 1px solid #ddd }
button { border: none; border-radius: 0.3em; padding: 6px 12px; font: inherit; background: #e4e4e4; cursor: pointer }
button:hover { background: #d4d4d4 }
button.tab.on { background: #333; color: #fff }
button.danger { background: #c62828; color: #fff }
button.danger:hover { background: #a31f1f }
.info { font-variant-numeric: tabular-nums; color: #555; margin-left: 8px }
.spacer { flex: 1 }
#grid { display: grid; grid-template-columns: repeat(5, 1fr); grid-template-rows: repeat(4, 1fr); gap: 6px; padding: 6px; height: calc(100% - 48px) }
#grid .cell { position: relative; min-height: 0; background: #ddd; display: flex; align-items: center; justify-content: center; overflow: hidden }
#grid img { max-width: 100%; max-height: 100%; object-fit: contain }
#grid .cell button { position: absolute; right: 4px; bottom: 4px }
#grid .cell .name { position: absolute; left: 4px; top: 4px; background: #fffc; padding: 0 4px; font: 11px ui-monospace, monospace }
#prints { padding: 6px 12px; height: calc(100% - 48px); overflow-y: auto }
.print { background: #fff; margin: 8px 0; padding: 8px; display: flex; gap: 10px; align-items: flex-start }
.print > .restored { width: 180px; flex: none }
.print .restored img { width: 100% }
.print .restored div { font: 12px ui-monospace, monospace; font-variant-numeric: tabular-nums }
.photos { display: flex; flex-wrap: wrap; gap: 8px }
figure { margin: 0; width: 180px }
figure img { width: 100%; display: block; background: #eee }
figcaption { font: 11px ui-monospace, monospace; font-variant-numeric: tabular-nums; color: #444; margin: 3px 0 }
figure .buttons { display: flex; gap: 4px }
figure .buttons button { padding: 4px 6px; font-size: 12px }
.poor { color: #c62828 }
.legend { color: #555; margin: 4px 0 }
</style></head><body>
<header>
  <button class="tab on" data-tab="nolabels">No labels</button>
  <button class="tab" data-tab="bad">Bad photos</button>
  <span class="info" id="count"></span>
  <span class="spacer"></span>
  <span id="controls"></span>
</header>
<div id="grid"></div>
<div id="prints" hidden></div>
<script>
let S = null, tab = "nolabels", page = 0;
const deleted = new Set();
const PER = 20, PRINTS_PER = 25;
const $ = s => document.querySelector(s);

async function load() {
  const r = await fetch("/state");
  if (r.status === 503) { $("#count").textContent = "loading (comparing label photos with their prints, see the console)"; setTimeout(load, 2000); return; }
  S = await r.json();
  S.deleted.forEach(s => deleted.add(s));
  render();
}

async function remove(sha1s, here) {
  sha1s = [...new Set(sha1s)].filter(s => !deleted.has(s));
  if (!sha1s.length) return;
  const others = new Set();
  for (const s of sha1s) for (const p of S.photo_prints[s] || []) if (p !== here) others.add(p);
  if (others.size) {
    const names = [...others].map(id => (S.prints.find(p => p.id === id) || {}).serial + " (" + id.slice(0, 10) + ")");
    if (!confirm(`${sha1s.length === 1 ? "This photo also holds" : "These photos also hold"} label photos of ${others.size} other print${others.size > 1 ? "s" : ""}:\n${names.join("\n")}\n\nDelete anyway?`)) return;
  }
  const r = await fetch("/delete", {method: "POST", body: JSON.stringify({photos: sha1s})});
  if (!r.ok) { alert(await r.text()); return; }
  (await r.json()).deleted.forEach(s => deleted.add(s));
  render();
}

function render() {
  document.querySelectorAll(".tab").forEach(b => b.classList.toggle("on", b.dataset.tab === tab));
  $("#grid").hidden = tab !== "nolabels";
  $("#prints").hidden = tab !== "bad";
  tab === "nolabels" ? renderNoLabels() : renderPrints();
}

function renderNoLabels() {
  const left = S.no_labels.filter(s => !deleted.has(s));
  const pages = Math.max(1, Math.ceil(left.length / PER));
  page = Math.min(page, pages - 1);
  const shown = left.slice(page * PER, page * PER + PER);
  $("#count").textContent = `${left.length} photos without label photos, the fewest matched features first; page ${page + 1} of ${pages}`;
  $("#controls").innerHTML = "";
  const all = button("Delete these " + shown.length, "danger", () => remove(shown));
  all.disabled = !shown.length;
  $("#controls").append(button("Previous", "", () => { page = Math.max(0, page - 1); render(); }),
                        button("Next", "", () => { page = Math.min(pages - 1, page + 1); render(); }), " ", all);
  const grid = $("#grid");
  grid.innerHTML = "";
  for (const s of shown) {
    const cell = document.createElement("div");
    cell.className = "cell";
    cell.innerHTML = `<a href="/photo/${s}" target="_blank"><img src="/thumb/${s}"></a><span class="name">${s.slice(0, 10)} matched ${S.matched[s]}</span>`;
    cell.append(button("Delete", "danger", () => remove([s])));
    grid.append(cell);
  }
}

function pct(x) { return (100 * x).toFixed(0).padStart(3) + " %"; }

function renderPrints() {
  const prints = S.prints.map(p => ({...p, label_photos: p.label_photos.filter(e => !deleted.has(e.photo))}))
                         .filter(p => p.label_photos.length);
  prints.forEach(p => p.left = p.label_photos.reduce((a, e) => a + e.badness, 0));
  prints.sort((a, b) => b.left - a.left);
  const pages = Math.max(1, Math.ceil(prints.length / PRINTS_PER));
  page = Math.min(page, pages - 1);
  $("#count").textContent = `${prints.length} prints, the worst first; page ${page + 1} of ${pages}`;
  $("#controls").innerHTML = "";
  $("#controls").append(button("Previous", "", () => { page = Math.max(0, page - 1); render(); $("#prints").scrollTop = 0; }),
                        button("Next", "", () => { page = Math.min(pages - 1, page + 1); render(); $("#prints").scrollTop = 0; }));
  const box = $("#prints");
  box.innerHTML = `<div class="legend">Badness = 1 - usable × resolution. Usable: the label's share in the photo and the cut, and within reach of the restored print's colours (0.15 mm blur). Resolution: the photo's px/mm at the label over 10, at most 1. "not compared": no other label photo of its family to compare with.</div>`;
  for (const p of prints.slice(page * PRINTS_PER, page * PRINTS_PER + PRINTS_PER)) {
    const div = document.createElement("div");
    div.className = "print";
    div.innerHTML = `<div class="restored">${p.has_image ? `<img loading="lazy" src="/print/${encodeURIComponent(p.id)}">` : ""}<div>${p.serial}<br>sum ${p.left.toFixed(2)}<br>${p.label_photos.length} label photo${p.label_photos.length > 1 ? "s" : ""}</div></div><div class="photos"></div>`;
    const list = div.querySelector(".photos");
    p.label_photos.forEach((e, i) => {
      const fig = document.createElement("figure");
      fig.innerHTML = `<a href="/photo/${e.photo}" target="_blank"><img loading="lazy" src="/label/${encodeURIComponent(e.key)}"></a>
        <figcaption>badness ${e.badness.toFixed(2)}<br>damage ${pct(e.damage)} off ${pct(e.off)}<br>${e.px_per_mm.toFixed(1).padStart(4)} px/mm${e.compared ? "" : " not compared"}${e.poor_fit ? '<br><span class="poor">poor fit</span>' : ""}</figcaption><div class="buttons"></div>`;
      const worse = p.label_photos.slice(i).map(x => x.photo);
      fig.querySelector(".buttons").append(button("Delete this and worse", "danger", () => remove(worse, p.id)),
                                          button("Delete", "danger", () => remove([e.photo], p.id)));
      list.append(fig);
    });
    box.append(div);
  }
}

function button(text, cls, f) {
  const b = document.createElement("button");
  b.textContent = text;
  if (cls) b.className = cls;
  b.onclick = f;
  return b;
}

document.querySelectorAll(".tab").forEach(b => b.onclick = () => { tab = b.dataset.tab; page = 0; render(); });
load();
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
            return self.send(tool.state())
        part, _, name = path[1:].partition("/")
        if part in ("thumb", "photo"):
            file = photos.all_photos().get(name)
            body = file and thumbnail(file, THUMB_PX if part == "thumb" else 4000)
            return self.send(body, "image/jpeg", cache=True) if body else self.send_error(404)
        if part == "label" and name in tool.crops:
            img = cv2.imread(os.path.join(GEN, "straighten", straighten.file_name(name)))
            if img is None:
                return self.send_error(404)
            img = publish.cut(img, *tool.crops[name])
            return self.send(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])[1].tobytes(), "image/jpeg", cache=True)
        if part == "print":
            file = restored(name) + ".avif"
            return self.send(open(file, "rb").read(), "image/avif", cache=True) if os.path.exists(file) else self.send_error(404)
        self.send_error(404)

    def do_POST(self):
        if self.path != "/delete" or tool is None:
            return self.send_error(404)
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        done = tool.delete([s for s in data.get("photos", []) if isinstance(s, str)])
        for s in done:
            print(f"deleted {s}", flush=True)
        self.send({"deleted": done})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8773
    tool = None
    server = ThreadingHTTPServer(("localhost", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"remove photos at http://localhost:{PORT}/ (ctrl-C to stop); the page waits until the photos are loaded",
          flush=True)
    tool = Tool()
    print(f"loaded: {len(tool.no_labels)} photos without label photos, {len(tool.prints)} prints", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
