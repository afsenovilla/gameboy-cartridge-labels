# solve: every label photo's homography from its photo into ink coordinates (mm on the label's print, one coordinate
# system per shape, anchored by each linked set's median cut), into <generated>/solve/solve.json:
#   {"label_photos": {key: {"photo_to_ink" (3 x 3), "cut_to_photo" (3 x 3: the sticker's cut outline, the canonical
#                            label size, -> the photo), "offset" (dx, dy mm, turn degrees: the sticker's cut -> ink),
#                            "start" (how the outline was started), "support" (the share of each side, top, right,
#                            bottom, left, along LSD segments), "fallback" (null, or why the pose is weak),
#                            "residual_mm" (matched points' disagreement in ink coordinates, median), "links" (used)},
#                     ...},
#    "sets": [{"keys", "links used", "links dropped", "residual_mm"}],
#    "unsolved": {key: why}}
# Two stages (label-detection.md):
#   1. Each label photo on its own: the sticker's cut outline, a perspective view of a rectangle of its shape's
#      canonical label size, fitted to the photo's LSD segments (edges). Starts, best first: the label placed by a
#      fixed-place logo (find); a fitted label photo's outline carried through a match (one of the same release first,
#      then the same game, then any: another layout can be off); a rectangle around the evidence, turned by its
#      serial's reading direction and scaled by its height. Each side snaps to the line best supported by segments
#      near it (parallel within ANGLE, within a window shrinking from WINDOWS), the corners from the four lines; a
#      start is dropped when less than MIN_SUPPORT of the outline lies along segments, and the next tried.
#   2. Each linked set: matched points (match's inliers, assigned to label photo pairs) map into each sticker's
#      frame; a link's shift and turn between the two frames counts if within MAX_SHIFT and MAX_TURN (else the two are
#      likely other layouts sharing a template); one least-squares fit gives every label photo a shift and turn, the
#      set's median taken as none (the median cut anchors ink coordinates).
# The recess (the placement on the plastic) isn't used yet.
# Done again when solve.json is older than this file or its inputs.
# Usage: solve.py [--sample]
import argparse, html, json, os, sys
import cv2, numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photos, steps, match, shapes, find

ANGLE = 6.0           # degrees: a segment counts for a side if this parallel
WINDOWS = (4.0, 1.5, 0.6)  # mm: how far a side may move, per round
BIN = 0.2             # mm: the offsets of segments from a side are histogrammed in these
MIN_SUPPORT = 0.45    # the least mean share of the four sides along segments for a fit to count
MAX_SHIFT = 4.0       # mm: a link's shift between two stickers' frames that still counts
MAX_TURN = 4.0        # degrees
MIN_LINK_POINTS = 8


def corners_mm(shape):
    w, h = shapes.LABEL_MM[shape]
    return np.float64([[0, 0], [w, 0], [w, h], [0, h]])


def project(H, pts):
    return cv2.perspectiveTransform(np.float64(pts).reshape(-1, 1, 2), np.float64(H)).reshape(-1, 2)


def line_through(p, q):
    """(unit normal n, c) with n . x = c for points x on the line through p and q."""
    d = np.subtract(q, p) / np.linalg.norm(np.subtract(q, p))
    n = np.array([-d[1], d[0]])
    return n, float(n @ p)


def intersect(l1, l2):
    (n1, c1), (n2, c2) = l1, l2
    A = np.array([n1, n2])
    if abs(np.linalg.det(A)) < 1e-9:
        return None
    return np.linalg.solve(A, [c1, c2])


def snap_side(p, q, segs, window_px, bin_px):
    """The line best supported by segments near the side p -> q (parallel within ANGLE, their midpoints within
    window_px of it, overlapping it), and the share of the side they cover; the side itself if none."""
    n, c = line_through(p, q)
    d = np.subtract(q, p); length = np.linalg.norm(d); u = d / length
    sd = segs[:, 2:] - segs[:, :2]
    sl = np.linalg.norm(sd, axis=1)
    su = sd / np.maximum(sl[:, None], 1e-9)
    mid = (segs[:, :2] + segs[:, 2:]) / 2
    off = mid @ n - c
    along = (mid - p) @ u
    ok = (np.abs(su @ u) > np.cos(np.radians(ANGLE))) & (np.abs(off) < window_px) & (along > -0.1 * length) & (along < 1.1 * length)
    if not ok.any():
        return (n, c), 0.0
    bins = np.round(off[ok] / bin_px).astype(int)
    weight = {}
    for b, w in zip(bins, sl[ok]):
        for nb in (b - 1, b, b + 1):
            weight[nb] = weight.get(nb, 0) + w * (1.0 if nb == b else 0.5)
    best = max(weight, key=weight.get)
    near = ok.copy()
    near[ok] = np.abs(bins - best) <= 1
    pts = np.vstack([segs[near, :2], segs[near, 2:]])
    w = np.repeat(sl[near], 2)
    centre = (pts * w[:, None]).sum(0) / w.sum()
    cov = ((pts - centre) * w[:, None]).T @ (pts - centre)
    direction = np.linalg.eigh(cov)[1][:, -1]
    if direction @ u < 0:
        direction = -direction
    n2 = np.array([-direction[1], direction[0]])
    # the share of the side covered: its points within a bin of a supporting segment
    ts = np.linspace(0, 1, 40)
    side_pts = np.asarray(p)[None] + ts[:, None] * d[None]
    covered = np.zeros(len(ts), bool)
    for s0, s1 in zip(segs[near, :2], segs[near, 2:]):
        v = s1 - s0
        t = np.clip(((side_pts - s0) @ v) / max(v @ v, 1e-9), 0, 1)
        covered |= np.linalg.norm(side_pts - (s0 + t[:, None] * v), axis=1) < 2 * bin_px + window_px * 0.1
    return (n2, float(n2 @ centre)), float(covered.mean())


def fit_outline(H0, shape, segs):
    """The cut outline from a start (H0: label mm -> photo), snapped to the segments round by round: (H, support per
    side) or (None, support) if the result isn't plausible."""
    mm = corners_mm(shape)
    H = np.float64(H0)
    support = [0.0] * 4
    for window_mm in WINDOWS:
        quad = project(H, mm)
        px_per_mm = np.sqrt(abs(cv2.contourArea(quad.astype(np.float32))) / (shapes.LABEL_MM[shape][0] * shapes.LABEL_MM[shape][1]))
        lines, support = [], []
        for k in range(4):
            l, s = snap_side(quad[k], quad[(k + 1) % 4], segs, window_mm * px_per_mm, BIN * px_per_mm)
            lines.append(l); support.append(s)
        new = [intersect(lines[k - 1], lines[k]) for k in range(4)]  # corner k between side k-1 and side k
        if any(c is None for c in new):
            return None, support
        new = np.array(new)
        if not plausible_quad(new, quad):
            return None, support
        H = cv2.getPerspectiveTransform(mm.astype(np.float32), new.astype(np.float32)).astype(np.float64)
    return H, support


def plausible_quad(new, old):
    """Convex, not crossed, and its sides within 25 % of the start's (a snap to a far line distorts it)."""
    if not cv2.isContourConvex(new.astype(np.float32)):
        return False
    side = lambda q: np.linalg.norm(np.roll(q, -1, 0) - q, axis=1)
    return bool(np.all(np.abs(np.log(side(new) / np.maximum(side(old), 1e-9))) < np.log(1.25)))


def similarity_to_H(centre, angle_deg, px_per_mm, shape):
    """label mm -> photo: the label's centre at centre, turned by angle, at px_per_mm."""
    w, h = shapes.LABEL_MM[shape]
    a = np.radians(angle_deg)
    R = px_per_mm * np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
    t = np.asarray(centre) - R @ [w / 2, h / 2]
    return np.vstack([np.hstack([R, t[:, None]]), [0, 0, 1]])


def evidence_start(lp, shape):
    """A rough start from a label photo's evidence: its outline's centre, its serial's reading direction (or the
    first string's, or level), scaled by the line's height (the serial's line about 2.2 mm)."""
    if not lp["strings"]:
        return None
    c = np.float64(lp["strings"][0]["corners"])
    d = c[1] - c[0]
    height = (np.linalg.norm(c[3] - c[0]) + np.linalg.norm(c[2] - c[1])) / 2
    centre = np.float64(lp["outline"]).mean(0) if len(lp["outline"]) >= 3 else c.mean(0)
    return similarity_to_H(centre, np.degrees(np.arctan2(d[1], d[0])), height / 2.2, shape)


def release_of(lp):
    return next((t["release"] for t in lp["strings"] if t.get("release")), None)


def game_of(lp):
    s = next((t["serial"] for t in lp["strings"] if t["kind"] != "unknown"), None)
    return s.split("-")[1][:3] if s else None


def link_points(lps, matches):
    """(key a, key b) -> (points in photo a, points in photo b): match inliers lying in both label photos' circles."""
    by_photo = {}
    for lp in lps:
        by_photo.setdefault(lp["photo"], []).append(lp)
    out = {}
    for a, b, H, inl in matches:
        for la in by_photo.get(a, []):
            ina = np.hypot(*(inl[:, :2] - la["centre"]).T) < la["radius"]
            for lb in by_photo.get(b, []):
                ok = ina & (np.hypot(*(inl[:, 2:] - lb["centre"]).T) < lb["radius"])
                if ok.sum() >= MIN_LINK_POINTS:
                    k = (la["key"], lb["key"])
                    pa, pb = out.get(k, (np.zeros((0, 2)), np.zeros((0, 2))))
                    out[k] = (np.vstack([pa, inl[ok, :2]]), np.vstack([pb, inl[ok, 2:]]))
    return out


def photo_homography(pa, pb):
    H, mask = cv2.findHomography(np.float32(pa), np.float32(pb), cv2.USAC_MAGSAC, 3.0)
    return H


def rigid_fit(a, b):
    """b ~ R(theta) a + t, least squares: (theta degrees, t)."""
    ca, cb = a.mean(0), b.mean(0)
    A, B = a - ca, b - cb
    theta = np.arctan2((A[:, 0] * B[:, 1] - A[:, 1] * B[:, 0]).sum(), (A * B).sum())
    R = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    return np.degrees(theta), cb - R @ ca


def stage1(lps, edges_dir, pairs):
    """The cut outlines: key -> {"cut_to_photo", "support", "start"}; key -> why for those that failed."""
    by_key = {lp["key"]: lp for lp in lps}
    segs = {}
    get_segs = lambda s: segs.setdefault(s, np.load(os.path.join(edges_dir, s + ".npz"))["segments"].astype(np.float64))
    fits, failed = {}, {}

    def attempt(lp, H0, start):
        if H0 is None:
            return False
        H, support = fit_outline(H0, lp["shape"], get_segs(lp["photo"]))
        if H is not None and np.mean(support) >= MIN_SUPPORT:
            fits[lp["key"]] = {"cut_to_photo": H, "support": [round(s, 2) for s in support], "start": start}
            return True
        return False

    todo = [lp for lp in lps if lp["shape"]]
    for lp in lps:
        if not lp["shape"]:
            failed[lp["key"]] = "no shape"
    # placed by a logo
    for lp in todo:
        if lp.get("placed_by") and len(lp["outline"]) == 4:
            mm = corners_mm(lp["shape"])
            attempt(lp, cv2.getPerspectiveTransform(mm.astype(np.float32), np.float32(lp["outline"])).astype(np.float64), "placed by " + lp["placed_by"])
    # carried through matches from fitted ones, best related first, until nothing more is fitted
    neighbours = {}
    for (a, b), (pa, pb) in pairs.items():
        neighbours.setdefault(a, []).append((b, pb, pa))  # (other key, points there, points here)
        neighbours.setdefault(b, []).append((a, pa, pb))
    changed = True
    while changed:
        changed = False
        for lp in todo:
            if lp["key"] in fits:
                continue
            cands = [(o, po, ph) for o, po, ph in neighbours.get(lp["key"], []) if o in fits and by_key[o]["shape"] == lp["shape"]]
            rank = lambda c: (release_of(by_key[c[0]]) != release_of(lp) or release_of(lp) is None,
                              game_of(by_key[c[0]]) != game_of(lp) or game_of(lp) is None, -len(c[1]))
            for o, po, ph in sorted(cands, key=rank):
                M = photo_homography(po, ph)  # other photo -> this photo
                if M is not None and attempt(lp, M @ fits[o]["cut_to_photo"], "carried from " + o):
                    changed = True
                    break
    # from the evidence
    for lp in todo:
        if lp["key"] not in fits and not attempt(lp, evidence_start(lp, lp["shape"]), "evidence"):
            failed[lp["key"]] = "no outline found"
    return fits, failed


def stage2(lps, fits, pairs, sets):
    """Per linked set, every fitted label photo's shift and turn (sticker's cut -> ink), the set's median none."""
    offsets, set_info, residual = {}, [], {}
    for keys in sets:
        keys = [k for k in keys if k in fits]
        if not keys:
            continue
        idx = {k: i for i, k in enumerate(keys)}
        links, dropped = [], 0
        for (a, b), (pa, pb) in pairs.items():
            if a not in idx or b not in idx:
                continue
            ma = project(np.linalg.inv(fits[a]["cut_to_photo"]), pa)
            mb = project(np.linalg.inv(fits[b]["cut_to_photo"]), pb)
            theta, t = rigid_fit(mb, ma)  # b's frame -> a's
            if abs(theta) <= MAX_TURN and np.linalg.norm(t) <= MAX_SHIFT:
                links.append((idx[a], idx[b], ma, mb))
            else:
                dropped += 1
        # unknowns per label photo: turn (radians, small), dx, dy; ink = R_i m + t_i; matched points agree in ink
        n = len(keys)
        rows, rhs = [], []
        for i, j, ma, mb in links:
            w = 1 / np.sqrt(len(ma))  # each link counts about equally, however many points
            for (xa, ya), (xb, yb) in zip(ma, mb):
                # R_i a + t_i - R_j b - t_j = 0, small angles: x: -ya th_i + dx_i + yb th_j - dx_j = xb - xa
                r = np.zeros(3 * n); r[3 * i] = -ya; r[3 * i + 1] = 1; r[3 * j] = yb; r[3 * j + 1] = -1
                rows.append(w * r); rhs.append(w * (xb - xa))
                r = np.zeros(3 * n); r[3 * i] = xa; r[3 * i + 2] = 1; r[3 * j] = -xb; r[3 * j + 2] = -1
                rows.append(w * r); rhs.append(w * (yb - ya))
        # a weak pull of every offset towards none keeps label photos without links (and the gauge) in place
        for i in range(n):
            for k in range(3):
                r = np.zeros(3 * n); r[3 * i + k] = 0.01
                rows.append(r); rhs.append(0.0)
        x = np.linalg.lstsq(np.array(rows), np.array(rhs), rcond=None)[0].reshape(n, 3)
        x -= np.median(x, 0)  # the set's median cut is the anchor
        for k, i in idx.items():
            offsets[k] = x[i]
        res = {k: [] for k in keys}
        for i, j, ma, mb in links:
            ink_a = apply_offset(x[i], ma); ink_b = apply_offset(x[j], mb)
            d = np.linalg.norm(ink_a - ink_b, axis=1)
            res[keys[i]].append(d); res[keys[j]].append(d)
        for k in keys:
            residual[k] = float(np.median(np.concatenate(res[k]))) if res[k] else None
        set_info.append({"keys": keys, "links used": len(links), "links dropped": dropped,
                         "residual_mm": float(np.median(np.concatenate([np.linalg.norm(apply_offset(x[i], ma) - apply_offset(x[j], mb), axis=1) for i, j, ma, mb in links]))) if links else None})
    return offsets, set_info, residual


def apply_offset(o, pts):
    th, dx, dy = o
    R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    return pts @ R.T + [dx, dy]


def offset_matrix(o):
    th, dx, dy = o
    return np.array([[np.cos(th), -np.sin(th), dx], [np.sin(th), np.cos(th), dy], [0, 0, 1]])


def solve(found, matches, edges_dir):
    lps = found["label_photos"]
    for lp in lps:
        lp["centre"] = np.float64(lp["centre"])
    pairs = link_points(lps, matches)
    fits, failed = stage1(lps, edges_dir, pairs)
    offsets, set_info, residual = stage2(lps, fits, pairs, found["sets"])
    out = {}
    for lp in lps:
        k = lp["key"]
        if k not in fits:
            continue
        f = fits[k]
        o = offsets.get(k, np.zeros(3))
        photo_to_ink = offset_matrix(o) @ np.linalg.inv(f["cut_to_photo"])
        out[k] = {"photo": lp["photo"], "shape": lp["shape"], "photo_to_ink": (photo_to_ink / photo_to_ink[2, 2]).tolist(),
                  "cut_to_photo": (f["cut_to_photo"] / f["cut_to_photo"][2, 2]).tolist(),
                  "offset": [round(float(o[1]), 3), round(float(o[2]), 3), round(float(np.degrees(o[0])), 3)],
                  "start": f["start"], "support": f["support"],
                  "fallback": None if not f["start"].startswith("evidence") else "started from the evidence only",
                  "residual_mm": None if residual.get(k) is None else round(residual[k], 3)}
    return {"label_photos": out, "sets": set_info, "unsolved": failed}


def page(out_dir, chosen, result, sizes):
    lps = result["label_photos"]
    rel = os.path.relpath(".", out_dir)
    order = sorted(lps.items(), key=lambda kv: (-(kv[1]["residual_mm"] or 0), np.mean(kv[1]["support"])))

    def figure(key, r):
        s = r["photo"]; w, h = sizes[s]
        quad = project(r["cut_to_photo"], corners_mm(r["shape"]))
        pts = " ".join(f"{x:.0f},{y:.0f}" for x, y in quad)
        return (f'<figure><div class="ph"><img loading="lazy" src="{rel}/{chosen[s]}"><svg viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
                f'<polygon points="{pts}" fill="none" stroke="#0c0" stroke-width="{max(w, h) / 250:.1f}"/>'
                f'<circle cx="{quad[0][0]:.0f}" cy="{quad[0][1]:.0f}" r="{max(w, h) / 80:.0f}" fill="#f00"/></svg></div>'
                f'<figcaption><code>{html.escape(key[:14])}</code> {html.escape(r["start"][:30])}<br>support {r["support"]}, residual {r["residual_mm"]} mm, offset {r["offset"]}</figcaption></figure>')

    unsolved = "".join(f"<li><code>{html.escape(k[:16])}</code>: {html.escape(v)}</li>" for k, v in result["unsolved"].items())
    starts = {}
    for r in lps.values():
        kind = r["start"].split(" ")[0]
        starts[kind] = starts.get(kind, 0) + 1
    with open(os.path.join(out_dir, "index.html"), "w") as f:
        f.write(f"""<!doctype html><meta charset="utf-8"><title>solve</title>
<style>body{{font:14px system-ui;margin:16px}} figure{{display:inline-block;margin:6px;vertical-align:top;width:280px}}
.ph{{position:relative;display:inline-block}} .ph img{{max-width:280px;max-height:280px;display:block}} .ph svg{{position:absolute;inset:0;width:100%;height:100%}} figcaption{{font-size:11px}}</style>
<h1>solve</h1>
<p>{len(lps)} label photos solved (started: {", ".join(f"{k} {v}" for k, v in starts.items())}), {len(result["unsolved"])} not. Sets: {", ".join(f'{len(si["keys"])} label photos, {si["links used"]} links used, {si["links dropped"]} dropped, residual {si["residual_mm"] and round(si["residual_mm"], 2)} mm' for si in result["sets"][:5])}.</p>
<p>Green: the sticker's cut outline as fitted (canonical size); red dot: the label's top left. Worst first (residual, then support).</p>
<h2>Not solved ({len(result["unsolved"])})</h2><ul>{unsolved}</ul>
<h2>Solved</h2>{"".join(figure(k, r) for k, r in order)}
""")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true")
    args = ap.parse_args()
    chosen = photos.chosen(args.sample)
    gen = photos.generated(args.sample)
    out_dir = os.path.join(gen, "solve")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "solve.json")
    found_file = os.path.join(gen, "find", "label-photos.json")
    inputs = [found_file] + [os.path.join(gen, d, s + e) for s in chosen for d, e in (("edges", ".npz"), ("match", ".npz"))]
    missing = [p for p in inputs if not os.path.exists(p)]
    if missing:
        sys.exit(f"{len(missing)} inputs missing: run make find and make edges first")
    if steps.stale(out, __file__) or os.path.getmtime(out) < max(os.path.getmtime(p) for p in inputs):
        result = solve(json.load(open(found_file)), match.read_matches(os.path.join(gen, "match"), list(chosen)), os.path.join(gen, "edges"))
        steps.write_json(out, result)
    result = json.load(open(out))
    sizes = {s: json.load(open(os.path.join(gen, "read-text", s + ".json")))["size"] or [1, 1] for s in chosen}
    page(out_dir, chosen, result, sizes)
    print(f"{len(result['label_photos'])} solved, {len(result['unsolved'])} not; page: {os.path.join(out_dir, 'index.html')}")


if __name__ == "__main__":
    main()
