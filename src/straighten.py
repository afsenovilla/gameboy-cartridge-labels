# straighten: every solved label photo drawn in ink coordinates (solve's photo_to_ink), at PX_PER_MM, the nominal
# label (its shape's canonical size) plus MARGIN mm on every side, uncropped (the crop is decided later, and
# restoration pools the print's overflow past the cut), into <generated>/straighten/<key>.avif (quality QUALITY).
# Where the photo has more pixels per mm than PX_PER_MM, the image is drawn at up to 3 times that and shrunk, so it
# isn't aliased.
# Beside each image, <key>.json: the sticker's cut edges found in it (cuts.find: {side: {position, turn, strength,
# found}}, ink mm), from the image as drawn.
# An image is drawn again when it's missing or older than solve.json or this file; its cut found again when that's
# missing or older than the image or cuts.py. Those of label photos no longer solved are removed.
# The page, <generated>/straighten/index.html: every image, the label's nominal rectangle, the recess and the cut
# found drawn on it, the fits with the largest leftover error first. <generated>/straighten/cuts.html: each side's middle
# CLOSE_MM close up (CLOSE_ZOOM times), the cut found, its INSET and the fitted cut drawn, the sides moved most first.
# Usage: straighten.py [--sample] [--workers N]
import argparse, html, json, os, sys
import cv2, numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photos, steps, shapes, cuts
MODELS = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "shape-models.json")))["shapes"]

PX_PER_MM = 20
MARGIN = 5.0
QUALITY = 90


def canvas(shape):
    """The image's size (w, h px) and the ink px -> ink mm transform."""
    lw, lh = shapes.LABEL_MM[shape]
    w, h = round((lw + 2 * MARGIN) * PX_PER_MM), round((lh + 2 * MARGIN) * PX_PER_MM)
    s = 1 / PX_PER_MM
    px_to_mm = np.array([[s, 0, -MARGIN + s / 2], [0, s, -MARGIN + s / 2], [0, 0, 1.0]])
    return (w, h), px_to_mm


def straightened(photo, photo_to_ink, shape):
    """The label photo in ink coordinates (BGR)."""
    (w, h), px_to_mm = canvas(shape)
    ink_to_photo = np.linalg.inv(np.float64(photo_to_ink))
    # photo px per ink px at the label's middle
    lw, lh = shapes.LABEL_MM[shape]
    c = cv2.perspectiveTransform(np.float64([[[lw / 2, lh / 2]], [[lw / 2 + 1, lh / 2]], [[lw / 2, lh / 2 + 1]]]), ink_to_photo).reshape(-1, 2)
    (ax, ay), (bx, by) = c[1] - c[0], c[2] - c[0]
    photo_per_mm = np.sqrt(abs(ax * by - ay * bx))
    ss = int(np.clip(np.ceil(photo_per_mm / PX_PER_MM), 1, 3))
    up = np.array([[1 / ss, 0, (1 / ss - 1) / 2], [0, 1 / ss, (1 / ss - 1) / 2], [0, 0, 1.0]])  # big px -> small px
    M = ink_to_photo @ px_to_mm @ up
    big = cv2.warpPerspective(photo, M, (w * ss, h * ss), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                              borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
    return cv2.resize(big, (w, h), interpolation=cv2.INTER_AREA) if ss > 1 else big


def recess_in_ink(r):
    """The cartridge's recess (from the plastic's fit) in ink mm: top left, top right, bottom right, bottom left."""
    x0, y0, x1, y1 = MODELS[r["shape"]]["recess"]
    return cv2.perspectiveTransform(np.float64([[[x0, y0]], [[x1, y0]], [[x1, y1]], [[x0, y1]]]),
                                    np.float64(r["photo_to_ink"]) @ np.float64(r["plastic_to_photo"])).reshape(-1, 2)


def find_cut(img, r):
    fitted = cuts.corners_in_ink(np.float64(r["photo_to_ink"]) @ np.float64(r["cut_to_photo"]), r["shape"])
    recess = recess_in_ink(r) if r.get("plastic_to_photo") is not None else None
    return cuts.find(img, r["shape"], fitted, recess, PX_PER_MM, MARGIN)


def do_one(job):
    key, path, r, out, draw = job
    if draw:
        photo = photos.load(path)
        if photo is None:
            return key
        img = straightened(photo, r["photo_to_ink"], r["shape"])
        tmp = out + ".tmp.avif"
        cv2.imwrite(tmp, img, [cv2.IMWRITE_AVIF_QUALITY, QUALITY])
        os.replace(tmp, out)
    img = cv2.imread(out)
    if img is not None:
        steps.write_json(cut_file(out), find_cut(img, r))
    return key


def file_name(key):
    return key.replace("@", "_").replace(",", "_") + ".avif"


def cut_file(image_path):
    return image_path[:-5] + ".json"


def load_cut(gen, key):
    """A label photo's cut found by straighten (cuts.find's), or None."""
    p = cut_file(os.path.join(gen, "straighten", file_name(key)))
    return json.load(open(p)) if os.path.exists(p) else None


def page(out_dir, solved):
    order = sorted(solved.items(), key=lambda kv: -(kv[1].get("error_mm") or 0))
    figs = []
    for key, r in order:
        (w, h), _ = canvas(r["shape"])
        m = MARGIN * PX_PER_MM
        lw, lh = shapes.LABEL_MM[r["shape"]]
        rect = f'<rect x="{m}" y="{m}" width="{lw * PX_PER_MM}" height="{lh * PX_PER_MM}" fill="none" stroke="#f0f" stroke-width="3"/>'
        # the recess, from the plastic's fit: plastic mm -> photo -> ink mm -> the image's px
        x0, y0, x1, y1 = MODELS[r["shape"]]["recess"]
        rec = cv2.perspectiveTransform(np.float64([[[x0, y0]], [[x1, y0]], [[x1, y1]], [[x0, y1]]]),
                                       np.float64(r["photo_to_ink"]) @ np.float64(r["plastic_to_photo"])).reshape(-1, 2)
        rec = (rec + MARGIN) * PX_PER_MM
        rect += f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in rec)}" fill="none" stroke="#ff0" stroke-width="3"/>'
        cut = load_cut(os.path.dirname(out_dir), key)
        if cut:
            q = (cuts.polygon(cut, r["shape"]) + MARGIN) * PX_PER_MM
            rect += f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in q)}" fill="none" stroke="#0ff" stroke-width="2"/>'
        figs.append(f'<figure><div class="ph"><img loading="lazy" src="{file_name(key)}"><svg viewBox="0 0 {w} {h}">{rect}</svg></div>'
                    f'<figcaption><code>{html.escape(key[:14])}</code> {html.escape(r["start"].split(" (")[0])}, error {r.get("error_mm")} mm</figcaption></figure>')
    with open(os.path.join(out_dir, "index.html"), "w") as f:
        f.write(f"""<!doctype html><meta charset="utf-8"><title>straighten</title>
<style>body{{font:14px system-ui;margin:16px;background:#333;color:#eee}} figure{{display:inline-block;margin:6px;vertical-align:top;width:300px}}
.ph{{position:relative;display:inline-block}} .ph img{{width:300px;display:block}} .ph svg{{position:absolute;inset:0;width:100%;height:100%}} figcaption{{font-size:11px}}</style>
<h1>straighten</h1>
<p>{len(solved)} label photos in ink coordinates, {PX_PER_MM} px/mm, {MARGIN:g} mm around the nominal label. Largest leftover error first.</p>
{steps.legend([("#f0f", "the label's canonical size at its family's median cut"), ("#ff0", "this cartridge's recess, from the plastic's fit"), ("#0ff", "the sticker's cut found")])}
{"".join(figs)}""")


CLOSE_MM = 6.0
CLOSE_OUT, CLOSE_IN = 1.5, 1.0
CLOSE_ZOOM = 3


def cuts_page(out_dir, solved):
    P, Z = PX_PER_MM, CLOSE_ZOOM
    tiles = []
    for key, r in solved.items():
        cut = load_cut(os.path.dirname(out_dir), key)
        if not cut:
            continue
        (w, h), _ = canvas(r["shape"])
        lw, lh = shapes.LABEL_MM[r["shape"]]
        fitted = cuts.corners_in_ink(np.float64(r["photo_to_ink"]) @ np.float64(r["cut_to_photo"]), r["shape"])
        for side in cuts.SIDES:
            c = cut[side]
            inward = 1 if side in ("top", "left") else -1
            moved = (c["position"] - cuts.side_position(fitted, side)) * inward
            vertical = side in ("left", "right")
            along = (lh if vertical else lw) / 2
            # the tile in ink mm: along [along - CLOSE_MM / 2, + CLOSE_MM / 2], across CLOSE_OUT outside to CLOSE_IN inside the cut
            a0 = along - CLOSE_MM / 2
            c0 = c["position"] - CLOSE_OUT if inward == 1 else c["position"] - CLOSE_IN
            span = CLOSE_OUT + CLOSE_IN
            tw, th = (span, CLOSE_MM) if vertical else (CLOSE_MM, span)
            x0, y0 = (c0, a0) if vertical else (a0, c0)
            to_px = lambda mm_x, mm_y: ((mm_x - x0) * P * Z, (mm_y - y0) * P * Z)
            lines = []
            t = np.tan(np.radians(c["turn"]))
            for off, colour, dash in ((0, "#0ff", ""), (cuts.INSET, "#0ff", ' stroke-dasharray="4 4"')):
                p0 = c["position"] + inward * off
                ends = [(a, p0 + t * (a - along)) for a in (a0, a0 + CLOSE_MM)]
                pts = [to_px(q, a) if vertical else to_px(a, q) for a, q in ends]
                lines.append(f'<line x1="{pts[0][0]:.1f}" y1="{pts[0][1]:.1f}" x2="{pts[1][0]:.1f}" y2="{pts[1][1]:.1f}" stroke="{colour}" stroke-width="1"{dash}/>')
            f0 = cuts.side_position(fitted, side)
            pts = [to_px(f0, a) if vertical else to_px(a, f0) for a in (a0, a0 + CLOSE_MM)]
            lines.append(f'<line x1="{pts[0][0]:.1f}" y1="{pts[0][1]:.1f}" x2="{pts[1][0]:.1f}" y2="{pts[1][1]:.1f}" stroke="#f0f" stroke-width="1" stroke-dasharray="2 6"/>')
            W, H = tw * P * Z, th * P * Z
            img = (f'<div class="tile" style="width:{W:.0f}px;height:{H:.0f}px;background:url({file_name(key)}) '
                   f'{-(x0 + MARGIN) * P * Z:.1f}px {-(y0 + MARGIN) * P * Z:.1f}px / {w * Z}px {h * Z}px">'
                   f'<svg width="{W:.0f}" height="{H:.0f}">{"".join(lines)}</svg></div>')
            label = f'<code>{html.escape(key[:10])}</code> {side}: {"moved " + format(moved, "+.2f") + " mm" if c["found"] else "not found: the fitted cut"}'
            tiles.append((-(abs(moved) if c["found"] else 9), f'<figure>{img}<figcaption>{label}</figcaption></figure>'))
    tiles.sort(key=lambda t: t[0])
    with open(os.path.join(out_dir, "cuts.html"), "w") as f:
        f.write(f"""<!doctype html><meta charset="utf-8"><title>cuts</title>
<style>body{{font:14px system-ui;margin:16px;background:#333;color:#eee}} figure{{display:inline-block;margin:6px;vertical-align:top}}
.tile{{position:relative;image-rendering:pixelated;background-repeat:no-repeat}} .tile svg{{position:absolute;inset:0}} figcaption{{font-size:11px}}</style>
<h1>cuts</h1>
<p>{len(tiles)} sides of {len(solved)} label photos: each side's middle {CLOSE_MM:g} mm, {CLOSE_ZOOM}x ({PX_PER_MM * CLOSE_ZOOM} screen px per mm). Not found first, then the sides moved most from the fitted cut.</p>
{steps.legend([("#0ff", "the cut found (solid) and the crop's edge, {} mm inside it (dashed)".format(cuts.INSET)), ("#f0f", "the fitted cut (solve's, dotted)")])}
{"".join(t[1] for t in tiles)}""")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    chosen = photos.chosen(args.sample)
    gen = photos.generated(args.sample)
    solve_file = os.path.join(gen, "solve", "solve.json")
    if not os.path.exists(solve_file):
        sys.exit("no solve.json: run make solve first")
    solved = json.load(open(solve_file))["label_photos"]
    out_dir = os.path.join(gen, "straighten")
    os.makedirs(out_dir, exist_ok=True)
    wanted = {file_name(k) for k in solved} | {file_name(k)[:-5] + ".json" for k in solved}
    for f in os.listdir(out_dir):
        if (f.endswith(".avif") or f.endswith(".json")) and f not in wanted:
            os.remove(os.path.join(out_dir, f))
    newest = max(os.path.getmtime(solve_file), os.path.getmtime(__file__))
    cuts_code = os.path.getmtime(cuts.__file__)
    out = lambda k: os.path.join(out_dir, file_name(k))
    stale = lambda p, t: not os.path.exists(p) or os.path.getmtime(p) < t
    jobs = []
    for k, r in solved.items():
        if r["photo"] not in chosen:
            continue
        draw = stale(out(k), newest)
        if draw or stale(cut_file(out(k)), max(cuts_code, os.path.getmtime(out(k)))):
            jobs.append((k, chosen[r["photo"]], r, out(k), draw))
    steps.run(do_one, jobs, args.workers, what="straightened or cut found")
    page(out_dir, solved)
    cuts_page(out_dir, solved)
    print(f"page: {os.path.join(out_dir, 'index.html')}")
    print(f"page: {os.path.join(out_dir, 'cuts.html')}")


if __name__ == "__main__":
    main()
