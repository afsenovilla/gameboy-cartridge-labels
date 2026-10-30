import json, os, socket, sys, threading, urllib.parse, cv2, numpy as np
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photos
from cartridge import CGB_RECESS, RECESS, SHELLS, project
from fit_cartridge import load
from fit_label import OUT as FITS, label_pose
from review_fits import BUTTONS, PORT as FITS_PORT, VERDICTS as PLASTIC_VERDICTS, VERDICTS_GIVEN, dense, rounded_outline, same_fit as same_plastic, save_verdicts

# review-labels: a local page for judging fit-label's fits of the label (generated/fit-label/, make fit-label) by eye, a
# page of photos at a time. Each shows the recess straightened (the photo seen through the plastic's fit, perspective
# removed), with 5 mm around it, all at the same scale whatever the photo's resolution; the fitted label drawn red (a
# fit rejected for sticking out of the recess: orange). The labels farthest from the recess's middle
# come first. A verdict (reject, almost, accept; clicked again, it's taken back; or for all the page's photos not yet
# judged at once) is on the fit shown, and saved to reviews/labels.json with it: photo name -> [{"verdict",
# "label_mm_to_photo", "sha1"}...], one per fit judged, with the SHA-1 of the photo it judged; when fit-label changes, a verdict stays with the fit it judged. Labels
# placed by hand (make fit-by-hand) are kept by fit-label and shown as accepted.
# Where the plastic's fit turns out to be off, "Plastic: almost" beside the photo's name demotes it in reviews/fits.json:
# its verdict becomes almost, as in make review-fits (so fit-label drops the photo on its next run, and make fit-by-hand
# lists it first), and the label's fit, made on it, is rejected; clicked again, the verdicts on both are put back. Not while make review-fits runs, which rewrites that file.
# Usage: review_labels.py [port]
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8770
VERDICTS = "reviews/labels.json"
PER_PAGE = 24
# The straightened view: px per mm, and the margin around the recess (mm). Framed alike on both shells, around the
# recess's middle, as wide and high as the larger recess.
SCALE = 12
MARGIN = 5.0
FRAME = (max(r[2] - r[0] for r in (RECESS, CGB_RECESS)) + 2 * MARGIN, max(r[3] - r[1] for r in (RECESS, CGB_RECESS)) + 2 * MARGIN)
LABEL_RADIUS = 1.4
shown = lambda verdict: "accepted" if verdict == "great" else verdict


def straightened(path, fit):
    """The recess seen straight on, with the label drawn, as JPEG bytes: FRAME mm at SCALE px per mm."""
    photo = load(path)
    shell = SHELLS[fit["shell"]]
    recess = shell.recess
    H = np.asarray(fit["mm_to_photo"], np.float64)
    left, top = (recess[0] + recess[2] - FRAME[0]) / 2, (recess[1] + recess[3] - FRAME[1]) / 2
    to_mm = np.array([[1 / SCALE, 0, left], [0, 1 / SCALE, top], [0, 0, 1]])
    # Shrunk first to about twice the view's scale, so that a large photo isn't sampled sparsely (aliased).
    c = project(H, [[28.5, 37.5], [29.5, 37.5], [28.5, 38.5]])
    (ax, ay), (bx, by) = c[1] - c[0], c[2] - c[0]
    px_per_mm = np.sqrt(abs(ax * by - ay * bx))
    shrink = min(1.0, 2 * SCALE / px_per_mm)
    if shrink < 1:
        photo = cv2.resize(photo, None, fx=shrink, fy=shrink, interpolation=cv2.INTER_AREA)
        H = np.diag([shrink, shrink, 1]) @ H
    size = (round(FRAME[0] * SCALE), round(FRAME[1] * SCALE))
    view = cv2.warpPerspective(photo, H @ to_mm, size, flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderValue=(80, 80, 80))
    at = lambda pts: ((np.asarray(pts) - [left, top]) * SCALE * 4).round().astype(np.int32)  # 2 bits of subpixel
    draw = lambda pts, color: cv2.polylines(view, [at(pts)], True, color, 1, cv2.LINE_AA, shift=2)
    label = dense(rounded_outline(shell.label, LABEL_RADIUS))
    if "error" not in fit:
        draw(project(np.linalg.inv(H) @ np.diag([shrink, shrink, 1]) @ np.asarray(fit["label_mm_to_photo"]), label), (0, 0, 255))
    elif "offset_mm" in fit:
        draw(project(label_pose(*fit["offset_mm"], np.radians(fit["angle_degrees"]), fit["width_mm"], shell.label), label), (0, 150, 255))
    return cv2.imencode(".jpg", view, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes()


def notes(fit):
    if "error" in fit:
        return [("REJECTED: " if "sticks out" in fit["error"] else "") + fit["error"]]
    if "judged" in fit:
        return ["placed by hand: kept by fit-label"]
    dx, dy = fit["offset_mm"]
    found = [f'shifted {dx:+.2f}, {dy:+.2f} mm, turned {fit["angle_degrees"]:+.2f}°, {fit["width_mm"]:.2f} mm wide']
    if fit["width_at_limit"]:
        found.append("stopped at a width limit: fitted again at the median width")
    return found


def same_fit(verdict, fit):
    return "error" not in fit and verdict.get("sha1") == fit["sha1"] and np.allclose(verdict["label_mm_to_photo"], fit["label_mm_to_photo"])


class Review:
    """The label fits, the photos and the verdicts, read when the tool starts."""

    def __init__(self):
        self.paths = {photos.stem(n): os.path.join(photos.ROOT, s, system, n) for s, system, n, _ in photos.all_sources()}
        self.fits = {}
        sha1s = photos.sha1s()
        for name in sorted(os.listdir(FITS)):
            if name.endswith(".json") and name[:-5] in self.paths:
                fit = json.load(open(os.path.join(FITS, name)))
                # A fit made from another photo under the same name waits for its step to run again.
                if fit.get("sha1") == sha1s[name[:-5]]:
                    self.fits[name[:-5]] = fit
        # Farthest from the recess's middle first (the shift, plus the turn's reach at the label's corners); placed by
        # hand next; rejected last.
        reach = lambda f: np.hypot(*f["offset_mm"]) + 28 * abs(np.radians(f["angle_degrees"]))
        self.order = sorted(self.fits, key=lambda n: (2, 0) if "error" in self.fits[n] else (1, 0) if "judged" in self.fits[n] else (0, -reach(self.fits[n])))
        fitted = [n for n in self.order if "error" not in self.fits[n]]
        self.verdicts = json.load(open(VERDICTS)) if os.path.exists(VERDICTS) else {}
        self.groups = {"all": self.order, "Game Boy Color only": [n for n in fitted if self.fits[n]["shell"] == "cgb"],
                       # Fits without a verdict on them, or with one, as the tool starts.
                       "not judged": [n for n in fitted if self.current(n) is None],
                       **{v: [n for n in fitted if shown(self.current(n)) == v] for v in VERDICTS_GIVEN},
                       "rejected by fit-label": [n for n in self.order if "error" in self.fits[n]]}
        self.demoted = {}  # photo -> its plastic's verdicts before it was demoted in this run
        self.cache, self.lock = {}, threading.Lock()

    def image(self, name):
        """The straightened recess, rendered once (the last few pages are kept)."""
        with self.lock:
            if name in self.cache:
                return self.cache[name]
        image = straightened(self.paths[name], self.fits[name])
        with self.lock:
            self.cache[name] = image
            while len(self.cache) > 4 * PER_PAGE:
                self.cache.pop(next(iter(self.cache)))
        return image

    def current(self, name):
        """The verdict on the fit shown, or None; a label placed by hand is great."""
        if "judged" in self.fits[name]:
            return "great"
        return next((v["verdict"] for v in self.verdicts.get(name, []) if same_fit(v, self.fits[name])), None)

    def judge(self, names, verdict):
        """Gives the fits shown a verdict (None: takes it back), keeping the verdicts on other fits."""
        for name in names:
            others = [v for v in self.verdicts.get(name, []) if not same_fit(v, self.fits[name])]
            if verdict is not None:
                others.append({"verdict": verdict, "label_mm_to_photo": self.fits[name]["label_mm_to_photo"], "sha1": self.fits[name]["sha1"]})
            self.verdicts[name] = others
            if not others:
                del self.verdicts[name]
        save_verdicts(self.verdicts, VERDICTS)

    def summary(self):
        """Per group, how many fits there are and the verdicts on them (only those judging the current fit)."""
        counts = {}
        for group, names in self.groups.items():
            judged = [shown(self.current(n)) for n in names]
            counts[group] = {"fits": len(names), **{v: judged.count(v) for v in VERDICTS_GIVEN}}
        return counts

    def demote(self, name, demote):
        """Gives the plastic's fit the verdict almost in reviews/fits.json (read again first) and rejects the label's
        fit, or puts back the verdicts both had before."""
        verdicts = json.load(open(PLASTIC_VERDICTS)) if os.path.exists(PLASTIC_VERDICTS) else {}
        fit = self.fits[name]
        if demote:
            self.demoted[name] = (verdicts.get(name, []), self.verdicts.get(name, []))
            verdicts[name] = [v for v in self.demoted[name][0] if not same_plastic(v, fit)] + [{"verdict": "almost", "mm_to_photo": fit["mm_to_photo"], "sha1": fit["sha1"]}]
            if "error" not in fit and "judged" not in fit:
                self.judge([name], "rejected")
        else:
            verdicts[name], self.verdicts[name] = self.demoted.pop(name)
            if not self.verdicts[name]:
                del self.verdicts[name]
            save_verdicts(self.verdicts, VERDICTS)
        save_verdicts(verdicts, PLASTIC_VERDICTS)

    def page(self, group, number):
        names = self.groups[group][number * PER_PAGE:(number + 1) * PER_PAGE]
        items = []
        for name in names:
            fit = self.fits[name]
            others = [f'{v["verdict"]} on another fit' for v in self.verdicts.get(name, []) if v.get("sha1") == fit["sha1"] and not same_fit(v, fit)]
            items.append({"name": name, "path": self.paths[name], "judgeable": "error" not in fit and "judged" not in fit,
                          "notes": notes(fit) + others, "verdict": shown(self.current(name)), "demoted": name in self.demoted})
        return {"items": items, "pages": max(1, -(-len(self.groups[group]) // PER_PAGE))}


PAGE = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Review labels</title>
<style>
body{font:14px system-ui;margin:0;background:#f4f4f4;color:#222}
header{position:sticky;top:0;background:#fff;padding:8px 16px;border-bottom:1px solid #ddd;display:flex;gap:12px;align-items:center;flex-wrap:wrap;z-index:1}
#position{display:inline-block;width:12ch;text-align:center;font-variant-numeric:tabular-nums}
#summary{flex-basis:100%;color:#555;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-variant-numeric:tabular-nums}
main{padding:12px 16px;display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:12px}
section{background:#fff;border-radius:6px;padding:8px;display:flex;flex-direction:column;gap:6px;min-width:0}
.top{display:flex;gap:6px;align-items:center}
h2{flex:1;font-size:14px;margin:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
button.plastic{flex:none;width:17ch;font-size:12px;padding:2px 8px}button.plastic.on{background:#c70;color:#fff}
.photo{display:block;aspect-ratio:%ASPECT%;background:#eee}
.photo img{width:100%;height:100%;display:block}
.verdicts{display:flex;gap:6px}.verdicts button{flex:1}
section .verdicts{margin-top:auto}
button{font:inherit;padding:4px 10px;border:none;border-radius:0.3em}
button.on[data-verdict=rejected]{background:#b00;color:#fff}button.on[data-verdict=almost]{background:#c70;color:#fff}button.on[data-verdict=accepted]{background:#070;color:#fff}
.notes{margin:0;font-size:12px;color:#555}.notes b{color:#b00}
</style>
<header>
<select id="group"></select>
<button id="prev">← prev</button><span id="position"></span><button id="next">next →</button>
<span>Not yet judged on this page:</span><span class="verdicts" id="rest"></span>
<span id="summary"></span>
</header>
<main id="entries"></main>
<script>
const VERDICTS = %VERDICTS%;
const BUTTONS = %BUTTONS%;
let groups = [], group = "all", page = 0, pages = 1;
const $ = id => document.getElementById(id);
const esc = s => s.replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
async function load() {
  const data = await (await fetch("/list")).json();
  groups = data.groups;
  $("group").innerHTML = groups.map(g => `<option>${g}</option>`).join("");
  showSummary(data.summary);
  const [g, p] = decodeURIComponent(location.hash.slice(1)).split("/");
  if (groups.includes(g)) { group = g; page = Math.max(0, (parseInt(p) || 1) - 1); }
  $("group").value = group;
  show();
}
function showSummary(s) {
  $("summary").textContent = Object.entries(s).map(([g, c]) => `${g} ${c.fits}: ` + VERDICTS.map(v => `${c[v]} ${v}`).join(", ")).join(" · ");
}
async function show() {
  const data = await (await fetch(`/page/${encodeURIComponent(group)}/${page}`)).json();
  pages = data.pages;
  if (page >= pages) { page = pages - 1; return show(); }
  history.replaceState(null, "", "#" + encodeURIComponent(group) + "/" + (page + 1));
  $("position").textContent = `page ${page + 1} / ${pages}`;
  $("entries").innerHTML = data.items.map(item => `<section data-name="${esc(item.name)}" data-judged="${item.verdict ? 1 : ""}">
    <div class="top"><h2 title="${esc(item.path)}">${esc(item.name)}</h2><button class="plastic ${item.demoted ? "on" : ""}">${item.demoted ? "Plastic demoted" : "Plastic: almost"}</button></div>
    <a class="photo" href="/image/${encodeURIComponent(item.name)}" target="_blank"><img src="/image/${encodeURIComponent(item.name)}" loading="lazy"></a>
    <p class="notes">${item.notes.map(n => /^[A-Z ]+:/.test(n) ? `<b>${esc(n)}</b>` : esc(n)).join("<br>")}</p>
    ${item.judgeable ? `<div class="verdicts">${VERDICTS.map(v => `<button data-verdict="${v}" class="${item.verdict === v ? "on" : ""}">${BUTTONS[v]}</button>`).join("")}</div>` : ""}
  </section>`).join("");
  window.scrollTo(0, 0);
}
$("entries").onclick = async e => {
  const plastic = e.target.closest("button.plastic");
  if (plastic) {
    const demote = !plastic.classList.contains("on");  // clicked again: put back
    const response = await fetch("/plastic", {method: "POST", body: JSON.stringify({name: plastic.closest("section").dataset.name, demote})});
    if (!response.ok) return alert("Not changed: " + (await response.text()));
    const data = await response.json(), section = plastic.closest("section");
    plastic.classList.toggle("on", demote);
    plastic.textContent = demote ? "Plastic demoted" : "Plastic: almost";
    section.dataset.judged = data.verdict ? 1 : "";
    section.querySelectorAll(".verdicts button").forEach(b => b.classList.toggle("on", b.dataset.verdict === data.verdict));
    showSummary(data.summary);
    return;
  }
  const button = e.target.closest("button[data-verdict]");
  if (!button) return;
  const verdict = button.classList.contains("on") ? null : button.dataset.verdict;  // clicked again: taken back
  judge([button.closest("section")], verdict);
};
$("rest").innerHTML = VERDICTS.map(v => `<button data-verdict="${v}">${BUTTONS[v]}</button>`).join("");
$("rest").onclick = e => {
  const button = e.target.closest("button[data-verdict]");
  if (button) judge([...document.querySelectorAll("section")].filter(s => s.querySelector(".verdicts") && !s.dataset.judged), button.dataset.verdict);
};
async function judge(sections, verdict) {
  if (!sections.length) return;
  const names = sections.map(s => s.dataset.name);
  const data = await (await fetch("/verdict", {method: "POST", body: JSON.stringify({names, verdict})})).json();
  for (const s of sections) {
    s.dataset.judged = verdict ? 1 : "";
    s.querySelectorAll(".verdicts button").forEach(b => b.classList.toggle("on", b.dataset.verdict === verdict));
  }
  showSummary(data.summary);
}
const go = p => { if (p >= 0 && p < pages) { page = p; show(); } };
$("group").onchange = e => { group = e.target.value; page = 0; show(); };
$("prev").onclick = () => go(page - 1);
$("next").onclick = () => go(page + 1);
document.onkeydown = e => {
  if (e.target.tagName === "SELECT") return;
  if (e.key === "ArrowLeft") go(page - 1);
  if (e.key === "ArrowRight") go(page + 1);
};
load();
</script>
"""


class Handler(BaseHTTPRequestHandler):
    def send(self, body, kind="application/json"):
        body = json.dumps(body).encode() if kind == "application/json" else body
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parts = [urllib.parse.unquote(p) for p in self.path.split("?")[0].split("/")[1:]]
        if parts == [""]:
            page = PAGE.replace("%VERDICTS%", json.dumps(VERDICTS_GIVEN)).replace("%BUTTONS%", json.dumps(BUTTONS)).replace("%ASPECT%", f"{FRAME[0]}/{FRAME[1]}")
            self.send(page.encode(), "text/html; charset=utf-8")
        elif parts == ["list"]:
            self.send({"groups": list(review.groups), "summary": review.summary()})
        elif len(parts) == 3 and parts[0] == "page" and parts[1] in review.groups and parts[2].isdigit():
            self.send(review.page(parts[1], int(parts[2])))
        elif len(parts) == 2 and parts[0] == "image" and parts[1] in review.fits:
            self.send(review.image(parts[1]), "image/jpeg")
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path not in ("/verdict", "/plastic"):
            return self.send_error(404)
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/plastic":
            if data["name"] not in review.fits or data["demote"] == (data["name"] in review.demoted):
                return self.send_error(400)
            with socket.socket() as s:
                if s.connect_ex(("localhost", FITS_PORT)) == 0:
                    return self.send_error(409, "make review-fits is running: stop it first, as it rewrites reviews/fits.json")
            review.demote(data["name"], data["demote"])
            return self.send({"summary": review.summary(), "verdict": shown(review.current(data["name"]))})
        if any(n not in review.fits or "error" in review.fits[n] or "judged" in review.fits[n] for n in data["names"]) or data["verdict"] not in VERDICTS_GIVEN + (None,):
            return self.send_error(400)
        review.judge(data["names"], data["verdict"])
        self.send({"summary": review.summary()})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    review = Review()
    print(f"{len(review.fits)} label fits, {len(review.verdicts)} with verdicts; review them at http://localhost:{PORT}/ (ctrl-C to stop)")
    ThreadingHTTPServer(("localhost", PORT), Handler).serve_forever()
