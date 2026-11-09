# straighten: every solved label photo drawn in ink coordinates (solve's photo_to_ink), at PX_PER_MM, the nominal
# label (its shape's canonical size) plus MARGIN mm on every side, uncropped (the crop is decided later, and
# restoration pools the print's overflow past the cut), into <generated>/straighten/<key>.avif (quality QUALITY).
# Where the photo has more pixels per mm than PX_PER_MM, the image is drawn at up to 3 times that and shrunk, so it
# isn't aliased.
# An image is drawn again when it's missing or older than solve.json or this file; those of label photos no longer
# solved are removed.
# The page, <generated>/straighten/index.html: every image, the label's nominal rectangle drawn on it, the fits with
# the largest leftover error first.
# Usage: straighten.py [--sample] [--workers N]
import argparse, html, json, os, sys
import cv2, numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photos, steps, shapes
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


def do_one(job):
    key, path, photo_to_ink, shape, out = job
    photo = photos.load(path)
    if photo is None:
        return key
    img = straightened(photo, photo_to_ink, shape)
    tmp = out + ".tmp.avif"
    cv2.imwrite(tmp, img, [cv2.IMWRITE_AVIF_QUALITY, QUALITY])
    os.replace(tmp, out)
    return key


def file_name(key):
    return key.replace("@", "_").replace(",", "_") + ".avif"


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
        figs.append(f'<figure><div class="ph"><img loading="lazy" src="{file_name(key)}"><svg viewBox="0 0 {w} {h}">{rect}</svg></div>'
                    f'<figcaption><code>{html.escape(key[:14])}</code> {html.escape(r["start"].split(" (")[0])}, error {r.get("error_mm")} mm</figcaption></figure>')
    with open(os.path.join(out_dir, "index.html"), "w") as f:
        f.write(f"""<!doctype html><meta charset="utf-8"><title>straighten</title>
<style>body{{font:14px system-ui;margin:16px;background:#333;color:#eee}} figure{{display:inline-block;margin:6px;vertical-align:top;width:300px}}
.ph{{position:relative;display:inline-block}} .ph img{{width:300px;display:block}} .ph svg{{position:absolute;inset:0;width:100%;height:100%}} figcaption{{font-size:11px}}</style>
<h1>straighten</h1>
<p>{len(solved)} label photos in ink coordinates, {PX_PER_MM} px/mm, {MARGIN:g} mm around the nominal label. Largest leftover error first.</p>
{steps.legend([("#f0f", "the label's canonical size at its family's median cut"), ("#ff0", "this cartridge's recess, from the plastic's fit")])}
{"".join(figs)}""")


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
    wanted = {file_name(k) for k in solved}
    for f in os.listdir(out_dir):
        if f.endswith(".avif") and f not in wanted:
            os.remove(os.path.join(out_dir, f))
    newest = max(os.path.getmtime(solve_file), os.path.getmtime(__file__))
    out = lambda k: os.path.join(out_dir, file_name(k))
    jobs = [(k, chosen[r["photo"]], r["photo_to_ink"], r["shape"], out(k)) for k, r in solved.items()
            if r["photo"] in chosen and (not os.path.exists(out(k)) or os.path.getmtime(out(k)) < newest)]
    steps.run(do_one, jobs, args.workers, what="straightened")
    page(out_dir, solved)
    print(f"page: {os.path.join(out_dir, 'index.html')}")


if __name__ == "__main__":
    main()
