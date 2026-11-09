# restore: an image of every print from its label photos, into <generated>/restore/:
#   <print>.avif: the restored print, cropped to its shape's canonical label size at its family's median cut (the
#     origin of ink coordinates), at straighten's PX_PER_MM
#   <print>-median.avif: the same by the plain median (prints of three or more label photos), to compare
#   <print>.json: {"keys" (its label photos used), "pooled" (other prints' label photos used where alike), "single"
#     (from one label photo), "bands" (how many label photos count in each band, finest first)}
# The label photos: the print's own (poor fits left out), and those of nearly-same prints of its family where their
# pair image (prints) says the tiles are alike. Each straightened label photo's colours evened per channel to the
# print's median (a scale and offset), then split into frequency bands in Oklab (a Laplacian pyramid, halving until
# the image is under 8 px across). Per band and pixel, each label photo weighs by the band's local energy (blurred over
# a radius larger than the details, as in focus stacking), not at all in bands finer than its own photo's resolution
# (the fit's photo pixels per mm) or where its straightened image is empty (off the photo). Combined per band: one
# label photo as it is; two averaged by weight; three or more by Tukey's biweight (a soft median: from the median,
# values reweighted smoothly by their distance from the estimate; its scale the weighted spread), and by the plain
# median for <print>-median.avif.
# Done again when an image is older than this file, prints.json or solve.json.
# Usage: restore.py [--sample] [--workers N]
import argparse, html, json, os, sys
import cv2, numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photos, steps, straighten, shapes, prints as prints_step

QUALITY = 90
MAX_PHOTOS = 30        # the sharpest kept, if a print has more
ENERGY_BLUR = 4.0      # px at each band's own scale: the radius the band's energy is spread over
TUKEY_C = 4.685
TUKEY_ROUNDS = 5


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


def tukey(values, weights, rounds=TUKEY_ROUNDS):
    """A weighted soft median per pixel: values n x ... x c, weights n x ... (0 = leave out)."""
    w0 = weights[..., None]
    present = w0 > 0
    v = np.where(present, values, np.nan)
    est = np.nanmedian(v, axis=0)
    est = np.nan_to_num(est)
    for _ in range(rounds):
        r = np.linalg.norm(values - est, axis=-1, keepdims=True)
        mad = np.nanmedian(np.where(present, r, np.nan), axis=0)
        scale = 1.4826 * np.nan_to_num(mad) + 1e-6
        u = r / (TUKEY_C * scale)
        wt = np.where(u < 1, (1 - u ** 2) ** 2, 0.0) * w0
        total = wt.sum(0)
        est = np.where(total > 1e-12, (wt * values).sum(0) / np.maximum(total, 1e-12), est)
    return est


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
            if lv < levels - 1:
                if lv < finest_band(e[3]):
                    wgt[:] = 0
                else:
                    energy = cv2.GaussianBlur((p[lv] ** 2).sum(2), (0, 0), ENERGY_BLUR)
                    wgt *= energy + 1e-6
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
            est = tukey(vals, Wn)
        # where nothing counts in this band (finer than every photo): no detail
        est = np.where((total > 1e-12)[..., None], est, 0 if lv < levels - 1 else vals.mean(0))
        out_levels.append(est.astype(np.float32))
        if n >= 3:
            med = np.nanmedian(np.where((W > 0)[..., None], vals, np.nan), axis=0)
            out_median.append(np.nan_to_num(med).astype(np.float32))
    result = np.clip(from_oklab(collapse(out_levels)), 0, 1)
    tmp = out_base + ".tmp.avif"
    cv2.imwrite(tmp, (result * 255).round().astype(np.uint8), [cv2.IMWRITE_AVIF_QUALITY, QUALITY])
    os.replace(tmp, out_base + ".avif")
    if out_median:
        med = np.clip(from_oklab(collapse(out_median)), 0, 1)
        cv2.imwrite(tmp, (med * 255).round().astype(np.uint8), [cv2.IMWRITE_AVIF_QUALITY, QUALITY])
        os.replace(tmp, out_base + "-median.avif")
    elif os.path.exists(out_base + "-median.avif"):
        os.remove(out_base + "-median.avif")
    return pid, {"keys": [k for k, _, _ in own], "pooled": [k for k, _, _ in pooled], "single": n == 1, "bands": counts}


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
        wanted |= {os.path.basename(base(p["id"])) + s for s in (".avif", "-median.avif", ".json")}
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
    figs = []
    for p in sorted(result["prints"], key=lambda p: -len(p["keys"])):
        b = straighten.file_name(p["id"])[:-5]
        if not os.path.exists(os.path.join(out_dir, b + ".avif")):
            continue
        desc = json.load(open(os.path.join(out_dir, b + ".json"))) if os.path.exists(os.path.join(out_dir, b + ".json")) else {}
        median = f'<img loading="lazy" src="{b}-median.avif" title="plain median">' if os.path.exists(os.path.join(out_dir, b + "-median.avif")) else ""
        figs.append(f'<figure><div class="pair"><img loading="lazy" src="{b}.avif" title="soft median">{median}</div>'
                    f'<figcaption><b>{html.escape(str(p["serial"] or p["release"] or "?"))}</b>: {len(desc.get("keys", []))} label photos'
                    f'{", " + str(len(desc.get("pooled", []))) + " pooled from nearly-same prints" if desc.get("pooled") else ""}'
                    f'{" (one photo: as it is)" if desc.get("single") else ""}<br>label photos per band, finest first: {desc.get("bands")}</figcaption></figure>')
    with open(os.path.join(out_dir, "index.html"), "w") as f:
        f.write(f"""<!doctype html><meta charset="utf-8"><title>restore</title>
<style>body{{font:14px system-ui;margin:16px;background:#333;color:#eee}} figure{{display:inline-block;margin:8px;vertical-align:top}} .pair img{{width:340px;margin-right:4px}} figcaption{{font-size:12px;max-width:700px}}</style>
<h1>restore</h1>
<p>{len(figs)} restored prints, the most label photos first. Left: the soft median (Tukey's biweight, weighted per band); right, where there are three or more label photos: the plain median, to compare.</p>
{"".join(figs)}""")


if __name__ == "__main__":
    main()
