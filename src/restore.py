# restore: an image of every print from its label photos, into <generated>/restore/:
#   <print>.avif: the restored print at straighten's PX_PER_MM, cropped to its family's cut (cuts.crop: the median of
#     each side of the stickers' cuts found by straighten, INSET mm inward, whole pixels; the same for every print of
#     the family); its colours scaled so its paper is white (see paper_white) where paper is found, else the label
#     photos' evened to their median (the user: one image per print)
#   <print>.json: {"crop" (cuts.crop's: x, y, w, h px in the straightened images, mm), "keys" (its label photos used),
#     "pooled" (other prints' label photos used, see pooling),
#     "pooled_share" ({key: the share of the label where it counts}), "single" (from one label photo), "bands" (how
#     many label photos count in each band, finest first), "paper" (the paper's colour found, or null)}
# The label photos: the print's own (poor fits left out), and those of the other prints of its family where they show
# what the print's own show (pooling, below). Each straightened label photo's colours evened per channel to the
# median of the print's own (a scale and offset), then split into frequency bands in Oklab (a Laplacian pyramid, halving until
# the image is under 8 px across). Per band and pixel, a label photo counts unless the band is finer than its own
# photo's resolution (the fit's photo pixels per mm), its straightened image is empty there (off the photo), it lies
# outside its own sticker's cut moved cuts.INSET mm inward (plastic, and the highlight or shadow on the cut's edge) or, for
# another print's label photo, it doesn't match the print's own there; in coarser bands, only where the whole pixel
# counts. Outside where it counts, each is filled from its nearest pixel that counts before it's split into bands (so
# neither black nor plastic leaks into the coarse bands). Before combining, the print's own label photos are registered finely at full resolution (register), the
# other prints' to their median (register_to_own_photos). Combined per band: one
# label photo as it is; two averaged; three or more by the median.
# (Tried: weighting by each band's local energy, as in focus stacking, with Tukey's biweight: the user found the plain
# median removes noise better; noise and dirt have high local energy too. To experiment with later: energy only to
# leave out clearly blurred regions.)
# Done again when an image is older than this file, cuts.py, prints.json, solve.json or its family's straightened
# images and cuts.
# Usage: restore.py [--sample] [--workers N]
import argparse, html, json, os, sys, warnings
import cv2, numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photos, steps, straighten, shapes, cuts, prints as prints_step
from scipy import ndimage

QUALITY = 90
MAX_PHOTOS = 30        # the sharpest kept, if a print has more


# sRGB <-> Oklab (Björn Ottosson's), on float images in 0..1 (BGR in and out, as OpenCV's)
_M1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929], [0.2119034982, 0.6806995451, 0.1073969566],
                [0.0883024619, 0.2817188376, 0.6299787005]])
_M2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468], [1.9779984951, -2.4285922050, 0.4505937099],
                [0.0259040371, 0.7827717662, -0.8086757660]])


def to_oklab(bgr):
    rgb = bgr[..., ::-1]
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    lms = np.cbrt(lin @ _M1.T)
    return (lms @ _M2.T).astype(np.float32)


def from_oklab(lab):
    lms = (lab @ np.linalg.inv(_M2).T) ** 3
    lin = np.clip(lms @ np.linalg.inv(_M1).T, 0, 1)
    rgb = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * np.power(lin, 1 / 2.4) - 0.055)
    return rgb[..., ::-1].astype(np.float32)


def pyramid(img):
    """A Laplacian pyramid: [band 0 (finest), ..., the residual]."""
    levels, cur = [], img
    while min(cur.shape[:2]) >= 16:
        down = cv2.pyrDown(cur)
        up = cv2.pyrUp(down, dstsize=(cur.shape[1], cur.shape[0]))
        levels.append(cur - up)
        cur = down
    levels.append(cur)
    return levels


def collapse(levels):
    cur = levels[-1]
    for band in reversed(levels[:-1]):
        cur = cv2.pyrUp(cur, dstsize=(band.shape[1], band.shape[0])) + band
    return cur


def even_to(img, ref, valid):
    """img's colours evened per channel to ref (a scale and offset, fitted on valid pixels, the best 80 %)."""
    out = img.copy()
    for c in range(3):
        x, y = img[..., c][valid], ref[..., c][valid]
        if len(x) < 100:
            continue
        A = np.c_[x, np.ones_like(x)]
        coef = np.linalg.lstsq(A, y, rcond=None)[0]
        r = np.abs(A @ coef - y)
        ok = r <= np.percentile(r, 80)  # <=: with residuals all zero (one label photo, its own reference), < kept none
        coef = np.linalg.lstsq(A[ok], y[ok], rcond=None)[0]
        out[..., c] = img[..., c] * coef[0] + coef[1]
    return np.clip(out, 0, 1)


# Fine registration at full resolution: solve aligns a print's label photos by their pixels at 5 px/mm, which leaves
# 0.4-1.8 px (at 20 px/mm) between them, most at the label's top and bottom, enough to blur small text in a median.
# Each label photo (lighting-evened gray) is aligned to the print's median by a homography (ECC), the median rebuilt,
# REGISTER_ROUNDS times; then by a smooth local correction: dense optical flow (DIS) against the median, smoothed over
# FLOW_SMOOTH_MM and limited to FLOW_MAX_PX, so a gentle bend or lens distortion is followed, not a detail (dirt isn't
# pulled into place).
REGISTER_ROUNDS = 2
FLOW_SMOOTH_MM = 2.0
FLOW_MAX_PX = 3.0


def evened_gray(img, valid):
    g = cv2.cvtColor((img * 255).astype(np.uint8), cv2.COLOR_BGR2GRAY).astype(np.float32)
    P = straighten.PX_PER_MM
    m = cv2.GaussianBlur(g, (0, 0), P / 2)
    s = np.sqrt(cv2.GaussianBlur((g - m) ** 2, (0, 0), P / 2)) + 2
    return np.where(valid, (g - m) / s, 0).astype(np.float32)


WARP_INTERPOLATION = cv2.INTER_LANCZOS4


def warp(img, M, flow=None, nearest=False, interpolation=None):
    """img resampled once: out(x) = img(M (x + flow(x))) (M: out px -> img px). One resampling, with a sharp kernel:
    a homography and then the flow, each bilinear, had softened every label photo (DMG-KYJ's sharpest: 0.57 -> 0.38 of
    its detail measure) and so every restored print."""
    h, w = img.shape[:2]
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    if flow is not None:
        gx, gy = gx + flow[..., 0], gy + flow[..., 1]
    pts = cv2.perspectiveTransform(np.dstack([gx, gy]).reshape(-1, 1, 2).astype(np.float64), np.float64(M)).reshape(h, w, 2)
    inter = cv2.INTER_NEAREST if nearest else (interpolation if interpolation is not None else WARP_INTERPOLATION)
    return cv2.remap(img, pts[..., 0].astype(np.float32), pts[..., 1].astype(np.float32), inter,
                     borderMode=cv2.BORDER_CONSTANT, borderValue=0)


ECC_CRITERIA = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-5)


def homography_to(ref, gray, valid, M):
    """M refined (ECC) so gray, warped by it, lies on ref; M as it was if ECC fails."""
    try:
        return cv2.findTransformECC(ref, gray, M, cv2.MOTION_HOMOGRAPHY, ECC_CRITERIA, valid, 5)[1]
    except cv2.error:
        return M


def warped_onto(ref, entry, gray, M):
    """entry (image, valid, px/mm) resampled onto ref: its homography M, then a smooth local correction (optical flow
    against ref, smoothed over FLOW_SMOOTH_MM, limited to FLOW_MAX_PX)."""
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    to8 = lambda x: np.clip(x * 40 + 128, 0, 255).astype(np.uint8)
    flow = dis.calc(to8(ref), to8(warp(gray, M)), None)        # ref px -> where it is in the aligned photo
    flow = cv2.GaussianBlur(flow, (0, 0), FLOW_SMOOTH_MM * straighten.PX_PER_MM)
    mag = np.linalg.norm(flow, axis=2, keepdims=True)
    flow = (flow * np.minimum(1, FLOW_MAX_PX / np.maximum(mag, 1e-6))).astype(np.float32)
    return (warp(entry[0], M, flow), warp(entry[1].astype(np.uint8), M, flow, nearest=True) > 0, entry[2])


def register(entries):
    """A print's own label photos (image, valid, px/mm) aligned to their median: a homography each, then a smooth
    local correction."""
    valids = [e[1].astype(np.uint8) for e in entries]
    grays = [evened_gray(e[0], v > 0) for e, v in zip(entries, valids)]
    Ms = [np.eye(3, dtype=np.float32) for _ in entries]
    for _ in range(REGISTER_ROUNDS):
        ref = np.median(np.stack([warp(g, M) for g, M in zip(grays, Ms)]), 0)
        Ms = [homography_to(ref, g, v, M) for g, v, M in zip(grays, valids, Ms)]
    ref = np.median(np.stack([warp(g, M) for g, M in zip(grays, Ms)]), 0)
    return [warped_onto(ref, e, g, M) for e, g, M in zip(entries, grays, Ms)]


def register_to_own_photos(own_ref, entry):
    """Another print's label photo (image, valid, px/mm) aligned to own_ref (the evened gray median of the print's own
    label photos, registered), as register aligns the print's own to their median."""
    valid = entry[1].astype(np.uint8)
    gray = evened_gray(entry[0], valid > 0)
    M = np.eye(3, dtype=np.float32)
    for _ in range(REGISTER_ROUNDS):
        M = homography_to(own_ref, gray, valid, M)
    return warped_onto(own_ref, entry, gray, M)


# Pooling: the label photos of the family's other prints (solve's family, split by prints) count in a restored print
# only where they show what the print's own label photos show; prints' comparison only tells prints apart (it ignores
# the label's outer millimetre and tiles textured in one photo only, which is right for that and wrong for this).
# Each is registered to the median of the print's own and its colours evened to the same median as theirs, then
# compared with each of them per pixel, over a POOL_WINDOW_MM square, on gray blurred POOL_BLUR_MM: where both are
# textured (gray spread over POOL_TEXTURE), the gray must correlate over POOL_CORRELATION; where both are flat, the
# mean colours must differ under POOL_COLOR_DIFF; textured in one and flat in the other never matches (small text on
# paper hardly moves the mean colour: DMG-JU-FAH's "this side out" showed in DMG-JU-USA that way). It counts where it
# matches more than half of the print's own label photos, and not at all if that's under POOL_MIN_SHARE of the label.
# The thresholds are prints' tile comparison's, not yet measured for this.
POOL_WINDOW_MM = 1.0
POOL_BLUR_MM = 0.25
POOL_TEXTURE = 6.0
POOL_CORRELATION = 0.0
POOL_COLOR_DIFF = 15.0
POOL_MIN_SHARE = 0.15


def where_other_print_photo_matches_own_photos(other, own):
    """H x W booleans: where another print's label photo (image 0..1 BGR, valid) matches more than half of the print's
    own label photos [(image, valid)], all registered and evened to the same median. See pooling."""
    P = straighten.PX_PER_MM
    k = max(1, int(round(POOL_WINDOW_MM * P)))
    box = lambda x: cv2.boxFilter(x, -1, (k, k))

    def local(img, valid):
        g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) * 255, (0, 0), POOL_BLUR_MM * P)
        m = box(g)
        var = np.maximum(box(g * g) - m * m, 0)
        return g, m, var, box(img * 255), box(valid.astype(np.float32)) > 0.999

    og, om, ovar, ocol, ocover = local(*other)
    votes = np.zeros(og.shape, np.int32)
    for img, valid in own:
        g, m, var, col, cover = local(img, valid)
        corr = (box(og * g) - om * m) / np.sqrt(ovar * var + 1e-9)
        o_tex, s_tex = np.sqrt(ovar) > POOL_TEXTURE, np.sqrt(var) > POOL_TEXTURE
        matches = ((o_tex & s_tex & (corr > POOL_CORRELATION))
                   | (~o_tex & ~s_tex & (np.abs(ocol - col).mean(2) < POOL_COLOR_DIFF)))
        votes += matches & cover
    return ocover & (votes > len(own) / 2)


def finest_band(photo_px_per_mm):
    """The finest band (0 = straighten's full resolution) a photo with this many pixels per mm carries: band k holds
    detail about 2^k pixels of straighten's across, which needs about as many of the photo's per mm."""
    ratio = straighten.PX_PER_MM / max(photo_px_per_mm, 1e-6)
    return max(0, int(np.floor(np.log2(max(ratio, 1.0)))))


# Local sharpness: a label photo blurred in places (out of focus, motion, a soft lens corner) has little detail there in
# the fine bands, and the median of crisp and blurred photos is soft (DMG-KYJ: six label photos of 16-44 px/mm, all
# counting in the finest band by their resolution, two of them clearly soft). Per band and pixel, a label photo's
# local detail is its band's lightness magnitude averaged over SHARP_MM; it counts only where that is at least
# SHARP_SHARE of the second most detailed label photo's there (the second: dirt or noise on one photo has detail too,
# and mustn't push the others out). Only to leave out what's clearly blurred, never to favour the most detailed (the
# energy-weighted median favoured noise and dirt). Needs three or more label photos: with two, which is blurred and
# which is dirty can't be told.
SHARP_MM = 1.0
SHARP_SHARE = 0.5


def sharp_enough(L, counts, lv):
    """n x H x W: whether each label photo is sharp enough at each pixel of band lv (L: the band's lightness; counts:
    where each label photo counts at all)."""
    sigma = max(1.0, SHARP_MM * straighten.PX_PER_MM / 2 ** lv)
    detail = np.stack([cv2.GaussianBlur(np.abs(l).astype(np.float32), (0, 0), sigma) for l in L]) * counts
    second = np.sort(detail, axis=0)[-2] if len(L) >= 2 else detail[0]
    return detail >= SHARP_SHARE * second


def filled(img, where):
    """img with the pixels outside where set to their nearest pixel inside (img as it is if where is empty)."""
    if where.all() or not where.any():
        return img
    idx = ndimage.distance_transform_edt(~where, return_distances=False, return_indices=True)
    return img[idx[0], idx[1]]


def restore_print(job):
    """Restores one print: (print id, the result's description)."""
    pid, shape, own, others, px_per_mm, crop, out_base = job
    P = straighten.PX_PER_MM
    x0, y0, w, h = crop["x"], crop["y"], crop["w"], crop["h"]
    size, px_to_mm = straighten.canvas(shape)

    def load(key, path):  # (image 0..1 BGR cropped, valid mask, px/mm) or None
        img = cv2.imread(path)
        if img is None:
            return None
        valid = img.max(2) > 1    # straighten's border outside the photo is black
        cut = straighten.load_cut(os.path.dirname(os.path.dirname(path)), key)
        if cut is not None:
            valid &= cuts.mask(cut, shape, size, px_to_mm)
        img = img[y0:y0 + h, x0:x0 + w].astype(np.float32) / 255
        return img, valid[y0:y0 + h, x0:x0 + w], px_per_mm.get(key, P)

    loaded = [(k, load(k, path)) for k, path in own]
    loaded = [(k, e) for k, e in loaded if e is not None]
    if not loaded:
        return pid, None
    if len(loaded) > MAX_PHOTOS:
        loaded = sorted(loaded, key=lambda ke: -ke[1][2])[:MAX_PHOTOS]
    own_keys = [k for k, _ in loaded]
    entries = [e for _, e in loaded]
    if len(entries) >= 2:
        entries = register(entries)
    ref = np.median(np.stack([e[0] for e in entries]), 0)
    evened = [even_to(e[0], ref, e[1]) for e in entries]
    own_ref = np.median(np.stack([evened_gray(e[0], e[1]) for e in entries]), 0)
    own_photos = list(zip(evened, [e[1] for e in entries]))
    valids = [e[1] for e in entries]
    pooled_share = {}
    for key, path in others:
        e = load(key, path)
        if e is None:
            continue
        img, valid, ppm = register_to_own_photos(own_ref, e)
        img = even_to(img, ref, valid)
        counts = where_other_print_photo_matches_own_photos((img, valid), own_photos)
        if counts.mean() >= POOL_MIN_SHARE:
            entries.append((img, counts, ppm))
            evened.append(img)
            valids.append(valid)
            pooled_share[key] = round(float(counts.mean()), 3)
    n = len(entries)
    pyrs = [pyramid(to_oklab(filled(img, v))) for img, v in zip(evened, valids)]
    levels = len(pyrs[0])
    out_levels, out_median, counts = [], [], []
    for lv in range(levels):
        vals = np.stack([p[lv] for p in pyrs])                                   # n x H x W x 3
        hh, ww = vals.shape[1:3]
        weights = []
        for e, p in zip(entries, pyrs):
            # where it counts (on the photo; for another print's label photo, where it matches): the whole pixel
            counts_here = cv2.resize(e[1].astype(np.float32), (ww, hh), interpolation=cv2.INTER_AREA) > 0.99
            wgt = counts_here.astype(np.float32)
            if lv < levels - 1 and lv < finest_band(e[2]):
                wgt[:] = 0
            weights.append(wgt)
        W = np.stack(weights)
        if n >= 3 and lv < levels - 1:
            W *= sharp_enough(vals[..., 0], W > 0, lv)
        total = W.sum(0)
        Wn = W / np.maximum(total, 1e-12)
        counts.append(int(np.median((W > 0).sum(0))))
        if n == 1:
            est = vals[0]
        elif n == 2:
            est = (Wn[..., None] * vals).sum(0)
        else:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)  # pixels no label photo covers
                est = np.nan_to_num(np.nanmedian(np.where((W > 0)[..., None], vals, np.nan), axis=0))
        # where nothing counts in this band (finer than every photo): no detail
        est = np.where((total > 1e-12)[..., None], est, 0 if lv < levels - 1 else vals.mean(0))
        out_levels.append(est.astype(np.float32))
    result = np.clip(from_oklab(collapse(out_levels)), 0, 1)
    paper, white = paper_white(result)
    write_avif(out_base + ".avif", white if white is not None else result)
    for old in (out_base + "-median.avif", out_base + "-paper.avif"):
        if os.path.exists(old):
            os.remove(old)
    return pid, {"crop": crop, "keys": own_keys, "pooled": list(pooled_share), "pooled_share": pooled_share, "single": n == 1,
                 "bands": counts,
                 "paper": None if paper is None else [round(float(v), 3) for v in paper]}


def canonical_crop(shape):
    """The canonical label at ink coordinates' origin, as cuts.crop gives a crop (when no cut was found at all)."""
    P, M = straighten.PX_PER_MM, straighten.MARGIN
    lw, lh = shapes.LABEL_MM[shape]
    x, y = int(round(M * P)), int(round(M * P))
    return {"x": x, "y": y, "w": int(round(lw * P)), "h": int(round(lh * P)), "mm": [0.0, 0.0, lw, lh]}


def write_avif(path, img):
    tmp = path + ".tmp.avif"
    cv2.imwrite(tmp, (np.clip(img, 0, 1) * 255).round().astype(np.uint8), [cv2.IMWRITE_AVIF_QUALITY, QUALITY])
    os.replace(tmp, path)


# Paper white: the paper is the restored image's brightest near-neutral pixels (Oklab chroma under PAPER_CHROMA, in the
# top PAPER_TOP of the lightness among those), at least PAPER_MIN of the label; each channel scaled in linear light so
# the paper at its PAPER_WHITE quantile of lightness becomes white: only the brightest of the paper clips (the user:
# the paper's median made white, 5 % over, clipped far too much). A label with too little such paper isn't done.
# Black point, likewise (the user: the printed solid black's texture crushed, that's the point): the ink is the
# near-neutral pixels darker than INK_MAX lightness, at least INK_MIN of the label; the ink at its INK_BLACK quantile of
# lightness becomes black (an offset per channel in linear light, so the black is neutral too), the darkest of it
# clipped. A label with too little such ink keeps its blacks as they are.
PAPER_CHROMA = 0.04
PAPER_TOP = 0.5
PAPER_MIN = 0.03
PAPER_WHITE = 0.9
INK_MAX = 0.4
INK_MIN = 0.01
INK_BLACK = 0.1


def paper_white(bgr):
    """(the paper's colour BGR 0..1, the image with paper white and, where there's ink enough, ink black) or (None, None)."""
    lab = to_oklab(bgr)
    neutral = np.hypot(lab[..., 1], lab[..., 2]) < PAPER_CHROMA
    if neutral.mean() < PAPER_MIN:
        return None, None
    L = lab[..., 0][neutral]
    paper = neutral & (lab[..., 0] >= np.quantile(L, 1 - PAPER_TOP))
    if paper.mean() < PAPER_MIN or np.median(lab[..., 0][paper]) < 0.6:
        return None, None
    lin = np.where(bgr <= 0.04045, bgr / 12.92, ((bgr + 0.055) / 1.055) ** 2.4)
    light = lab[..., 0][paper]
    brightest = paper.copy()
    brightest[paper] = light >= np.quantile(light, PAPER_WHITE)
    white_lin = np.median(lin[brightest], axis=0)  # the colour of the paper's brightest tenth, so its hue stays even
    ink = neutral & (lab[..., 0] < INK_MAX)
    black_lin = np.zeros(3)
    if ink.mean() >= INK_MIN:
        dark = ink.copy()
        dark[ink] = lab[..., 0][ink] <= np.quantile(lab[..., 0][ink], INK_BLACK)
        black_lin = np.median(lin[dark], axis=0)
    out = np.clip((lin - black_lin) / np.maximum(white_lin - black_lin, 1e-3), 0, 1)
    out = np.where(out <= 0.0031308, out * 12.92, 1.055 * np.power(out, 1 / 2.4) - 0.055)
    return np.median(bgr[paper], axis=0), out.astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    gen = photos.generated(args.sample)
    prints_file, solve_file = os.path.join(gen, "prints", "prints.json"), os.path.join(gen, "solve", "solve.json")
    for p in (prints_file, solve_file):
        if not os.path.exists(p):
            sys.exit(f"{p} missing: run make prints first")
    result = json.load(open(prints_file))
    solved = json.load(open(solve_file))["label_photos"]
    import solve as solve_step
    px_per_mm = {}
    for k, r in solved.items():  # the photo's pixels per mm at the label, from the fit
        lw, lh = shapes.LABEL_MM[r["shape"]]
        px_per_mm[k] = solve_step.local_scale(np.array(r["cut_to_photo"]), [0, 0, lw, lh])
    poor = {k for k, r in solved.items() if (r.get("fallback") or "").startswith("a poor")}
    out_dir = os.path.join(gen, "restore")
    os.makedirs(out_dir, exist_ok=True)
    image = lambda k: os.path.join(gen, "straighten", straighten.file_name(k))
    base = lambda pid: os.path.join(out_dir, straighten.file_name(pid)[:-5])
    newest = max(os.path.getmtime(p) for p in (prints_file, solve_file, __file__, cuts.__file__))
    by_family = {}
    for p in result["prints"]:
        by_family.setdefault(p["family"], []).append(p)
    crops = {}
    for fam, ps in by_family.items():
        keys = [k for p in ps for k in p["keys"] if k not in poor] or [k for p in ps for k in p["keys"]]
        found = [c for c in (straighten.load_cut(gen, k) for k in keys) if c is not None]
        crops[fam] = (cuts.crop(found, ps[0]["shape"], straighten.PX_PER_MM, straighten.MARGIN) if found
                      else canonical_crop(ps[0]["shape"]))
    mtime = lambda f: os.path.getmtime(f) if os.path.exists(f) else 0
    jobs, wanted = [], set()
    for p in result["prints"]:
        wanted |= {os.path.basename(base(p["id"])) + s for s in (".avif", ".json")}
        own = [(k, image(k)) for k in p["keys"] if k not in poor] or [(k, image(k)) for k in p["keys"]]
        others = [(k, image(k)) for q in by_family[p["family"]] if q is not p for k in q["keys"] if k not in poor]
        inputs = max([newest] + [max(mtime(f), mtime(straighten.cut_file(f))) for _, f in own + others])
        if not os.path.exists(base(p["id"]) + ".avif") or os.path.getmtime(base(p["id"]) + ".avif") < inputs:
            jobs.append((p["id"], p["shape"], own, others, px_per_mm, crops[p["family"]], base(p["id"])))
    for f in os.listdir(out_dir):
        if f not in wanted and f != "index.html":
            os.remove(os.path.join(out_dir, f))
    import multiprocessing
    with multiprocessing.Pool(args.workers) as pool:
        for n, (pid, desc) in enumerate(pool.imap_unordered(restore_print, jobs), 1):
            if desc is not None:
                steps.write_json(base(pid) + ".json", desc)
            if n % 20 == 0 or n == len(jobs):
                print(f"restored {n} of {len(jobs)} prints", flush=True)
    page(out_dir, result, gen)
    print(f"page: {os.path.join(out_dir, 'index.html')}")


def page(out_dir, result, gen):
    """index.html: per print, the restored image (paper white where found, else median colours), and its label photos
    straightened (the same crop)."""
    P, M = straighten.PX_PER_MM, straighten.MARGIN
    rel = os.path.relpath(os.path.join(gen, "straighten"), out_dir)
    figs = []
    for p in sorted(result["prints"], key=lambda p: -len(p["keys"])):
        b = straighten.file_name(p["id"])[:-5]
        if not os.path.exists(os.path.join(out_dir, b + ".avif")):
            continue
        desc = json.load(open(os.path.join(out_dir, b + ".json"))) if os.path.exists(os.path.join(out_dir, b + ".json")) else {}
        c = desc.get("crop") or canonical_crop(p["shape"])
        (cw, ch), _ = straighten.canvas(p["shape"])
        # a straightened label photo cropped by CSS: the image scaled so the crop is 160 px wide
        scale = 160 / c["w"]
        crop = lambda k: (f'<div class="src" style="width:{c["w"] * scale:.0f}px;height:{c["h"] * scale:.0f}px">'
                          f'<img loading="lazy" src="{rel}/{straighten.file_name(k)}" style="width:{cw * scale:.0f}px;'
                          f'margin:{-c["y"] * scale:.0f}px 0 0 {-c["x"] * scale:.0f}px"></div>')
        sources = "".join(crop(k) for k in desc.get("keys", [])) + "".join(crop(k) for k in desc.get("pooled", []))
        figs.append(f'<figure><div class="pair"><img loading="lazy" src="{b}.avif"></div>'
                    f'<figcaption><b>{html.escape(str(p["serial"] or p["release"] or "?"))}</b>: {len(desc.get("keys", []))} label photos'
                    f'{", " + str(len(desc.get("pooled", []))) + " pooled from other prints of its family, where they match (last)" if desc.get("pooled") else ""}'
                    f'{" (one photo: as it is)" if desc.get("single") else ""}{"" if desc.get("paper") else "; no paper found: median colours"}; label photos per band, finest first: {desc.get("bands")}</figcaption>'
                    f'<div class="sources">{sources}</div></figure>')
    with open(os.path.join(out_dir, "index.html"), "w") as f:
        f.write(f"""<!doctype html><meta charset="utf-8"><title>restore</title>
<style>body{{font:14px system-ui;margin:16px;background:#333;color:#eee}} figure{{display:block;margin:12px 0 24px}} .pair img{{width:340px;margin-right:6px}}
figcaption{{font-size:12px;margin:4px 0}} .src{{display:inline-block;overflow:hidden;margin:2px}} .src img{{display:block}}</style>
<h1>restore</h1>
<p>{len(figs)} restored prints, the most label photos first. The restored print: the median of its label photos per band, their colours evened to their median, then its paper made white (clipping a little) where paper is found. Below: its label photos straightened, the same crop.</p>
{"".join(figs)}""")


if __name__ == "__main__":
    main()
