import json, os, sys, threading, urllib.parse, cv2, numpy as np
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photos
from cartridge import CGB_ARROW_HEIGHT, CGB_ARROW_TOP, CGB_ARROW_WIDTH, RECESS_RADIUS, SHELLS, cgb_body_outline, corners_of, groove_edges, shell_of
from fit_cartridge import OUT as FITS, VERDICTS, load
from name_photos import review_running
from review_fits import arrow_outline, bevel_lines, dense, face_outline, pill_outline, rounded_outline, same_fit, save_verdicts, shown

# fit-by-hand: a local page for placing the plastic and the label by hand, one photo at a time, where fit-cartridge's
# fit (generated/fit-cartridge/, make fit-cartridge) is off: those judged almost first (make review-fits), then the
# rejected ones and the photos it couldn't fit. A photo starts from its fit (else the model in the box fit-cartridge
# cropped to, else in the middle), or from the last fit placed by hand. The recess's corners (green squares) are
# dragged onto the photo's; the dots in the middle of its sides slide one side through the perspective. Once "Label
# placed" is ticked, the label (cyan) shows: a rectangle in the recess, moving with it: its corners turn it about its
# center, the dots in its sides move one side, the cross moves it. A magnifier shows 6 mm around the handle held. Saving gives the placement the verdict
# "great" in reviews/fits.json: {"verdict": "great", "mm_to_photo", "sha1": the photo's}, with "label_mm_to_photo" (the label's model,
# cartridge's shell.label, to the photo's pixels) once the label has been placed. Like any verdict it judges that fit
# alone; fit-cartridge keeps it rather than fitting the photo again. Saved again in the same run, a photo's placement
# replaces the one saved before; the verdicts on other fits are kept. make review-fits and make name-photos rewrite that
# file too, so this one doesn't run alongside review-fits, and the file is read again before each save.
# Usage: fit_by_hand.py [port]
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8769


def homography(src, dst):
    H = cv2.getPerspectiveTransform(np.float32(src), np.float32(dst))
    return H / H[2, 2]


def project(H, pts):
    p = np.c_[pts, np.ones(len(pts))] @ np.asarray(H).T
    return p[:, :2] / p[:, 2:]


def model(shell):
    """A shell's model as the page draws it, in mm: the recess's and the label's corners, and the lines [points,
    color, dashed, closed] (as review-fits draws them)."""
    lines = [[dense(rounded_outline(shell.recess, RECESS_RADIUS)), "#3d3", False, True]]
    if shell.name == "cgb":
        half = CGB_ARROW_WIDTH / 2
        arrow = arrow_outline(0.15, 0.25, top=CGB_ARROW_TOP, half_width=half, half_angle=np.arctan2(half, CGB_ARROW_HEIGHT))
        lines += [[cgb_body_outline(), "#f33", False, True], [arrow, "#f90", False, True]]
    else:
        lines += [[dense(face_outline()), "#f33", False, True], *[[dense(l, False), "#f33", True, False] for l in bevel_lines()],
                  [arrow_outline(), "#f90", False, True], [pill_outline(), "#f90", False, True], *[[np.array(e), "#f90", False, False] for e in groove_edges()]]
    return {"recess": corners_of(shell.recess).tolist(), "label": corners_of(shell.label).tolist(),
            "lines": [[np.round(points, 3).tolist(), color, dashed, closed] for points, color, dashed, closed in lines]}


class Hand:
    """The photos to place, their fits and the verdicts, read when the tool starts."""

    def __init__(self):
        self.paths = {photos.stem(n): os.path.join(photos.ROOT, s, system, n) for s, system, n, _ in photos.all_sources()}
        self.fits = {}
        self.sha1s = sha1s = photos.sha1s()
        for name in sorted(os.listdir(FITS)):
            if name.endswith(".json") and name[:-5] in self.paths:
                fit = json.load(open(os.path.join(FITS, name)))
                # A fit made from another photo under the same name waits for its step to run again.
                if fit.get("sha1") == sha1s[name[:-5]]:
                    self.fits[name[:-5]] = fit
        verdicts = self.verdicts()
        current = lambda n: "error" not in self.fits[n] and next((shown(v["verdict"]) for v in verdicts.get(n, []) if same_fit(v, self.fits[n])), None)
        names = sorted(self.fits)
        self.groups = {"almost": [n for n in names if current(n) == "almost"],
                       "rejected": [n for n in names if current(n) == "rejected"],
                       "not fitted": [n for n in names if "error" in self.fits[n]],
                       "not judged": [n for n in names if "error" not in self.fits[n] and current(n) is None],
                       "all": names}
        self.placed = {}  # photo -> the placement saved in this run, which saving it again replaces
        self.cache, self.lock = {}, threading.Lock()

    @staticmethod
    def verdicts():
        return json.load(open(VERDICTS)) if os.path.exists(VERDICTS) else {}

    def shell(self, name):
        fit = self.fits[name]
        return SHELLS[fit["shell"]] if "shell" in fit else shell_of(photos.serial_of(name))

    def image(self, name):
        """The photo, upright, as JPEG bytes (the last few are kept)."""
        with self.lock:
            if name in self.cache:
                return self.cache[name]
        image = cv2.imencode(".jpg", load(self.paths[name]), [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()
        with self.lock:
            self.cache[name] = image
            while len(self.cache) > 8:
                self.cache.pop(next(iter(self.cache)))
        return image

    def item(self, name):
        """Where a photo starts: the recess's corners in the photo's pixels (None: in the middle of the photo), the
        label's corners in mm, if placed, and notes on its verdicts."""
        shell, fit = self.shell(name), self.fits[name]
        recess, label = corners_of(shell.recess), corners_of(shell.label)
        hand = [v for v in self.verdicts().get(name, []) if v["verdict"] == "great" and v.get("sha1") == fit["sha1"]]
        notes = []
        if hand:
            H, start = hand[-1]["mm_to_photo"], "the last fit placed by hand"
            label_mm = project(np.linalg.inv(H), project(hand[-1]["label_mm_to_photo"], label)).tolist() if "label_mm_to_photo" in hand[-1] else None
        elif "error" not in fit:
            H, start, label_mm = fit["mm_to_photo"], "fit-cartridge's fit", None
        elif "crop" in fit:
            # The body in the middle of the box fit-cartridge cropped to (the body and 12 % around it).
            x0, y0, x1, y1 = fit["crop"]
            s = min((x1 - x0) / shell.body[0], (y1 - y0) / shell.body[1]) / 1.24
            cx, cy = (x0 + x1) / 2 - s * shell.body[0] / 2, (y0 + y1) / 2 - s * shell.body[1] / 2
            H, start, label_mm = [[s, 0, cx], [0, s, cy], [0, 0, 1]], "the box fit-cartridge cropped to", None
            notes.append(f'not fitted: {fit["error"]}')
        else:
            H, start, label_mm = None, "the middle of the photo", None
            notes.append(f'not fitted: {fit["error"]}')
        notes.insert(0, f"started from {start}")
        for v in self.verdicts().get(name, []):
            if "error" not in fit and same_fit(v, fit):
                notes.append(f'fit-cartridge\'s fit judged {shown(v["verdict"])}')
        notes.append(f'{len(hand)} placed by hand before' if hand else "not placed by hand before")
        return {"name": name, "path": self.paths[name], "shell": shell.name, "recess": None if H is None else project(H, recess).tolist(),
                "label": label_mm, "notes": notes}

    def save(self, name, recess, label_mm):
        """Saves a placement as a great fit: the recess's corners in the photo's pixels, and the label's in mm (or None)."""
        shell = self.shell(name)
        H = homography(corners_of(shell.recess), recess)
        verdict = {"verdict": "great", "mm_to_photo": H.tolist(), "sha1": self.sha1s[name]}
        if label_mm is not None:
            verdict["label_mm_to_photo"] = homography(corners_of(shell.label), project(H, label_mm)).tolist()
        verdicts = self.verdicts()
        kept = [v for v in verdicts.get(name, []) if v != self.placed.get(name)]
        verdicts[name] = kept + [verdict]
        save_verdicts(verdicts)
        self.placed[name] = verdict

    def summary(self):
        """Per group, how many photos it has and how many were placed by hand (ever, not only in this run)."""
        verdicts = self.verdicts()
        hand = lambda n: any(v["verdict"] == "great" and v.get("sha1") == self.sha1s[n] for v in verdicts.get(n, []))
        return {group: {"photos": len(names), "placed": sum(map(hand, names))} for group, names in self.groups.items()}

    def group(self, group):
        verdicts = self.verdicts()
        return [{"name": n, "placed": any(v["verdict"] == "great" and v.get("sha1") == self.sha1s[n] for v in verdicts.get(n, []))} for n in self.groups[group]]


PAGE = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fit by hand</title>
<style>
body{font:14px system-ui;margin:0;background:#f4f4f4;color:#222;display:flex;height:100vh}
#side{width:260px;flex:none;display:flex;flex-direction:column;gap:8px;background:#fff;padding:8px;box-sizing:border-box;border-right:1px solid #ddd}
#loupe{display:block;width:240px;height:240px;background:#000}
#list{flex:1;overflow:auto;min-height:0;font-variant-numeric:tabular-nums}
#list a{display:block;color:#222;text-decoration:none;padding:2px 4px;border-radius:0.3em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#list a.cur{background:#dde}#list a::before{content:"\\2713  ";color:transparent}#list a.placed::before{color:#070}
#main{flex:1;display:flex;flex-direction:column;min-width:0}
header{background:#fff;padding:8px 16px;border-bottom:1px solid #ddd;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
#position{display:inline-block;width:12ch;text-align:center;font-variant-numeric:tabular-nums}
h2{font-size:14px;margin:0;width:22ch;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#notes,#help{flex-basis:100%;margin:0;font-size:12px;color:#555}
#stage{flex:1;position:relative;overflow:hidden;background:#333}
canvas#c{position:absolute;left:0;top:0}
button{font:inherit;padding:4px 10px;border:none;border-radius:0.3em}
button#save{background:#070;color:#fff}
#status{display:inline-block;width:10ch;color:#070}
</style>
<div id="side"><select id="group"></select><canvas id="loupe" width="240" height="240"></canvas><div id="list"></div></div>
<div id="main"><header>
<button id="prev">← prev</button><span id="position"></span><button id="next">next →</button>
<h2 id="title"></h2><button id="reset">Reset (R)</button><label><input type="checkbox" id="labelplaced"> Label placed (L)</label>
<button id="save">Save as great (S)</button><span id="status"></span>
<p id="notes"></p>
<p id="help">Drag the green corners (squares) onto the recess's; the dots slide a side. Tick Label placed to show the label (cyan): its corners turn it, the dots move a side, the cross moves it. Tab: next handle; arrow keys: nudge 1 px (Shift: 10 px); wheel: zoom; drag elsewhere: pan; S: save and go to the next photo.</p>
</header><div id="stage"><canvas id="c"></canvas></div></div>
<script>
const $ = id => document.getElementById(id);
const c = $("c"), ctx = c.getContext("2d"), lctx = $("loupe").getContext("2d");
let models, groups, group = "almost", list = [], i = 0, item = null, img = new Image();
let corners = null, rect = null, sel = 0, drag = -1, grab = null, startCorners = null, startRect = null, pan = null;
let scale = 1, ox = 0, oy = 0;
const apply = (H, [x, y]) => { const w = H[2][0] * x + H[2][1] * y + H[2][2]; return [(H[0][0] * x + H[0][1] * y + H[0][2]) / w, (H[1][0] * x + H[1][1] * y + H[1][2]) / w]; };
// The homography taking four points to four others.
function homography(src, dst) {
  const A = [], b = [];
  for (let k = 0; k < 4; k++) {
    const [x, y] = src[k], [u, v] = dst[k];
    A.push([x, y, 1, 0, 0, 0, -u * x, -u * y]); b.push(u);
    A.push([0, 0, 0, x, y, 1, -v * x, -v * y]); b.push(v);
  }
  for (let col = 0; col < 8; col++) {
    let p = col;
    for (let r = col + 1; r < 8; r++) if (Math.abs(A[r][col]) > Math.abs(A[p][col])) p = r;
    [A[col], A[p]] = [A[p], A[col]]; [b[col], b[p]] = [b[p], b[col]];
    for (let r = 0; r < 8; r++) if (r !== col) { const f = A[r][col] / A[col][col]; for (let k = col; k < 8; k++) A[r][k] -= f * A[col][k]; b[r] -= f * b[col]; }
  }
  const h = b.map((v, k) => v / A[k][k]);
  return [[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1]];
}
const model = () => models[item.shell];
const toPhoto = () => homography(model().recess, corners), toMm = () => homography(corners, model().recess);
// The label: a rectangle in the recess's mm, {c: center, a: turn (radians), w, h}.
const LOCAL = [[-.5, -.5], [.5, -.5], [.5, .5], [-.5, .5]], NORMALS = [[0, -1], [1, 0], [0, 1], [-1, 0]];
const rot = (a, [x, y]) => [Math.cos(a) * x - Math.sin(a) * y, Math.sin(a) * x + Math.cos(a) * y];
const mid = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
const copy = r => ({c: r.c.slice(), a: r.a, w: r.w, h: r.h});
function rectCorners(r) { return LOCAL.map(([u, v]) => { const d = rot(r.a, [u * r.w, v * r.h]); return [r.c[0] + d[0], r.c[1] + d[1]]; }); }
function rectFrom(q) {
  const t = [q[1][0] - q[0][0] + q[2][0] - q[3][0], q[1][1] - q[0][1] + q[2][1] - q[3][1]], l = [q[3][0] - q[0][0] + q[2][0] - q[1][0], q[3][1] - q[0][1] + q[2][1] - q[1][1]];
  return {c: q.reduce((s, p) => [s[0] + p[0] / 4, s[1] + p[1] / 4], [0, 0]), a: Math.atan2(t[1], t[0]), w: Math.hypot(...t) / 2, h: Math.hypot(...l) / 2};
}
const placed = () => $("labelplaced").checked;
// Handles, in the photo's pixels: 0-3 the recess's corners, 4-7 the middle of its sides (top, right, bottom, left),
// and with the label placed, 8-11 the label's corners, 12-15 the middle of its sides, 16 its center.
function handles() {
  const H = toPhoto(), R = model().recess, L = rectCorners(rect);
  const recess = corners.concat([0, 1, 2, 3].map(k => apply(H, mid(R[k], R[(k + 1) % 4]))));
  return placed() ? recess.concat(L.map(q => apply(H, q)), [0, 1, 2, 3].map(k => apply(H, mid(L[k], L[(k + 1) % 4]))), [apply(H, rect.c)]) : recess;
}
// Ticks or unticks Label placed; unticked, the label's handles are gone.
function setPlaced(on) {
  $("labelplaced").checked = on;
  if (!on && sel >= 8) sel = 0;
  draw();
}
// Slides recess side k, from where it was at the start of the drag, to pass through the photo's point q.
function slide(k, q, start) {
  const R = model().recess, Hs = homography(R, start), m = apply(homography(start, R), q), n = NORMALS[k], s = mid(R[k], R[(k + 1) % 4]);
  const d = (m[0] - s[0]) * n[0] + (m[1] - s[1]) * n[1];
  corners = start.map(p => p.slice());
  for (const j of [k, (k + 1) % 4]) corners[j] = apply(Hs, [R[j][0] + d * n[0], R[j][1] + d * n[1]]);
}
// Moves the label by handle h (0-8 from its first) to the photo's point q, from where it was at the start.
function moveLabel(h, q, s) {
  const m = apply(toMm(), q);
  rect = copy(s);
  if (h < 4) {
    const corner = rectCorners(s)[h];
    rect.a = s.a + Math.atan2(m[1] - s.c[1], m[0] - s.c[0]) - Math.atan2(corner[1] - s.c[1], corner[0] - s.c[0]);
  } else if (h < 8) {
    const k = h - 4, n = rot(s.a, NORMALS[k]), L = rectCorners(s), e = mid(L[k], L[(k + 1) % 4]);
    const d = (m[0] - e[0]) * n[0] + (m[1] - e[1]) * n[1];
    if (k % 2) rect.w = s.w + d; else rect.h = s.h + d;
    rect.c = [s.c[0] + n[0] * d / 2, s.c[1] + n[1] * d / 2];
  } else rect.c = m;
}
function move(h, q, startC, startR) {
  if (h < 4) corners[h] = q;
  else if (h < 8) slide(h - 4, q, startC);
  else moveLabel(h - 8, q, startR);
  $("status").textContent = "";
}
async function start() {
  [models, groups] = await Promise.all([(await fetch("/models")).json(), (await fetch("/groups")).json()]);
  const [g, name] = decodeURIComponent(location.hash.slice(1)).split("/");
  if (g in groups) group = g;
  showGroups();
  await showGroup(name);
}
function showGroups() {
  $("group").innerHTML = Object.entries(groups).map(([g, n]) => `<option value="${g}">${g}: ${n.placed} of ${n.photos} placed</option>`).join("");
  $("group").value = group;
}
async function showGroup(name) {
  list = await (await fetch("/group/" + encodeURIComponent(group))).json();
  i = Math.max(0, list.findIndex(p => p.name === name));
  showList();
  if (list.length) show(); else { $("title").textContent = "none"; ctx.clearRect(0, 0, c.width, c.height); }
}
function showList() {
  $("list").innerHTML = list.map((p, k) => `<a href="#" data-k="${k}" class="${k === i ? "cur" : ""} ${p.placed ? "placed" : ""}">${p.name}</a>`).join("");
  $("list").querySelector(".cur")?.scrollIntoView({block: "nearest"});
}
$("list").onclick = e => { const a = e.target.closest("a"); if (a) { e.preventDefault(); go(+a.dataset.k); } };
$("group").onchange = e => { group = e.target.value; showGroup(); };
async function show() {
  const name = list[i].name;
  history.replaceState(null, "", "#" + encodeURIComponent(group) + "/" + encodeURIComponent(name));
  $("position").textContent = `${i + 1} / ${list.length}`;
  $("title").textContent = name;
  $("status").textContent = "";
  showList();
  item = await (await fetch("/item/" + encodeURIComponent(name))).json();
  $("title").title = item.path;
  $("notes").textContent = item.notes.join(" · ");
  const next = new Image();
  next.onload = () => { if (item.name !== name) return; img = next; frame(); reset(); };
  next.src = "/image/" + encodeURIComponent(name);
}
function reset() {
  const W = img.width, H = img.height, R = model().recess;
  corners = item.recess ? item.recess.map(q => q.slice()) : R.map(([x, y]) => [W / 2 + (x - 28.5) * W / 120, H / 2 + (y - 37.5) * W / 120]);
  rect = rectFrom(item.label || model().label);
  $("labelplaced").checked = !!item.label;
  sel = 0;
  draw();
}
// The photo fills the stage; the wheel zooms about the pointer.
function frame() {
  const m = $("stage");
  c.width = m.clientWidth; c.height = m.clientHeight;
  scale = Math.min(c.width / img.width, c.height / img.height) * 0.95;
  ox = (c.width - img.width * scale) / 2; oy = (c.height - img.height * scale) / 2;
}
const toScreen = q => [ox + q[0] * scale, oy + q[1] * scale], toImage = (x, y) => [(x - ox) / scale, (y - oy) / scale];
// The model's lines and, if placed, the label in the photo's pixels: [points, color, dashed, closed].
function shapes() {
  const H = toPhoto(), lines = model().lines.map(([pts, col, dash, closed]) => [pts.map(q => apply(H, q)), col, dash, closed]);
  return placed() ? lines.concat([[rectCorners(rect).map(q => apply(H, q)), "#3cf", false, true]]) : lines;
}
function stroke(g, pts, closed, at) {
  g.beginPath();
  pts.forEach((q, k) => { const [x, y] = at(q); k ? g.lineTo(x, y) : g.moveTo(x, y); });
  if (closed) g.closePath();
  g.stroke();
}
function draw() {
  ctx.clearRect(0, 0, c.width, c.height);
  ctx.drawImage(img, ox, oy, img.width * scale, img.height * scale);
  ctx.lineWidth = 1;
  for (const [pts, col, dash, closed] of shapes()) { ctx.strokeStyle = col; ctx.setLineDash(dash ? [5, 4] : []); stroke(ctx, pts, closed, toScreen); }
  ctx.setLineDash([]);
  handles().forEach((q, k) => {
    const [x, y] = toScreen(q);
    ctx.fillStyle = ctx.strokeStyle = k === sel ? "#ff0" : k >= 8 ? "#3cf" : "#3d3";
    if (k === 16) { ctx.beginPath(); ctx.moveTo(x - 8, y); ctx.lineTo(x + 8, y); ctx.moveTo(x, y - 8); ctx.lineTo(x, y + 8); ctx.stroke(); }
    else if (k % 8 < 4) ctx.fillRect(x - 4, y - 4, 8, 8);
    else { ctx.beginPath(); ctx.arc(x, y, 4, 0, 7); ctx.fill(); }
  });
  loupe(handles()[sel]);
}
// The magnifier: 6 x 6 mm around the handle, at the photo's scale along the recess's top side.
function loupe(q) {
  const R = model().recess, pxPerMm = Math.hypot(corners[1][0] - corners[0][0], corners[1][1] - corners[0][1]) / (R[1][0] - R[0][0]);
  const r = 3 * pxPerMm, z = 120 / r, at = p => [120 + (p[0] - q[0]) * z, 120 + (p[1] - q[1]) * z];
  lctx.imageSmoothingEnabled = false;
  lctx.fillStyle = "#000"; lctx.fillRect(0, 0, 240, 240);
  lctx.drawImage(img, q[0] - r, q[1] - r, 2 * r, 2 * r, 0, 0, 240, 240);
  for (const [pts, col, dash, closed] of shapes()) { lctx.strokeStyle = col; lctx.setLineDash(dash ? [5, 4] : []); stroke(lctx, pts, closed, at); }
  lctx.setLineDash([]);
  lctx.strokeStyle = "#ff0"; lctx.strokeRect(117, 117, 6, 6);
}
c.onmousedown = e => {
  if (!corners) return;
  let best = -1, bd = 12 ** 2;
  handles().forEach((q, k) => { const [sx, sy] = toScreen(q), d = (sx - e.offsetX) ** 2 + (sy - e.offsetY) ** 2; if (d < bd) { bd = d; best = k; } });
  if (best < 0) { pan = [e.offsetX - ox, e.offsetY - oy]; return; }
  drag = sel = best;
  startCorners = corners.map(q => q.slice()); startRect = copy(rect);
  const h = handles()[best], m = toImage(e.offsetX, e.offsetY);
  grab = [h[0] - m[0], h[1] - m[1]];
  draw();
};
c.onmousemove = e => {
  if (pan) { ox = e.offsetX - pan[0]; oy = e.offsetY - pan[1]; return draw(); }
  if (drag < 0) return;
  const m = toImage(e.offsetX, e.offsetY);
  move(drag, [m[0] + grab[0], m[1] + grab[1]], startCorners, startRect);
  draw();
};
window.onmouseup = () => { drag = -1; pan = null; };
c.onwheel = e => {
  e.preventDefault();
  const f = Math.exp(-e.deltaY / 500), [x, y] = [e.offsetX, e.offsetY];
  ox = x - (x - ox) * f; oy = y - (y - oy) * f; scale *= f;
  draw();
};
async function save() {
  if (!corners) return;
  const body = {name: item.name, recess: corners, label: placed() ? rectCorners(rect) : null};
  const response = await fetch("/save", {method: "POST", body: JSON.stringify(body)});
  if (!response.ok) return alert("Not saved: " + response.status);
  groups = await response.json();
  showGroups();
  list[i].placed = true;
  if (i + 1 < list.length) go(i + 1); else { showList(); $("status").textContent = "saved"; }
}
const go = k => { if (k >= 0 && k < list.length) { i = k; show(); } };
$("prev").onclick = () => go(i - 1);
$("next").onclick = () => go(i + 1);
$("reset").onclick = () => reset();
$("save").onclick = save;
$("labelplaced").onchange = e => setPlaced(e.target.checked);
document.onkeydown = e => {
  if (e.target.tagName === "SELECT" || !corners) return;
  const step = e.shiftKey ? 10 : 1, d = {ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step]}[e.key];
  if (d) {
    const h = handles()[sel];
    move(sel, [h[0] + d[0], h[1] + d[1]], corners.map(q => q.slice()), copy(rect));
    draw(); e.preventDefault();
  } else if (e.key === "Tab") {
    // Round each rectangle: a corner, the middle of the side after it, the next corner...; the label's cross last.
    const order = [0, 4, 1, 5, 2, 6, 3, 7, 8, 12, 9, 13, 10, 14, 11, 15, 16].slice(0, handles().length), n = order.length;
    sel = order[(order.indexOf(sel) + (e.shiftKey ? n - 1 : 1)) % n]; draw(); e.preventDefault();
  }
  else if (e.key === "s" || e.key === "S") save();
  else if (e.key === "r" || e.key === "R") reset();
  else if (e.key === "l" || e.key === "L") setPlaced(!placed());
};
window.onresize = () => { if (img.width) { frame(); draw(); } };
start();
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
            self.send(PAGE.encode(), "text/html; charset=utf-8")
        elif parts == ["models"]:
            self.send({name: model(shell) for name, shell in SHELLS.items()})
        elif parts == ["groups"]:
            self.send(hand.summary())
        elif len(parts) == 2 and parts[0] == "group" and parts[1] in hand.groups:
            self.send(hand.group(parts[1]))
        elif len(parts) == 2 and parts[0] == "item" and parts[1] in hand.fits:
            self.send(hand.item(parts[1]))
        elif len(parts) == 2 and parts[0] == "image" and parts[1] in hand.fits:
            self.send(hand.image(parts[1]), "image/jpeg")
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/save":
            return self.send_error(404)
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if data["name"] not in hand.fits or np.shape(data["recess"]) != (4, 2) or data["label"] is not None and np.shape(data["label"]) != (4, 2):
            return self.send_error(400)
        if review_running():
            return self.send_error(409, "make review-fits is running")
        hand.save(data["name"], data["recess"], data["label"])
        self.send(hand.summary())

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    if review_running():
        sys.exit("make review-fits is running: it rewrites reviews/fits.json too; stop it first")
    hand = Hand()
    print(f"{len(hand.fits)} photos, {len(hand.groups['almost'])} with their fit judged almost; place them at http://localhost:{PORT}/ (ctrl-C to stop)")
    ThreadingHTTPServer(("localhost", PORT), Handler).serve_forever()
