# solve: every label photo's homography from its photo into ink coordinates (mm on the label's print, one coordinate
# system per shape, anchored by each linked set's median cut), into <generated>/solve/solve.json:
#   {"label_photos": {key: {"photo_to_ink" (3 x 3), "cut_to_photo" (3 x 3: the sticker's cut outline, the canonical
#                            label size, -> the photo), "plastic_to_photo" (3 x 3), "placement" (dx, dy mm, turn
#                            degrees: the label's cut in the recess, from its nominal place), "offset" (dx, dy mm, turn
#                            degrees: the sticker's cut -> ink), "start" (how it was started), "support" (the share of
#                            the face, recess and label samples along segments), "fallback" (null, or why the pose is weak),
#                            "residual_mm" (matched points' disagreement in ink coordinates, median), "links" (used)},
#                     ...},
#    "sets": [{"keys", "links used", "links dropped", "residual_mm"}],
#    "unsolved": {key: why}}
# Two stages (label-detection.md):
#   1. Each label photo on its own: three nested rectangles of known sizes and places fitted together to the photo's
#      LSD segments (edges): the cartridge's outline, its recess and the label's cut (main's shape models,
#      src/shape-models.json). Unknowns: a homography from the plastic's mm to the photo, and the label's shift and turn
#      in the recess (the placement), softly held to about PLACEMENT_MM and PLACEMENT_DEG. Each model sample point is
#      matched to the nearest segment parallel to its edge (within ANGLE) inside a window shrinking through WINDOWS;
#      the residual is the perpendicular distance in mm, robust (soft L1, ROBUST_MM). Starts, in order: the label
#      placed by a fixed-place logo (find), kept if it passes; else main's outline quadrilaterals (src/outlines.py:
#      each four-sided outline in the photo taken for the label, the recess or the body), all of the photo's, the best
#      supported kept (on the evaluation set: 97 % under 5 mm from the hand fits, 100 % where main's fitter had
#      failed); else the pose search: poses of the model near the evidence scored against direction-binned distance
#      maps of the segments (edge_maps, search_poses), the best few fitted, its turn the direction most of the label's
#      text reads (along the label on 193 of 194 of the sample's). (Carrying a fitted pose through a match was tried:
#      37 % under 5 mm; main's text starts: 42 %; both dropped.) A fit is dropped when less than MIN_SUPPORT of the
#      model's sample points end up along segments
#      (within ON_MM), or less than MIN_FACE of the cartridge's outline (a label placed far off still finds label- and
#      recess-like lines: on the sample, 0.4 kept 69 of 70 fits within 2 mm of main's and dropped 87 of 109 farther off).
#   2. Each linked set: matched points (match's inliers, assigned to label photo pairs) map into each sticker's
#      frame; a link's shift and turn between the two frames counts if within MAX_SHIFT and MAX_TURN (else the two are
#      likely other layouts sharing a template); one least-squares fit gives every label photo a shift and turn, the
#      set's median taken as none (the median cut anchors ink coordinates).
# Done again when solve.json is older than this file or its inputs.
# Usage: solve.py [--sample]
import argparse, html, json, os, sys
import cv2, numpy as np
from scipy.optimize import least_squares

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photos, steps, match, shapes, find, outlines
from multiprocessing import Pool

ANGLE = 8.0           # degrees: a segment counts for a sample point if this parallel to its edge
WINDOWS = (6.0, 3.0, 1.5, 0.8)  # mm: how far a sample point looks for a segment, per round
ROBUST_MM = 0.3       # the soft L1 loss's scale
ON_MM = 0.5           # a sample point is along a segment within this, for the support
PLACEMENT_MM = 1.0    # the label's shift in the recess, softly held to about this
PLACEMENT_DEG = 2.0
MIN_SUPPORT = 0.4     # the least share of the model's samples along segments for a fit to count
MIN_FACE = 0.4        # and of the cartridge's outline: a label placed far off still finds label- and recess-like lines
MODELS = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "shape-models.json")))["shapes"]
MAX_SHIFT = 4.0       # mm: a link's shift between two stickers' frames that still counts
MAX_TURN = 4.0        # degrees
MIN_LINK_POINTS = 8


def corners_mm(shape):
    w, h = shapes.LABEL_MM[shape]
    return np.float64([[0, 0], [w, 0], [w, h], [0, h]])


def project(H, pts):
    return cv2.perspectiveTransform(np.float64(pts).reshape(-1, 1, 2), np.float64(H)).reshape(-1, 2)


def label_to_plastic(shape):
    """label mm (its top left at 0, 0) -> plastic mm, at its nominal place."""
    x0, y0 = MODELS[shape]["label"][:2]
    return np.array([[1.0, 0, x0], [0, 1, y0], [0, 0, 1]])


def placement_matrix(shape, dx, dy, turn_rad):
    """plastic mm -> plastic mm: the label turned about its nominal centre and shifted."""
    x0, y0, x1, y1 = MODELS[shape]["label"]
    c = np.array([(x0 + x1) / 2, (y0 + y1) / 2])
    R = np.array([[np.cos(turn_rad), -np.sin(turn_rad)], [np.sin(turn_rad), np.cos(turn_rad)]])
    t = c + [dx, dy] - R @ c
    return np.array([[R[0, 0], R[0, 1], t[0]], [R[1, 0], R[1, 1], t[1]], [0, 0, 1]])


def model_samples(shape):
    m = MODELS[shape]
    pts = np.float64([x["point"] for x in m["samples"]])
    nrm = np.float64([x["normal"] for x in m["samples"]])
    kinds = np.array([x["kind"] for x in m["samples"]])
    return pts, nrm, kinds


def homography_from(params, H0):
    """The plastic -> photo homography: the start H0 times a small change (in mm)."""
    a = params
    D = np.array([[1 + a[0], a[1], a[2]], [a[3], 1 + a[4], a[5]], [a[6] * 1e-3, a[7] * 1e-3, 1]])
    return H0 @ D


def projected(params, H0, shape, pts, nrm, kinds):
    """The model's sample points and their edge directions in the photo, the label's moved by the placement."""
    H = homography_from(params[:8], H0)
    P = placement_matrix(shape, params[8], params[9], np.radians(params[10]))
    is_label = kinds == "label"
    p = pts.copy()
    p[is_label] = project(P, pts[is_label])
    tangent = np.stack([-nrm[:, 1], nrm[:, 0]], 1)
    q = p + 0.5 * tangent
    pp, qq = project(H, p), project(H, q)
    d = qq - pp
    return pp, d / np.maximum(np.linalg.norm(d, axis=1)[:, None], 1e-12), H


def correspond(pp, dirs, segs, window_px):
    """For each projected sample point, the nearest segment parallel to its edge whose line passes within window_px:
    (index or -1)."""
    sd = segs[:, 2:] - segs[:, :2]
    sl = np.linalg.norm(sd, axis=1)
    su = sd / np.maximum(sl[:, None], 1e-12)
    sn = np.stack([-su[:, 1], su[:, 0]], 1)
    out = np.full(len(pp), -1)
    cos = np.cos(np.radians(ANGLE))
    for i, (p, d) in enumerate(zip(pp, dirs)):
        par = np.abs(su @ d) > cos
        if not par.any():
            continue
        rel = p - segs[par, :2]
        perp = np.abs((rel * sn[par]).sum(1))
        along = (rel * su[par]).sum(1)
        ok = (perp < window_px) & (along > -0.1 * sl[par] - window_px) & (along < 1.1 * sl[par] + window_px)
        if ok.any():
            idx = np.where(par)[0][ok]
            out[i] = idx[np.argmin(perp[ok])]
    return out


def fit_nested(H0_plastic, shape, segs):
    """The three rectangles fitted from a start (plastic mm -> photo): (plastic_to_photo, placement (dx, dy, turn
    degrees), support {kind: share}) or None."""
    pts, nrm, kinds = model_samples(shape)
    params = np.zeros(11)
    sd = segs[:, 2:] - segs[:, :2]
    su = sd / np.maximum(np.linalg.norm(sd, axis=1)[:, None], 1e-12)
    sn = np.stack([-su[:, 1], su[:, 0]], 1)
    for window in WINDOWS:
        pp, dirs, H = projected(params, H0_plastic, shape, pts, nrm, kinds)
        px_per_mm = local_scale(H, MODELS[shape]["label"])
        corr = correspond(pp, dirs, segs, window * px_per_mm)
        use = corr >= 0
        if use.sum() < 12:
            return None

        def residuals(x):
            pp, _, H = projected(x, H0_plastic, shape, pts, nrm, kinds)
            j = corr[use]
            r = ((pp[use] - segs[j, :2]) * sn[j]).sum(1) / px_per_mm
            prior = [x[8] / PLACEMENT_MM, x[9] / PLACEMENT_MM, x[10] / PLACEMENT_DEG]
            return np.concatenate([r, prior])

        params = least_squares(residuals, params, loss="soft_l1", f_scale=ROBUST_MM, max_nfev=200).x
    pp, dirs, H = projected(params, H0_plastic, shape, pts, nrm, kinds)
    px_per_mm = local_scale(H, MODELS[shape]["label"])
    corr = correspond(pp, dirs, segs, ON_MM * px_per_mm)
    support = {k: round(float((corr[kinds == k] >= 0).mean()), 2) for k in ("face", "recess", "label")}
    return H / H[2, 2], (float(params[8]), float(params[9]), float(params[10])), support


def local_scale(H, rect):
    x0, y0, x1, y1 = rect
    q = project(H, [[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
    return np.sqrt(abs(cv2.contourArea(q.astype(np.float32))) / ((x1 - x0) * (y1 - y0)))


# The pose search: where no good start is known, many poses of the cartridge model near the label photo's evidence
# are scored cheaply against the photo's segments, and the best few refined by fit_nested.
MAP_SIDE = 1000           # the edge maps' long side, px
DIRECTIONS = 8            # edge direction bins over 180 degrees
SEARCH_TURNS = (-10, -5, 0, 5, 10)   # degrees around each quarter turn of the base angle
SEARCH_SCALES = (0.8, 0.87, 0.93, 1.0, 1.07, 1.15, 1.25)
SEARCH_RANGE = 25.0       # mm: the label's centre searched within this of the evidence's centre
SEARCH_STEP = 1.5         # mm
SEARCH_SIGMA = 0.7        # mm: how fast a sample point's score falls with its distance from an edge
SEARCH_REFINE = 6         # the best distinct poses refined


def edge_maps(segs, size):
    """Per edge direction bin, the distance (px of the map) to the nearest segment of about that direction, and the
    map's scale (photo px per map px)."""
    scale = max(1.0, max(size) / MAP_SIDE)
    w, h = int(np.ceil(size[0] / scale)) + 1, int(np.ceil(size[1] / scale)) + 1
    angle = np.degrees(np.arctan2(segs[:, 3] - segs[:, 1], segs[:, 2] - segs[:, 0])) % 180
    b = np.round(angle / (180 / DIRECTIONS)).astype(int) % DIRECTIONS
    maps = []
    for k in range(DIRECTIONS):
        img = np.full((h, w), 255, np.uint8)
        for s_ in segs[(b == k) | (b == (k + 1) % DIRECTIONS) | (b == (k - 1) % DIRECTIONS)] / scale:
            cv2.line(img, (int(round(s_[0])), int(round(s_[1]))), (int(round(s_[2])), int(round(s_[3]))), 0, 1)
        maps.append(cv2.distanceTransform(img, cv2.DIST_L2, 3))
    return np.stack(maps), scale


def base_estimate(lp, lines=()):
    """A label photo's rough turn (degrees; None if unknown) and scale (photo px per mm) from its evidence. The turn:
    the direction most of the text read in its circle runs (weighted by length; RapidOCR's lines read in order): on
    the sample, along the label on 193 of 194 label photos (a detail's turn was a quarter turn off on 17 of 152). The
    scale: the median of its details' and its serial line's (about 2.2 mm tall), else its circle (a label's diagonal)."""
    weight = {}
    for line in lines:
        c = np.float64(line["corners"])
        if np.hypot(*(c.mean(0) - lp["centre"])) > lp["radius"]:
            continue
        v = c[1] - c[0]
        a = np.degrees(np.arctan2(v[1], v[0]))
        q = int(np.round(a / 90)) % 4
        weight.setdefault(q, []).append((np.linalg.norm(v), a))
    turn = None
    if weight:
        q = max(weight, key=lambda k: sum(w for w, _ in weight[k]))
        ws = weight[q]
        turn = float(np.degrees(np.arctan2(sum(w * np.sin(np.radians(a)) for w, a in ws), sum(w * np.cos(np.radians(a)) for w, a in ws))))
    scales = [d["px_per_mm"] for d in lp.get("details", [])]
    for t in lp["strings"][:1]:
        c = np.float64(t["corners"])
        scales.append((np.linalg.norm(c[3] - c[0]) + np.linalg.norm(c[2] - c[1])) / 2 / 2.2)
    scale = float(np.median(scales)) if scales else float(lp["radius"] / find.LABEL_DIAGONAL)
    return turn, scale


def search_poses(lp, shape, maps, map_scale, lines=()):
    """The best distinct poses (plastic mm -> photo, similarities) of the cartridge model near the label photo, by how
    close the model's sample points land to segments of their own direction: [(score, H)]."""
    pts, nrm, kinds = model_samples(shape)
    x0, y0, x1, y1 = MODELS[shape]["label"]
    centre_mm = np.array([(x0 + x1) / 2, (y0 + y1) / 2])
    rel = pts - centre_mm
    tangent_angle = np.degrees(np.arctan2(nrm[:, 0], -nrm[:, 1])) % 180  # the edge's direction, perpendicular to its normal
    base_angle, base_scale = base_estimate(lp, lines)
    quarters = (0,) if base_angle is not None else (0, 90, 180, 270)
    base_angle = base_angle or 0.0
    centre = np.float64(lp["outline"]).mean(0) if len(lp["outline"]) >= 3 else np.float64(lp["centre"])
    nd, mh, mw = maps.shape
    results = []
    for quarter in quarters:
        for dt in SEARCH_TURNS:
            th = np.radians(base_angle + quarter + dt)
            R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
            bins = np.round(((tangent_angle + np.degrees(th)) % 180) / (180 / DIRECTIONS)).astype(int) % DIRECTIONS
            for k in SEARCH_SCALES:
                ppm = base_scale * k
                offs = (rel @ R.T) * ppm / map_scale  # sample points around the label's centre, map px
                step = SEARCH_STEP * ppm / map_scale
                n = int(SEARCH_RANGE / SEARCH_STEP)
                grid = np.arange(-n, n + 1) * step
                cx = centre[0] / map_scale + grid
                cy = centre[1] / map_scale + grid
                X = cx[None, :, None] + offs[:, 0][:, None, None]   # samples x positions-x x 1
                Y = cy[None, None, :] + offs[:, 1][:, None, None]   # samples x 1 x positions-y
                xi = np.clip(np.round(X).astype(int), 0, mw - 1)
                yi = np.clip(np.round(Y).astype(int), 0, mh - 1)
                inside = (X >= 0) & (X < mw) & (Y >= 0) & (Y < mh)
                d = maps[bins[:, None, None], yi, xi] * map_scale / ppm  # mm
                score = (np.exp(-(d / SEARCH_SIGMA) ** 2) * inside).mean(0)  # positions-x x positions-y
                i, j = np.unravel_index(np.argmax(score), score.shape)
                for i, j in zip(*np.unravel_index(np.argsort(-score, axis=None)[:3], score.shape)):
                    c = np.array([cx[i], cy[j]]) * map_scale
                    A = ppm * R
                    t = c - A @ centre_mm
                    H = np.array([[A[0, 0], A[0, 1], t[0]], [A[1, 0], A[1, 1], t[1]], [0, 0, 1]])
                    results.append((float(score[i, j]), H, c, base_angle + quarter + dt, ppm))
    results.sort(key=lambda r: -r[0])
    chosen = []
    for r in results:  # distinct: centres over 3 mm apart, or turns over 5 degrees
        if all(np.linalg.norm(r[2] - c[2]) > 3 * r[4] or abs((r[3] - c[3] + 180) % 360 - 180) > 5 for c in chosen):
            chosen.append(r)
        if len(chosen) >= SEARCH_REFINE:
            break
    return [(r[0], r[1]) for r in chosen]


def similarity_to_H(centre, angle_deg, px_per_mm, shape):
    """label mm -> photo: the label's centre at centre, turned by angle, at px_per_mm."""
    w, h = shapes.LABEL_MM[shape]
    a = np.radians(angle_deg)
    R = px_per_mm * np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
    t = np.asarray(centre) - R @ [w / 2, h / 2]
    return np.vstack([np.hstack([R, t[:, None]]), [0, 0, 1]])


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


def rigid_fit(a, b):
    """b ~ R(theta) a + t, least squares: (theta degrees, t)."""
    ca, cb = a.mean(0), b.mean(0)
    A, B = a - ca, b - cb
    theta = np.arctan2((A[:, 0] * B[:, 1] - A[:, 1] * B[:, 0]).sum(), (A * B).sum())
    R = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    return np.degrees(theta), cb - R @ ca


def candidate(lp, H0_plastic, segs, start):
    """A start (plastic mm -> photo) refined by the nested fit: the fit, or None if it fails the support checks."""
    shape = lp["shape"]
    result = fit_nested(H0_plastic, shape, segs)
    if result is None:
        return None
    H, placement, support = result
    if not np.all(np.isfinite(H)) or abs(np.linalg.det(H)) < 1e-12:
        return None
    if np.mean(list(support.values())) < MIN_SUPPORT or support["face"] < MIN_FACE:
        return None
    cut = H @ placement_matrix(shape, placement[0], placement[1], np.radians(placement[2])) @ label_to_plastic(shape)
    return {"cut_to_photo": cut / cut[2, 2], "plastic_to_photo": H, "placement": placement, "support": support, "start": start}


def fit_label_photo(job):
    """Stage 1 for one label photo: (key, fit or None, why)."""
    lp, edges_dir, text_dir = job
    if not lp["shape"]:
        return lp["key"], None, "no shape"
    shape = lp["shape"]
    e = np.load(os.path.join(edges_dir, lp["photo"] + ".npz"))
    segs, size = e["segments"].astype(np.float64), tuple(int(v) for v in e["size"])
    mean_support = lambda f: np.mean(list(f["support"].values()))
    # placed by a logo: kept if it passes
    if lp.get("placed_by") and len(lp["outline"]) == 4:
        mm = corners_mm(shape)
        Hl = cv2.getPerspectiveTransform(mm.astype(np.float32), np.float32(lp["outline"])).astype(np.float64)
        f = candidate(lp, Hl @ np.linalg.inv(label_to_plastic(shape)), segs, "placed by " + lp["placed_by"])
        if f is not None:
            return lp["key"], f, None
    # outline starts, all of the photo's, the best supported: keeping only those near the label photo (its circle)
    # dropped right ones (evaluation set: 94 % under 5 mm against 96 %, 87 against 98 % where main's fitter had
    # failed); with several cartridges in a photo, one may take another's outline
    found = []
    for H0, i, what in outlines.outline_starts(e["quads"], shape, size):
        f = candidate(lp, H0, segs, f"outline ({what})")
        if f is not None:
            found.append(f)
    if found:
        return lp["key"], max(found, key=mean_support), None
    # the pose search, as a fallback
    lines = json.load(open(os.path.join(text_dir, lp["photo"] + ".json")))["lines"]
    maps, map_scale = edge_maps(segs, size)
    for score, Hp in search_poses(lp, shape, maps, map_scale, lines):
        f = candidate(lp, Hp, segs, f"search ({score:.2f})")
        if f is not None:
            found.append(f)
    if found:
        return lp["key"], max(found, key=mean_support), None
    return lp["key"], None, "no outline found"


def stage1(lps, edges_dir, pairs, workers=8):
    """The fits, in parallel: key -> fit; key -> why for those that failed."""
    text_dir = os.path.join(os.path.dirname(edges_dir), "read-text")
    fits, failed = {}, {}
    with Pool(workers) as pool:
        for key, f, why in pool.imap_unordered(fit_label_photo, [(lp, edges_dir, text_dir) for lp in lps]):
            if f is None:
                failed[key] = why
            else:
                fits[key] = f
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
                  "plastic_to_photo": f["plastic_to_photo"].tolist(),
                  "placement": [round(v, 3) for v in f["placement"]],
                  "start": f["start"], "support": f["support"],
                  "fallback": None if not f["start"].startswith("search") else "found by the pose search",
                  "residual_mm": None if residual.get(k) is None else round(residual[k], 3)}
    return {"label_photos": out, "sets": set_info, "unsolved": failed}


def page(out_dir, chosen, result, sizes):
    lps = result["label_photos"]
    rel = os.path.relpath(".", out_dir)
    kinds = ["placed", "outline", "search"]
    group = lambda r: next((k for k in kinds if r["start"].startswith(k)), "search")
    by_kind = {k: sorted([(key, r) for key, r in lps.items() if group(r) == k], key=lambda kv: -kv[1]["support"]["face"]) for k in kinds}

    def figure(key, r):
        s = r["photo"]; w, h = sizes[s]
        quad = project(r["cut_to_photo"], corners_mm(r["shape"]))
        pts = " ".join(f"{x:.0f},{y:.0f}" for x, y in quad)
        m = MODELS[r["shape"]]
        box = project(r["plastic_to_photo"], [[m["box"][0], m["box"][1]], [m["box"][2], m["box"][1]], [m["box"][2], m["box"][3]], [m["box"][0], m["box"][3]]])
        rec = project(r["plastic_to_photo"], [[m["recess"][0], m["recess"][1]], [m["recess"][2], m["recess"][1]], [m["recess"][2], m["recess"][3]], [m["recess"][0], m["recess"][3]]])
        extra = "".join(f'<polygon points="{" ".join(f"{x:.0f},{y:.0f}" for x, y in q)}" fill="none" stroke="{c}" stroke-width="{max(w, h) / 400:.1f}"/>' for q, c in ((box, "#08f"), (rec, "#fa0")))
        return (f'<figure><div class="ph"><img loading="lazy" src="{rel}/{chosen[s]}"><svg viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
                f'{extra}<polygon points="{pts}" fill="none" stroke="#0c0" stroke-width="{max(w, h) / 250:.1f}"/>'
                f'<circle cx="{quad[0][0]:.0f}" cy="{quad[0][1]:.0f}" r="{max(w, h) / 80:.0f}" fill="#f00"/></svg></div>'
                f'<figcaption><code>{html.escape(key[:14])}</code> {html.escape(r["start"][:30])}<br>support {r["support"]}, placement {r["placement"]}, residual {r["residual_mm"]} mm</figcaption></figure>')

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
<p>Blue: the cartridge's outline; orange: the recess; green: the label's cut (canonical size); red dot: the label's top left. Grouped by how the fit was started; within a group, most outline support first.</p>
<h2>Not solved ({len(result["unsolved"])})</h2><ul>{unsolved}</ul>
{"".join(f'<h2>Started from: {k} ({len(by_kind[k])})</h2>' + "".join(figure(key, r) for key, r in by_kind[k]) for k in kinds)}
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
