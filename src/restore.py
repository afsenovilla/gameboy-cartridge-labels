# restore: an image of every print from its label photos, into <generated>/restore/:
#   <print>.avif: the restored print, its colours the label photos' evened to their median, cropped to its shape's
#     canonical label size at its family's median cut (the origin of ink coordinates), at straighten's PX_PER_MM
#   <print>-paper.avif: the same, its colours scaled so its paper is white (see paper_white), if paper is found
#   <print>.json: {"keys" (its label photos used), "pooled" (other prints' label photos used where alike), "single"
#     (from one label photo), "bands" (how many label photos count in each band, finest first), "paper" (the paper's
#     colour found, or null)}
# The label photos: the print's own (poor fits left out), and those of nearly-same prints of its family where their
# pair image (prints) says the tiles are alike. Each straightened label photo's colours evened per channel to the
# print's median (a scale and offset), then split into frequency bands in Oklab (a Laplacian pyramid, halving until
# the image is under 8 px across). Per band and pixel, a label photo counts unless the band is finer than its own
# photo's resolution (the fit's photo pixels per mm) or its straightened image is empty there (off the photo).
# Before combining, the label photos are registered finely at full resolution (register). Combined per band: one
# label photo as it is; two averaged; three or more by the median.
# (Tried: weighting by each band's local energy, as in focus stacking, with Tukey's biweight: the user found the plain
# median removes noise better; noise and dirt have high local energy too. To experiment with later: energy only to
# leave out clearly blurred regions.)
# Done again when an image is older than this file, prints.json or solve.json.
# Usage: restore.py [--sample] [--workers N]
import argparse, html, json, os, sys
import cv2, numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photos, steps, straighten, shapes, prints as prints_step

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


def warp(img, M, flow=None, nearest=False):
    h, w = img.shape[:2]
    out = cv2.warpPerspective(img, M, (w, h), flags=(cv2.INTER_NEAREST if nearest else cv2.INTER_LINEAR) | cv2.WARP_INVERSE_MAP,
                              borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    if flow is not None:
        gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
        out = cv2.remap(out, gx + flow[..., 0], gy + flow[..., 1], cv2.INTER_NEAREST if nearest else cv2.INTER_LINEAR,
                        borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    return out


def register(entries):
    """The entries' images (and valid masks, weight maps) aligned to their median: a homography each, then a smooth
    local correction."""
    imgs = [e[0] for e in entries]
    valids = [e[1].astype(np.uint8) for e in entries]
    grays = [evened_gray(i, v > 0) for i, v in zip(imgs, valids)]
    Ms = [np.eye(3, dtype=np.float32) for _ in entries]
    crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-5)
    for _ in range(REGISTER_ROUNDS):
        ref = np.median(np.stack([warp(g, M) for g, M in zip(grays, Ms)]), 0)
        for i, g in enumerate(grays):
            try:
                _, Ms[i] = cv2.findTransformECC(ref, g, Ms[i], cv2.MOTION_HOMOGRAPHY, crit, valids[i], 5)
            except cv2.error:
                pass
    ref = np.median(np.stack([warp(g, M) for g, M in zip(grays, Ms)]), 0)
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    to8 = lambda x: np.clip(x * 40 + 128, 0, 255).astype(np.uint8)
    P = straighten.PX_PER_MM
    out = []
    for e, g, M in zip(entries, grays, Ms):
        flow = dis.calc(to8(ref), to8(warp(g, M)), None)        # ref px -> where it is in the aligned photo
        flow = cv2.GaussianBlur(flow, (0, 0), FLOW_SMOOTH_MM * P)
        mag = np.linalg.norm(flow, axis=2, keepdims=True)
        flow = (flow * np.minimum(1, FLOW_MAX_PX / np.maximum(mag, 1e-6))).astype(np.float32)
        img = warp(e[0], M, flow)
        valid = warp(e[1].astype(np.uint8), M, flow, nearest=True) > 0
        extra = warp(e[2], M, flow) if e[2] is not None else None
        out.append((img, valid, extra, e[3]))
    return out


def finest_band(photo_px_per_mm):
    """The finest band (0 = straighten's full resolution) a photo with this many pixels per mm carries: band k holds
    detail about 2^k pixels of straighten's across, which needs about as many of the photo's per mm."""
    ratio = straighten.PX_PER_MM / max(photo_px_per_mm, 1e-6)
    return max(0, int(np.floor(np.log2(max(ratio, 1.0)))))


def restore_print(job):
    """Restores one print: (print id, the result's description)."""
    pid, shape, own, pooled, px_per_mm, out_base = job
    P, M = straighten.PX_PER_MM, straighten.MARGIN
    lw, lh = shapes.LABEL_MM[shape]
    y0, x0 = int(round(M * P)), int(round(M * P))
    h, w = int(round(lh * P)), int(round(lw * P))
    entries = []  # (image 0..1 BGR cropped, valid mask, extra weight map or None, px/mm)
    for key, path, mask in own + pooled:
        img = cv2.imread(path)
        if img is None:
            continue
        img = img[y0:y0 + h, x0:x0 + w].astype(np.float32) / 255
        valid = img.max(2) > 0.004   # straighten's border outside the photo is black
        extra = None
        if mask is not None:  # another print's label photo: only its alike tiles, smoothed
            extra = cv2.resize(mask, (w, h), interpolation=cv2.INTER_LINEAR)
            extra = cv2.GaussianBlur(extra, (0, 0), P / 2)
        entries.append((img, valid, extra, px_per_mm.get(key, P)))
    if not entries:
        return pid, None
    if len(entries) > MAX_PHOTOS:
        entries = sorted(entries, key=lambda e: -e[3])[:MAX_PHOTOS]
    if len(entries) >= 2:
        entries = register(entries)
    ref = np.median(np.stack([e[0] for e in entries]), 0)
    evened = [even_to(e[0], ref, e[1]) for e in entries]
    n = len(entries)
    pyrs = [pyramid(to_oklab(img)) for img in evened]
    levels = len(pyrs[0])
    out_levels, out_median, counts = [], [], []
    for lv in range(levels):
        vals = np.stack([p[lv] for p in pyrs])                                   # n x H x W x 3
        hh, ww = vals.shape[1:3]
        weights = []
        for e, p in zip(entries, pyrs):
            valid = cv2.resize(e[1].astype(np.float32), (ww, hh), interpolation=cv2.INTER_AREA) > 0.99
            wgt = valid.astype(np.float32)
            if lv < levels - 1 and lv < finest_band(e[3]):
                wgt[:] = 0
            if e[2] is not None:
                wgt *= cv2.resize(e[2], (ww, hh), interpolation=cv2.INTER_AREA)
            weights.append(wgt)
        W = np.stack(weights)
        total = W.sum(0)
        Wn = W / np.maximum(total, 1e-12)
        counts.append(int(np.median((W > 0).sum(0))))
        if n == 1:
            est = vals[0]
        elif n == 2:
            est = (Wn[..., None] * vals).sum(0)
        else:
            est = np.nan_to_num(np.nanmedian(np.where((W > 0)[..., None], vals, np.nan), axis=0))
        # where nothing counts in this band (finer than every photo): no detail
        est = np.where((total > 1e-12)[..., None], est, 0 if lv < levels - 1 else vals.mean(0))
        out_levels.append(est.astype(np.float32))
    result = np.clip(from_oklab(collapse(out_levels)), 0, 1)
    write_avif(out_base + ".avif", result)
    paper, white = paper_white(result)
    if white is not None:
        write_avif(out_base + "-paper.avif", white)
    elif os.path.exists(out_base + "-paper.avif"):
        os.remove(out_base + "-paper.avif")
    for old in (out_base + "-median.avif",):
        if os.path.exists(old):
            os.remove(old)
    return pid, {"keys": [k for k, _, _ in own], "pooled": [k for k, _, _ in pooled], "single": n == 1, "bands": counts,
                 "paper": None if paper is None else [round(float(v), 3) for v in paper]}


def write_avif(path, img):
    tmp = path + ".tmp.avif"
    cv2.imwrite(tmp, (np.clip(img, 0, 1) * 255).round().astype(np.uint8), [cv2.IMWRITE_AVIF_QUALITY, QUALITY])
    os.replace(tmp, path)


# Paper white: the paper is the restored image's brightest near-neutral pixels (Oklab chroma under PAPER_CHROMA, in the
# top PAPER_TOP of the lightness among those), at least PAPER_MIN of the label; each channel scaled in linear light so
# the paper at its PAPER_WHITE quantile of lightness becomes white: only the brightest of the paper clips (the user:
# the paper's median made white, 5 % over, clipped far too much). A label with too little such paper isn't done.
PAPER_CHROMA = 0.04
PAPER_TOP = 0.5
PAPER_MIN = 0.03
PAPER_WHITE = 0.9


def paper_white(bgr):
    """(the paper's colour BGR 0..1, the image with paper white) or (None, None)."""
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
    out = np.clip(lin / np.maximum(white_lin, 1e-3), 0, 1)
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
    poor = set(result["poor_fits"]) | {k for k, r in solved.items() if (r.get("fallback") or "").startswith("a poor")}
    out_dir = os.path.join(gen, "restore")
    os.makedirs(out_dir, exist_ok=True)
    image = lambda k: os.path.join(gen, "straighten", straighten.file_name(k))
    base = lambda pid: os.path.join(out_dir, straighten.file_name(pid)[:-5])
    newest = max(os.path.getmtime(p) for p in (prints_file, solve_file, __file__))
    by_family = {}
    for p in result["prints"]:
        by_family.setdefault(p["family"], []).append(p)
    jobs, wanted = [], set()
    for p in result["prints"]:
        wanted |= {os.path.basename(base(p["id"])) + s for s in (".avif", "-paper.avif", ".json")}
        own = [(k, image(k), None) for k in p["keys"] if k not in poor] or [(k, image(k), None) for k in p["keys"]]
        pooled = []
        pair_dir = os.path.join(gen, "prints", straighten.file_name(p["id"])[:-5])
        for q in by_family[p["family"]]:
            mask_file = os.path.join(pair_dir, straighten.file_name(q["id"])[:-5] + ".png")
            if q is not p and os.path.exists(mask_file):
                m = cv2.imread(mask_file, cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255
                pooled += [(k, image(k), m) for k in q["keys"] if k not in poor]
        if not os.path.exists(base(p["id"]) + ".avif") or os.path.getmtime(base(p["id"]) + ".avif") < newest:
            jobs.append((p["id"], p["shape"], own, pooled, px_per_mm, base(p["id"])))
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
    """index.html: per print, the restored image (median colours, and paper white where found), and its label photos
    straightened (the canonical label's area, the same crop)."""
    P, M = straighten.PX_PER_MM, straighten.MARGIN
    rel = os.path.relpath(os.path.join(gen, "straighten"), out_dir)
    figs = []
    for p in sorted(result["prints"], key=lambda p: -len(p["keys"])):
        b = straighten.file_name(p["id"])[:-5]
        if not os.path.exists(os.path.join(out_dir, b + ".avif")):
            continue
        desc = json.load(open(os.path.join(out_dir, b + ".json"))) if os.path.exists(os.path.join(out_dir, b + ".json")) else {}
        lw, lh = shapes.LABEL_MM[p["shape"]]
        (cw, ch), _ = straighten.canvas(p["shape"])
        # a straightened label photo cropped to the canonical label by CSS: the image scaled so the label is 160 px wide
        scale = 160 / (lw * P)
        crop = lambda k: (f'<div class="src" style="width:{lw * P * scale:.0f}px;height:{lh * P * scale:.0f}px">'
                          f'<img loading="lazy" src="{rel}/{straighten.file_name(k)}" style="width:{cw * scale:.0f}px;'
                          f'margin:{-M * P * scale:.0f}px 0 0 {-M * P * scale:.0f}px"></div>')
        sources = "".join(crop(k) for k in desc.get("keys", [])) + "".join(crop(k) for k in desc.get("pooled", []))
        paper = f'<img loading="lazy" src="{b}-paper.avif" title="paper white">' if os.path.exists(os.path.join(out_dir, b + "-paper.avif")) else '<span class="none">no paper found</span>'
        figs.append(f'<figure><div class="pair"><img loading="lazy" src="{b}.avif" title="median colours">{paper}</div>'
                    f'<figcaption><b>{html.escape(str(p["serial"] or p["release"] or "?"))}</b>: {len(desc.get("keys", []))} label photos'
                    f'{", " + str(len(desc.get("pooled", []))) + " pooled from nearly-same prints (last)" if desc.get("pooled") else ""}'
                    f'{" (one photo: as it is)" if desc.get("single") else ""}; label photos per band, finest first: {desc.get("bands")}</figcaption>'
                    f'<div class="sources">{sources}</div></figure>')
    with open(os.path.join(out_dir, "index.html"), "w") as f:
        f.write(f"""<!doctype html><meta charset="utf-8"><title>restore</title>
<style>body{{font:14px system-ui;margin:16px;background:#333;color:#eee}} figure{{display:block;margin:12px 0 24px}} .pair img{{width:340px;margin-right:6px}} .none{{display:inline-block;width:340px;color:#999}}
figcaption{{font-size:12px;margin:4px 0}} .src{{display:inline-block;overflow:hidden;margin:2px}} .src img{{display:block}}</style>
<h1>restore</h1>
<p>{len(figs)} restored prints, the most label photos first. Left: the restored print (the median of its label photos per band, their colours evened to their median); right: the same with its paper made white (clipping a little), where paper is found. Below: its label photos straightened, the same crop.</p>
{"".join(figs)}""")


if __name__ == "__main__":
    main()
