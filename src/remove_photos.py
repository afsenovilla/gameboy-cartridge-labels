# remove-photos: a tool, not a step: a local page for deleting photos from photos/ (the file and its record in
# photo-sources.json, photos.delete). The steps drop what they made from a deleted photo on their next run. Two tabs:
#   - Unused: the photos none of whose label photos is used (unused), 5 x 4 at a time, the fewest matched features
#     first (its distinct points among the inliers of its matches with other photos, match's), each with why: delete
#     one, OK one (a good photo: kept in OK_FILE, never listed again), or delete the page's photos not OK-ed. No
#     confirm(): they're unused, though prints.json may list them (a family of approximate cuts). (Before 2026-11-12
#     only the photos find found no label photo in; on the full set, 48 of the 71 matched nothing.)
#   - Restored prints: every print's restored image (restore), 6 x 3 at a time, the unmarked first, each to mark Good or
#     Bad (MARKS_FILE). A mark is of that image file (its SHA-1): a print restored differently is unmarked again.
# The tabs keep their pages as loaded (the user, 2026-11-12: a photo deleted or OK-ed leaves its place, nothing moves).
#   - Bad photos: every print (prints.json) with its label photos, the worst first; prints by the sum of their label
#     photos' badness (many bad label photos, and how bad), label photos within a print by their own badness. Each label
#     photo: "Delete this and worse" (the photos of it and of the print's label photos after it) or "Delete".
# In Bad photos, deleting a photo that also holds label photos of other prints asks first (confirm()).
# Badness of a label photo: 1 - usable x resolution, both 0..1:
#   usable: the share of the label (restore's crop) that is in the photo, inside the sticker's cut, and matches the
#     reference: its straightened image, colours evened to the reference (restore.even_to), both blurred over BLUR_MM,
#     within DAMAGE_DE (Oklab) of it. Damage, glare, dirt, blur and a part off the photo all count against it.
#   resolution: the photo's pixels per mm at the label (from solve's fit) over FULL_PX_PER_MM, at most 1.
# The reference, never including the label photo itself (leave-one-out, 2026-11-12; the restored print it was before
#   holds the label photo's own damage, which then hid part of it): in a print of REFERENCE_MIN or more label photos, the
#   median of the print's other label photos (up to REFERENCE_MAX of them; each straightened, its colours evened to the
#   median of all, filled from its nearest valid pixel outside its cut), compared only where at least one of them is on
#   its photo; otherwise the restored print of the print with the most label photos in its family; none if there's
#   neither (then only the part off the photo or the cut counts).
# Measured on the full set (25 prints of 4 or more label photos, against the restored print, before leave-one-out):
#   over DAMAGE_DE, 0.1 % of the label for the cleanest, 5 % at the median, 38 % for the worst; at 0.05 the clean ones
#   already differed on 10-20 % (noise, slight blur). Against the user's deletions (2026-11-12, the 113 compared photos
#   deleted from the first pages): 84 % over 0.1 damage, 62 % over 0.2.
# Computed when the page starts, kept in generated/remove-photos/badness.json until prints.json, solve.json, a restored
# print is newer, or the settings (BLUR_MM, DAMAGE_DE, REFERENCE_MIN, REFERENCE_MAX, the method) changed.
# Usage: remove_photos.py [port]
import json, os, sys, threading, urllib.parse, warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cv2, numpy as np
import photos, steps, straighten, cuts, restore, shapes, publish

GEN = "generated"
BLUR_MM = 0.15          # what a slightly misregistered or less sharp label photo still matches
DAMAGE_DE = 0.08        # Oklab distance to the reference over which a pixel is damaged
FULL_PX_PER_MM = 10     # a photo this sharp at the label or more loses nothing by its resolution
REFERENCE_MIN = 3       # a print with this many label photos: each compared with the median of its others
REFERENCE_MAX = 30      # the others in that median, at most
THUMB_PX = 600
CACHE = os.path.join(GEN, "remove-photos", "badness.json")
MARKS_FILE = "print-marks.json"  # {image sha1: {mark: good|bad, serial, print, label_photos, date}}: restored prints judged
OK_FILE = "ok-photos.json"  # {sha1: date OK-ed}: photos the user judged good in Unused, not listed there again
lock = threading.Lock()


def sha1_file(path):
    import hashlib
    return hashlib.sha1(open(path, "rb").read()).hexdigest()


def restored(pid):
    return os.path.join(GEN, "restore", straighten.file_name(pid)[:-5])


def load_label(key, shape, crop):
    """A label photo's straightened image cropped (BGR 0..1) and where it counts (on the photo, inside its cut), or None."""
    img = cv2.imread(os.path.join(GEN, "straighten", straighten.file_name(key)))
    if img is None:
        return None
    size, px_to_mm = straighten.canvas(shape)
    valid = img.max(2) > 1
    cut = straighten.load_cut(GEN, key)
    if cut is not None:
        valid &= cuts.mask(cut, shape, size, px_to_mm)
    x, y, w, h = publish.crop_box(shape, crop)
    return img[y:y + h, x:x + w].astype(np.float32) / 255, valid[y:y + h, x:x + w]


def damage(img, valid, ref, ref_valid):
    """The share of the label where img differs from ref by over DAMAGE_DE (both blurred over BLUR_MM), counted where
    both are valid; img's colours evened to ref first."""
    both = valid & ref_valid
    if both.sum() < 100:
        return None
    s = BLUR_MM * straighten.PX_PER_MM
    a = restore.to_oklab(cv2.GaussianBlur(restore.filled(restore.even_to(img, ref, both), valid), (0, 0), s))
    b = restore.to_oklab(cv2.GaussianBlur(restore.filled(ref, ref_valid), (0, 0), s))
    return float(((np.linalg.norm(a - b, axis=2) > DAMAGE_DE) & both).mean())


def result(key, valid, dmg, ref):
    coverage = float(valid.mean())
    return key, {"coverage": round(coverage, 3), "damage": round(dmg or 0.0, 3), "usable": round(coverage - (dmg or 0.0), 3),
                 "reference": ref if dmg is not None else None}


def badness_of(job):
    """[(key, {usable, coverage, damage, reference})] for one job: ("others", keys, shape, crop): each label photo against
    the median of the others; ("print", keys, shape, crop, ref_id): each against that print's restored image."""
    kind, keys, shape, crop = job[:4]
    loaded = [(k, load_label(k, shape, crop)) for k in keys]
    loaded = [(k, e) for k, e in loaded if e is not None]
    out = []
    if kind == "others" and len(loaded) >= REFERENCE_MIN:
        dmgs = against_others([e for _, e in loaded])
        return [result(k, e[1], d, "others") for (k, e), d in zip(loaded, dmgs)]
    ref_id = job[4] if kind == "print" else None
    # a print restore made no image for (fewer than restore.MIN_PHOTOS): no reference (and no OpenCV warning per photo)
    ref = cv2.imread(restored(ref_id) + ".avif") if ref_id and os.path.exists(restored(ref_id) + ".avif") else None
    for k, (img, valid) in loaded:
        dmg = None
        if ref is not None and ref.shape[:2] == img.shape[:2]:
            dmg = damage(img, valid, ref.astype(np.float32) / 255, np.ones(valid.shape, bool))
        out.append(result(k, valid, dmg, ref_id))
    return out


def against_others(entries):
    """Each label photo's damage (image, valid) against the median of the others (up to REFERENCE_MAX), all evened to the
    median of all first."""
    imgs = np.stack([e[0] for e in entries])
    valids = np.stack([e[1] for e in entries])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # pixels no label photo covers
        median = lambda idx: np.nan_to_num(np.nanmedian(np.where(valids[idx][..., None], imgs_e[idx], np.nan), axis=0))
        imgs_e = imgs
        median_all = median(list(range(len(entries))))
        imgs_e = np.stack([restore.filled(restore.even_to(i, median_all, v), v) for i, v in zip(imgs, valids)])
        out = []
        for n, (img, valid) in enumerate(entries):
            others = [m for m in range(len(entries)) if m != n][:REFERENCE_MAX]
            out.append(damage(img, valid, median(others), valids[others].any(0)))
    return out


def jobs_of(prints):
    """badness_of's jobs: a print of REFERENCE_MIN or more label photos compared within itself; another against the
    print with the most label photos in its family (none if that is itself)."""
    by_family = {}
    for p in prints:
        by_family.setdefault(p["family"], []).append(p)
    jobs = []
    for p in prints:
        if len(p["keys"]) >= REFERENCE_MIN:
            jobs.append(("others", p["keys"], p["shape"], crop_of(p["id"])))
        else:
            ref = max(by_family[p["family"]], key=lambda q: (len(q["keys"]), q is p))
            jobs.append(("print", p["keys"], p["shape"], crop_of(ref["id"]) if ref is not p else crop_of(p["id"]),
                         None if ref is p else ref["id"]))
    return jobs


def crop_of(pid):
    """restore's crop of a print (its family's), or None."""
    path = restored(pid) + ".json"
    return json.load(open(path))["crop"] if os.path.exists(path) else None


def badness(prints):
    """key -> {coverage, damage, usable, reference}, from the cache where it's still good."""
    inputs = [os.path.join(GEN, "prints", "prints.json"), os.path.join(GEN, "solve", "solve.json")]
    settings = [BLUR_MM, DAMAGE_DE, REFERENCE_MIN, REFERENCE_MAX, "leave-one-out"]
    newest = max(os.path.getmtime(f) for f in inputs)
    restore_dir = os.path.join(GEN, "restore")
    newest = max([newest] + [os.path.getmtime(os.path.join(restore_dir, f)) for f in os.listdir(restore_dir)])
    if os.path.exists(CACHE) and os.path.getmtime(CACHE) >= newest:
        cached = json.load(open(CACHE))
        if cached.get("settings") == settings:
            print("badness: from the cache", flush=True)
            return cached["badness"]
    jobs = jobs_of(prints)
    jobs.sort(key=lambda j: -len(j[1]))  # the biggest prints first, so the pool ends evenly
    out = {}
    total = sum(len(j[1]) for j in jobs)
    print(f"comparing {total} label photos ({len(jobs)} prints)", flush=True)
    done = 0
    with Pool(8) as pool:
        for n, res in enumerate(pool.imap_unordered(badness_of, jobs), 1):
            for key, b in res:
                out[key] = b
            done += len(res)
            if n % 200 == 0 or n == len(jobs):
                print(f"compared {n} of {len(jobs)} prints", flush=True)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    steps.write_json(CACHE, {"settings": settings, "badness": out})
    return out


def unused(all_photos, found, solved):
    """sha1 -> why, for the photos none of whose label photos is used: find found none in it, or each is unsolved, a
    poor fit, or an approximate cut whose family has no precise fit (alone in its family, or among approximate cuts
    only: a box's art matching other photos of the box, 2026-11-12). A label photo merged into another (solve: the
    same sticker) is that one."""
    import solve as solve_step
    precise_families = {r["family"] for r in solved.values() if not solve_step.poor_fit(r) and not solve_step.approximate_cut(r)}
    def why_not(k):
        r = solved.get(k)
        if r is None:
            return "unsolved"
        if solve_step.poor_fit(r):
            return "poor fit"
        if solve_step.approximate_cut(r) and r["family"] not in precise_families:
            return "approximate cut alone" if r["family_size"] <= 1 else "approximate cuts only in its family"
        return None
    merged = {d for r in solved.values() for d in r.get("merged", [])}
    of_photo = {}
    for lp in found:
        if lp["key"] not in merged:
            of_photo.setdefault(lp["photo"], []).append(why_not(lp["key"]))
    out = {}
    for s in all_photos:
        whys = of_photo.get(s)
        if not whys:
            out[s] = "no label photo found"
        elif all(whys):
            out[s] = ", ".join(sorted(set(whys)))
    return out


class Tool:
    def __init__(self):
        import solve as solve_step
        say = lambda m: print(m, flush=True)
        say("loading photos/, find's, solve's and prints' results")
        self.photos = photos.all_photos()
        self.ok = json.load(open(OK_FILE)) if os.path.exists(OK_FILE) else {}
        self.marks = json.load(open(MARKS_FILE)) if os.path.exists(MARKS_FILE) else {}
        found = json.load(open(os.path.join(GEN, "find", "label-photos.json")))["label_photos"]
        prints = json.load(open(os.path.join(GEN, "prints", "prints.json")))["prints"]
        solved = json.load(open(os.path.join(GEN, "solve", "solve.json")))["label_photos"]
        self.why = unused(self.photos, found, solved)
        say(f"{len(self.why)} unused photos of {len(self.photos)}; counting their matched features")
        self.matched = matched_features(set(self.why))
        self.unused = sorted(self.why, key=lambda s: self.matched[s])
        say("the label photos' badness")
        bad = badness(prints)
        say(f"listing {len(prints)} prints")
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
                                "poor_fit": solve_step.poor_fit(r)})
                self.crops[k] = (p["shape"], crop)
            entries.sort(key=lambda e: -e["badness"])
            image = restored(p["id"]) + ".avif"
            self.prints.append({"id": p["id"], "serial": p.get("serial") or p.get("release") or "?",
                                "has_image": os.path.exists(image),
                                "image_sha1": sha1_file(image) if os.path.exists(image) else None,
                                "score": round(sum(e["badness"] for e in entries), 3), "label_photos": entries})
        self.prints.sort(key=lambda p: -p["score"])

    def state(self):
        have = set(photos.all_photos())
        photo_prints = {}
        for p in self.prints:
            for e in p["label_photos"]:
                photo_prints.setdefault(e["photo"], []).append(p["id"])
        return {"unused": [s for s in self.unused if s in have], "ok": sorted(self.ok),
                "marks": {k: v["mark"] for k, v in self.marks.items()}, "matched": self.matched,
                "why": self.why,
                "prints": self.prints, "photo_prints": photo_prints,
                "deleted": sorted((set(self.photos) | set(photo_prints)) - have)}  # gone, also before the page started

    def set_ok(self, sha1, ok):
        import datetime
        with lock:
            if ok:
                self.ok[sha1] = datetime.date.today().isoformat()
            else:
                self.ok.pop(sha1, None)
            steps.write_json(OK_FILE, dict(sorted(self.ok.items())))

    def set_mark(self, pid, mark):
        """Marks print pid's restored image good or bad (None: unmarks it); False if it has no image now."""
        import datetime
        p = next((p for p in self.prints if p["id"] == pid), None)
        if p is None or not p["image_sha1"]:
            return False
        with lock:
            if mark is None:
                self.marks.pop(p["image_sha1"], None)
            else:
                self.marks[p["image_sha1"]] = {"mark": mark, "serial": p["serial"], "print": pid,
                                               "label_photos": [e["key"] for e in p["label_photos"]],
                                               "date": datetime.date.today().isoformat()}
            steps.write_json(MARKS_FILE, dict(sorted(self.marks.items())))
        return True

    def delete(self, sha1s):
        """Deletes those of sha1s still in photos/; returns all of sha1s no longer there."""
        done = []
        with lock:
            have = photos.all_photos()
            for s in sha1s:
                if s in have:
                    photos.delete(s)
                    print(f"deleted {s}", flush=True)
                done.append(s)
        return done


def matched_features(wanted):
    """sha1 -> how many distinct points of the photo are inliers of its matches with other photos, for those wanted."""
    points = {s: [] for s in wanted}
    folder = os.path.join(GEN, "match")
    files = [f for f in os.listdir(folder) if f.endswith(".npz")]
    for n, f in enumerate(files, 1):
        if n % 1000 == 0 or n == len(files):
            print(f"matched features: {n} of {len(files)} match files read", flush=True)
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
[hidden] { display: none !important }
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
#grid .cell .buttons { position: absolute; right: 4px; bottom: 4px; display: flex; gap: 4px }
#grid .cell.ok { outline: 4px solid #2e7d32; outline-offset: -4px }
button.ok { background: #2e7d32; color: #fff }
.hole { background: #eee !important; color: #999; border: 2px dashed #ccc }
figure.hole { min-height: 120px; display: flex; align-items: center; justify-content: center }
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
#marks { display: grid; grid-template-columns: repeat(6, 1fr); grid-template-rows: repeat(3, 1fr); gap: 6px; padding: 6px; height: calc(100% - 48px) }
#marks .cell { position: relative; min-height: 0; background: #ddd; display: flex; align-items: center; justify-content: center; overflow: hidden; padding-bottom: 34px }
#marks img { max-width: 100%; max-height: 100%; object-fit: contain }
#marks .name { position: absolute; left: 4px; top: 4px; background: #fffc; padding: 0 4px; font: 11px ui-monospace, monospace }
#marks .buttons { position: absolute; left: 4px; right: 4px; bottom: 4px; display: flex; gap: 4px; justify-content: center }
#marks .cell.good, .print.good { outline: 4px solid #2e7d32; outline-offset: -4px }
#marks .cell.bad, .print.bad { outline: 4px solid #c62828; outline-offset: -4px }
button.bad { background: #c62828; color: #fff }
</style></head><body>
<header>
  <button class="tab on" data-tab="nolabels">Unused</button>
  <button class="tab" data-tab="bad">Bad photos</button>
  <button class="tab" data-tab="marks">Restored prints</button>
  <span class="info" id="count"></span>
  <span class="spacer"></span>
  <span id="controls"></span>
</header>
<div id="grid"></div>
<div id="prints" hidden></div>
<div id="marks" hidden></div>
<script>
let S = null, tab = "nolabels", page = 0, unusedList = [], printList = [], markList = [];
const MARKS_PER = 18;
const deleted = new Set(), ok = new Set();
const PER = 20, PRINTS_PER = 25;
const $ = s => document.querySelector(s);

async function load() {
  const r = await fetch("/state");
  if (r.status === 503) { $("#count").textContent = "loading (comparing label photos with their prints, see the console)"; setTimeout(load, 2000); return; }
  S = await r.json();
  S.deleted.forEach(s => deleted.add(s));
  S.ok.forEach(s => ok.add(s));
  // the lists as loaded: a photo deleted or OK-ed from here on leaves its place
  unusedList = S.unused.filter(s => !deleted.has(s) && !ok.has(s));
  printList = S.prints.map(p => ({...p, label_photos: p.label_photos.filter(e => !deleted.has(e.photo))}))
                      .filter(p => p.label_photos.length);
  const withImage = S.prints.filter(p => p.image_sha1);
  markList = [...withImage.filter(p => !S.marks[p.image_sha1]), ...withImage.filter(p => S.marks[p.image_sha1])];
  render();
}

async function setMark(p, mark) {
  const r = await fetch("/mark", {method: "POST", body: JSON.stringify({print: p.id, mark})});
  if (!r.ok) { alert(await r.text()); return; }
  if (mark) S.marks[p.image_sha1] = mark; else delete S.marks[p.image_sha1];
  render();
}

function markButtons(p) {
  const m = S.marks[p.image_sha1];
  return [button(m === "good" ? "Good ✓" : "Good", m === "good" ? "ok" : "", () => setMark(p, m === "good" ? null : "good")),
          button(m === "bad" ? "Bad ✓" : "Bad", m === "bad" ? "bad" : "", () => setMark(p, m === "bad" ? null : "bad"))];
}

function renderMarks() {
  const pages = Math.max(1, Math.ceil(markList.length / MARKS_PER));
  page = Math.min(page, pages - 1);
  const marked = markList.filter(p => S.marks[p.image_sha1]).length;
  $("#count").textContent = `${markList.length} restored prints, ${marked} marked, the unmarked first (as when the page was loaded); page ${page + 1} of ${pages}`;
  $("#controls").innerHTML = "";
  $("#controls").append(button("Previous", "", () => { page = Math.max(0, page - 1); render(); }),
                        button("Next", "", () => { page = Math.min(pages - 1, page + 1); render(); }));
  const box = $("#marks");
  box.innerHTML = "";
  for (const p of markList.slice(page * MARKS_PER, page * MARKS_PER + MARKS_PER)) {
    const cell = document.createElement("div");
    cell.className = "cell " + (S.marks[p.image_sha1] || "");
    cell.innerHTML = `<a href="/print/${encodeURIComponent(p.id)}" target="_blank"><img src="/print/${encodeURIComponent(p.id)}"></a><span class="name">${p.serial} (${p.label_photos.length} photos)</span><span class="buttons"></span>`;
    cell.querySelector(".buttons").append(...markButtons(p));
    box.append(cell);
  }
}

async function setOk(s, value) {
  const r = await fetch("/ok", {method: "POST", body: JSON.stringify({photo: s, ok: value})});
  if (!r.ok) { alert(await r.text()); return; }
  value ? ok.add(s) : ok.delete(s);
  render();
}

async function remove(sha1s, here, ask = true) {
  sha1s = [...new Set(sha1s)].filter(s => !deleted.has(s));
  if (!sha1s.length) return;
  const others = new Set();
  if (ask) for (const s of sha1s) for (const p of S.photo_prints[s] || []) if (p !== here) others.add(p);
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
  $("#marks").hidden = tab !== "marks";
  tab === "nolabels" ? renderNoLabels() : tab === "bad" ? renderPrints() : renderMarks();
}

function renderNoLabels() {
  const left = unusedList.filter(s => !deleted.has(s) && !ok.has(s)).length;
  const pages = Math.max(1, Math.ceil(unusedList.length / PER));
  page = Math.min(page, pages - 1);
  const shown = unusedList.slice(page * PER, page * PER + PER);
  const doomed = shown.filter(s => !deleted.has(s) && !ok.has(s));
  $("#count").textContent = `${left} unused photos left to judge (no label photo used; OK-ed ones aren't listed), the fewest matched features first; page ${page + 1} of ${pages}`;
  $("#controls").innerHTML = "";
  const all = button(`Delete the ${doomed.length} not OK`, "danger", () => remove(doomed, null, false));
  all.disabled = !doomed.length;
  $("#controls").append(button("Previous", "", () => { page = Math.max(0, page - 1); render(); }),
                        button("Next", "", () => { page = Math.min(pages - 1, page + 1); render(); }), " ", all);
  const grid = $("#grid");
  grid.innerHTML = "";
  for (const s of shown) {
    const cell = document.createElement("div");
    if (deleted.has(s)) {
      cell.className = "cell hole";
      cell.textContent = "deleted";
      grid.append(cell);
      continue;
    }
    cell.className = "cell" + (ok.has(s) ? " ok" : "");
    cell.innerHTML = `<a href="/photo/${s}" target="_blank"><img src="/thumb/${s}"></a><span class="name">${s.slice(0, 10)} matched ${S.matched[s]}<br>${S.why[s]}</span><span class="buttons"></span>`;
    cell.querySelector(".buttons").append(
      ok.has(s) ? button("OK ✓", "ok", () => setOk(s, false)) : button("OK", "", () => setOk(s, true)),
      button("Delete", "danger", () => remove([s], null, false)));
    grid.append(cell);
  }
}

function pct(x) { return (100 * x).toFixed(0).padStart(3) + " %"; }

function renderPrints() {
  const prints = printList;  // as loaded: a deleted label photo leaves a hole
  prints.forEach(p => p.left = p.label_photos.filter(e => !deleted.has(e.photo)).reduce((a, e) => a + e.badness, 0));
  const pages = Math.max(1, Math.ceil(prints.length / PRINTS_PER));
  page = Math.min(page, pages - 1);
  $("#count").textContent = `${prints.length} prints, the worst first (as when the page was loaded); page ${page + 1} of ${pages}`;
  $("#controls").innerHTML = "";
  $("#controls").append(button("Previous", "", () => { page = Math.max(0, page - 1); render(); $("#prints").scrollTop = 0; }),
                        button("Next", "", () => { page = Math.min(pages - 1, page + 1); render(); $("#prints").scrollTop = 0; }));
  const box = $("#prints");
  box.innerHTML = `<div class="legend">Badness = 1 - usable × resolution. Usable: the label's share in the photo and the cut, and within reach of the restored print's colours (0.15 mm blur). Resolution: the photo's px/mm at the label over 10, at most 1. "not compared": no other label photo of its family to compare with.</div>`;
  for (const p of prints.slice(page * PRINTS_PER, page * PRINTS_PER + PRINTS_PER)) {
    const div = document.createElement("div");
    div.className = "print " + (p.image_sha1 && S.marks[p.image_sha1] || "");
    div.innerHTML = `<div class="restored">${p.has_image ? `<img loading="lazy" src="/print/${encodeURIComponent(p.id)}">` : ""}<div>${p.serial}<br>sum ${p.left.toFixed(2)}<br>${p.label_photos.filter(e => !deleted.has(e.photo)).length} label photo(s) left</div></div><div class="photos"></div>`;
    const list = div.querySelector(".photos");
    if (p.image_sha1) { const b = document.createElement("div"); b.className = "buttons"; b.append(...markButtons(p)); div.querySelector(".restored").append(b); }
    p.label_photos.forEach((e, i) => {
      const fig = document.createElement("figure");
      if (deleted.has(e.photo)) {
        fig.className = "hole";
        fig.textContent = "deleted";
        list.append(fig);
        return;
      }
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
        if self.path not in ("/delete", "/ok", "/mark") or tool is None:
            return self.send_error(404)
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/mark":
            mark = data.get("mark")
            if mark not in ("good", "bad", None) or not tool.set_mark(data.get("print"), mark):
                return self.send_error(400)
            return self.send({"marked": data.get("print")})
        if self.path == "/ok":
            if not isinstance(data.get("photo"), str):
                return self.send_error(400)
            tool.set_ok(data["photo"], bool(data.get("ok")))
            return self.send({"ok": data["photo"]})
        done = tool.delete([s for s in data.get("photos", []) if isinstance(s, str)])
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
    print(f"loaded: {len(tool.unused)} unused photos, {len(tool.prints)} prints", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
