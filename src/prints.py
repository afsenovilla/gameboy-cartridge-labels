# prints: the label photos of each family (solve) split into prints, and the pooling masks between nearly-same prints,
# into <generated>/prints/:
#   prints.json: {"prints": [{"id" (its smallest key), "keys", "release", "serial", "shape", "family"}], "tile_mm": TILE_MM,
#                 "differences": {family: {"grid": [rows, columns], "tiles": [index...]}} (the tiles telling its prints apart)}
#   <print>/<other print>.png: one pixel per tile, white where the two prints match (for pairs matching on at least
#     MIN_SHARED of the label)
#   few-photos.json: [print ids] of prints with fewer than FEW label photos
# Comparing, in each family's ink coordinates (straighten's images): the label, 1 mm in from its edges, in TILE_MM
# tiles. Two label photos match at a tile: where both are textured (gray spread over TEXTURE), the lighting-evened
# gray (minus the local mean, over the local spread, 0.25 mm blur) correlates over CORRELATION; where both are flat,
# their colors (each label photo's evened per channel to the family's median) differ under COLOR_DIFF; textured in one
# and flat in the other, never. Different (conflicting) at a tile: textured in both and not correlating. Different
# prints: different on MIN_DIFF_TILES tiles or more. Only the pixels decide: serials and releases are only the prints'
# labels. Measured on the full set at 1 mm tiles (pairs within a family, by
# their serials read): 3 or more different tiles on 10 % of same-serial pairs (dirt, misfits: split, then pooled
# back), 86 % of one release's region variants (many of the rest misread serials of one print: IPN for JPN, a cut-off
# serial) and 95 % of different releases. At 2 mm tiles a region code hardly showed (one tile, often still correlating).
# Done again when prints.json is older than this file, solve.json or serials.json.
# Usage: prints.py [--sample]
import argparse, html, itertools, json, os, sys
from collections import Counter
import cv2, numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photos, steps, straighten, shapes

TILE_MM = 1
TEXTURE = 6.0
CORRELATION = 0.0
COLOR_DIFF = 15.0
MIN_SHARED = 0.15
FEW = 3
MIN_DIFF_TILES = 3


def tile_views(image_path, shape):
    """A straightened label photo's tiles: (lighting-evened gray per tile, flattened; mean color; gray spread)."""
    P, M = straighten.PX_PER_MM, straighten.MARGIN
    img = cv2.imread(image_path).astype(np.float32)
    lw, lh = shapes.LABEL_MM[shape]
    x0, y0, x1, y1 = int((M + 1) * P), int((M + 1) * P), int((M + lw - 1) * P), int((M + lh - 1) * P)
    g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (0, 0), 0.25 * P)
    mean = cv2.GaussianBlur(g, (0, 0), P)
    spread = np.sqrt(cv2.GaussianBlur((g - mean) ** 2, (0, 0), P)) + 2
    hp = ((g - mean) / spread)[y0:y1, x0:x1]
    col = cv2.GaussianBlur(img, (0, 0), 0.25 * P)[y0:y1, x0:x1]
    g = g[y0:y1, x0:x1]
    t = TILE_MM * P
    h, w = hp.shape[0] // t, hp.shape[1] // t
    cut = lambda a: a[:h * t, :w * t]
    return (cut(hp).reshape(h, t, w, t).transpose(0, 2, 1, 3).reshape(h, w, -1),
            cut(col).reshape(h, t, w, t, 3).mean((1, 3)), cut(g).reshape(h, t, w, t).std((1, 3)))


def even_colors(colors, ref):
    """Tile colors evened per channel to ref: a scale and offset, fitted on the best 80 %."""
    out = colors.copy()
    for c in range(3):
        x, y = colors[..., c].ravel(), ref[..., c].ravel()
        A = np.c_[x, np.ones_like(x)]
        coef = np.linalg.lstsq(A, y, rcond=None)[0]
        r = np.abs(A @ coef - y)
        ok = r <= np.percentile(r, 80)  # <=: with residuals all zero (one label photo, its own reference), < kept none
        coef = np.linalg.lstsq(A[ok], y[ok], rcond=None)[0]
        out[..., c] = colors[..., c] * coef[0] + coef[1]
    return out


def matching_and_conflicting_tiles(va, vb, ca, cb):
    """Per tile, two booleans for two label photos (their tile_views, and their tile colors evened):
    matching: textured in both with their lighting-evened gray correlating over CORRELATION, or flat in both with
      their evened colors differing under COLOR_DIFF. A tile textured in one and flat in the other never matches: the
      color test can't see small text on paper (a region variant's text was pooled into another print).
    conflicting: textured in both and not correlating (the outermost ring of tiles left out: the cut wanders up to
      about 1 mm past them). Textured in one only isn't conflicting: blur or glare in one photo does that."""
    textured = (va[2] > TEXTURE) & (vb[2] > TEXTURE)
    flat = (va[2] <= TEXTURE) & (vb[2] <= TEXTURE)
    za = va[0] - va[0].mean(2, keepdims=True)
    zb = vb[0] - vb[0].mean(2, keepdims=True)
    corr = (za * zb).sum(2) / np.sqrt((za ** 2).sum(2) * (zb ** 2).sum(2) + 1e-9)
    matching = (textured & (corr > CORRELATION)) | (flat & (np.abs(ca - cb).mean(2) < COLOR_DIFF))
    conflicting = textured & ~(corr > CORRELATION)
    conflicting[0, :] = conflicting[-1, :] = conflicting[:, 0] = conflicting[:, -1] = False
    return matching, conflicting


def components(n, edges):
    parent = list(range(n))
    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b in edges:
        parent[root(a)] = root(b)
    return [root(i) for i in range(n)]


def split_family(A, D):
    """A family's prints: [[member index...]], and the tiles that tell its prints apart. A: n x n x tiles booleans
    (matching); D: n x n x tiles booleans (conflicting: textured in both and not correlating). Two label photos are
    different prints where they differ on MIN_DIFF_TILES tiles or more (dirt or glare rarely does; other text does).
    Prints are merged, the pairs with the fewest differing tiles first, where most cross pairs aren't different."""
    n = A.shape[0]
    count = D.sum(2)
    same = count < MIN_DIFF_TILES
    prints = [[i] for i in range(n)]
    where = list(range(n))
    for a, b in sorted(itertools.combinations(range(n), 2), key=lambda p: (count[p], -A[p].mean())):
        pa, pb = where[a], where[b]
        if pa == pb or not same[a, b]:
            continue
        if np.mean([same[x, y] for x in prints[pa] for y in prints[pb]]) > 0.5:
            prints[pa] += prints[pb]
            for i in prints[pb]:
                where[i] = pa
            prints[pb] = []
    prints = [p for p in prints if p]
    differs = np.zeros(A.shape[2], bool)   # tiles where most cross pairs of some two prints differ
    for p, q in itertools.combinations(prints, 2):
        differs |= np.mean([D[i, j] for i in p for j in q], 0) > 0.5
    return prints, differs


def pair_masks(groups, A):
    """{(p, q): tiles matching} for the pairs of a family's prints (groups: their member indices; A: n x n x tiles) worth
    a pair image: matching where most cross pairs match, on at least MIN_SHARED of the label. (Tiles shared by most of a
    family's prints, a frame, were once left out: that dropped the region variants of one release, alike nearly
    everywhere, from each other's pooling.)"""
    masks = {}
    for p, q in itertools.combinations(range(len(groups)), 2):
        masks[(p, q)] = np.mean([A[i, j] for i in groups[p] for j in groups[q]], 0) > 0.5
    return {pq: m for pq, m in masks.items() if m.mean() >= MIN_SHARED}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true")
    args = ap.parse_args()
    gen = photos.generated(args.sample)
    solve_file = os.path.join(gen, "solve", "solve.json")
    serials_file = os.path.join(gen, "read-serials", "serials.json")
    for p in (solve_file, serials_file):
        if not os.path.exists(p):
            sys.exit(f"{p} missing: run make solve, straighten and read-serials first")
    out_dir = os.path.join(gen, "prints")
    out = os.path.join(out_dir, "prints.json")
    os.makedirs(out_dir, exist_ok=True)
    solved = json.load(open(solve_file))["label_photos"]
    serial = json.load(open(serials_file))
    if not os.path.exists(out) or os.path.getmtime(out) < max(os.path.getmtime(p) for p in (solve_file, serials_file, __file__)):
        families = {}
        for k, r in solved.items():
            families.setdefault(r["family"], []).append(k)
        all_prints, pair_images, differences = [], {}, {}
        for fam, keys in sorted(families.items()):
            keys = sorted(keys)
            shape = solved[keys[0]]["shape"]
            if len(keys) == 1:
                all_prints.append({"keys": keys, "family": fam})
                continue
            views = [tile_views(os.path.join(gen, "straighten", straighten.file_name(k)), shape) for k in keys]
            ref = np.median(np.stack([v[1] for v in views]), 0)
            colors = [even_colors(v[1], ref) for v in views]
            n = len(keys)
            A = np.ones((n, n) + views[0][2].shape, bool)
            D = np.zeros_like(A)
            for i, j in itertools.combinations(range(n), 2):
                a, d = matching_and_conflicting_tiles(views[i], views[j], colors[i], colors[j])
                A[i, j] = A[j, i] = a
                D[i, j] = D[j, i] = d
            groups, differs = split_family(A.reshape(n, n, -1), D.reshape(n, n, -1))
            A = A.reshape(n, n, -1)
            if differs.any():
                differences[fam] = {"grid": list(views[0][2].shape), "tiles": np.flatnonzero(differs).tolist()}
            fam_prints = [{"keys": [keys[i] for i in g], "family": fam, "_idx": g} for g in groups]
            # pooling masks between this family's prints: matching where most cross pairs match
            if len(fam_prints) > 1:
                grid = views[0][2].shape
                for (p, q), m in pair_masks([fp["_idx"] for fp in fam_prints], A).items():
                    pair_images[(id(fam_prints[p]), id(fam_prints[q]))] = (fam_prints[p], fam_prints[q], m.reshape(grid))
            all_prints += fam_prints
        for p in all_prints:
            p.pop("_idx", None)
            p["id"] = min(p["keys"])
            rel = Counter(serial.get(k, {}).get("release") for k in p["keys"] if serial.get(k, {}).get("release"))
            p["release"] = rel.most_common(1)[0][0] if rel else None
            ser = Counter(serial.get(k, {}).get("serial") for k in p["keys"] if serial.get(k, {}).get("serial"))
            p["serial"] = ser.most_common(1)[0][0] if ser else None
            p["shape"] = solved[p["keys"][0]]["shape"]
        # pair images
        for d in os.listdir(out_dir):
            if os.path.isdir(os.path.join(out_dir, d)):
                for f in os.listdir(os.path.join(out_dir, d)):
                    os.remove(os.path.join(out_dir, d, f))
                os.rmdir(os.path.join(out_dir, d))
        for p, q, m in pair_images.values():
            for a, b in ((p, q), (q, p)):
                d = os.path.join(out_dir, straighten.file_name(a["id"])[:-5])
                os.makedirs(d, exist_ok=True)
                cv2.imwrite(os.path.join(d, straighten.file_name(b["id"])[:-5] + ".png"), (m * 255).astype(np.uint8))
        steps.write_json(out, {"prints": sorted(all_prints, key=lambda p: p["id"]), "tile_mm": TILE_MM,
                               "differences": differences})
        steps.write_json(os.path.join(out_dir, "few-photos.json"), sorted(p["id"] for p in all_prints if len(p["keys"]) < FEW))
    result = json.load(open(out))
    page(out_dir, result, gen)
    print(f"{len(result['prints'])} prints of {sum(len(p['keys']) for p in result['prints'])} label photos; page: {os.path.join(out_dir, 'index.html')}")


def page(out_dir, result, gen):
    """index.html: per family of several label photos, its prints side by side, the tiles that split them outlined in
    red; for a family of several prints, a viewer stacking one label photo per print in the same place, flipped by a
    click or by itself (they share ink coordinates, so only real differences move)."""
    by_family = {}
    for p in result["prints"]:
        by_family.setdefault(p["family"], []).append(p)
    rel = os.path.relpath(os.path.join(gen, "straighten"), out_dir)
    P, M, T = straighten.PX_PER_MM, straighten.MARGIN, result["tile_mm"]
    blocks = []
    for fam, ps in sorted(by_family.items(), key=lambda kv: (-len(kv[1]), -sum(len(p["keys"]) for p in kv[1]))):
        if len(ps) < 2 and len(ps[0]["keys"]) < 2:
            continue
        shape = ps[0]["shape"]
        (w, h), _ = straighten.canvas(shape)
        d = result.get("differences", {}).get(fam)
        marks = ""
        if d:
            cols = d["grid"][1]
            for t in d["tiles"]:
                r, c = divmod(t, cols)
                marks += f'<rect x="{(M + 1 + c * T) * P}" y="{(M + 1 + r * T) * P}" width="{T * P}" height="{T * P}" fill="none" stroke="#f33" stroke-width="5"/>'
        overlay = f'<svg viewBox="0 0 {w} {h}">{marks}</svg>'
        figure = lambda k: f'<div class="ph"><img loading="lazy" src="{rel}/{straighten.file_name(k)}" >{overlay}</div>'
        row = "".join(f'<div class="print"><div>{html.escape(str(p["serial"] or p["release"] or "?"))} ({len(p["keys"])})</div>{"".join(figure(k) for k in p["keys"])}</div>' for p in ps)
        viewer = ""
        if len(ps) > 1:
            layers = "".join(f'<img src="{rel}/{straighten.file_name(p["keys"][0])}" data-label="{html.escape(str(p["serial"] or p["release"] or "?"))} ({len(p["keys"])} label photos)" style="display:{"block" if n == 0 else "none"}">' for n, p in enumerate(ps))
            viewer = (f'<div class="viewer" onclick="flip(this)"><div class="stack">{layers}{overlay}</div>'
                      f'<div class="caption">{html.escape(str(ps[0]["serial"] or ps[0]["release"] or "?"))} ({len(ps[0]["keys"])} label photos)</div>'
                      f'<label onclick="event.stopPropagation()"><input type="checkbox" onchange="auto(this)"> flip by itself</label></div>')
        blocks.append(f'<h3>Family {html.escape(fam[:10])}: {len(ps)} prints{", " + str(len(d["tiles"])) + " tiles differ" if d else ""}</h3>{viewer}{row}')
    n = len(result["prints"])
    multi = sum(1 for ps in by_family.values() if len(ps) > 1)
    with open(os.path.join(out_dir, "index.html"), "w") as f:
        f.write(f"""<!doctype html><meta charset="utf-8"><title>prints</title>
<style>body{{font:14px system-ui;margin:16px;background:#333;color:#eee}} .print{{display:inline-block;vertical-align:top;margin:4px 12px 12px 0;padding:4px;border:1px solid #666}}
.ph{{position:relative;display:inline-block;margin:2px}} .ph img{{width:150px;display:block}} .ph svg, .stack svg{{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}}
.viewer{{display:inline-block;vertical-align:top;margin:0 16px 12px 0;cursor:pointer}} .stack{{position:relative;width:420px}} .stack img{{width:420px}} .caption{{font-weight:bold}}</style>
<script>
function flip(v){{const imgs=v.querySelectorAll('.stack img');let i=[...imgs].findIndex(x=>x.style.display!='none');imgs[i].style.display='none';i=(i+1)%imgs.length;imgs[i].style.display='block';v.querySelector('.caption').textContent=imgs[i].dataset.label;}}
function auto(box){{const v=box.closest('.viewer');if(box.checked){{v._t=setInterval(()=>flip(v),700);}}else{{clearInterval(v._t);}}}}
</script>
<h1>prints</h1>
<p>{n} prints; families with more than one print: {multi}. Tiles of {result["tile_mm"]} mm.</p>
{steps.legend([("#f33", "a tile that tells the family's prints apart (a square on every image of the family)")])}
<p>The large viewer stacks one label photo per print in the same place: click it, or tick "flip by itself", to switch between them. Families of one label photo left out.</p>
{"".join(blocks)}""")


if __name__ == "__main__":
    main()
