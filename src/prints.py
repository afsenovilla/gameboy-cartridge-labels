# prints: the label photos of each family (solve) split into prints, and the pooling masks between nearly-same prints,
# into <generated>/prints/:
#   prints.json: {"prints": [{"id" (its smallest key), "keys", "release", "serial", "shape", "family"}],
#                 "poor_fits": [keys], "tile_mm": TILE_MM,
#                 "differences": {family: {"grid": [rows, columns], "tiles": [index...]}} (its print differences)}
#   <print>/<other print>.png: one pixel per tile, white where the two prints are alike (only for pairs sharing more
#     than the tiles most of their family's prints share, and at least MIN_SHARED of the label)
#   few-photos.json: [print ids] of prints with fewer than FEW label photos
# Comparing, in each family's ink coordinates (straighten's images): the label, 1 mm in from its edges, in TILE_MM
# tiles. Two label photos are alike at a tile: where both are textured (gray spread over TEXTURE), the lighting-evened
# gray (minus the local mean, over the local spread, 0.25 mm blur) correlates over CORRELATION; where flat, their
# colors (each label photo's evened per channel to the family's median) differ under COLOR_DIFF. Measured on the
# sample: pairs of one old name alike on 97 % of tiles at the median (textured 99 %, flat 93 %); different releases in
# one family 34 %.
# Per tile, the family's label photos group by being alike (connected): all alike, a shared area; one apart, a defect on
# that sticker; two or more groups of at least two, a print difference. Label photos are one print where they agree on
# every print difference (a defect doesn't count) and their releases (read-serials) don't differ. A print difference:
# a split on a tile textured in every member compared, recurring on MIN_DIFF_TILES tiles or more. A label photo alike
# with the others of its release on under POOR_SHARE of tiles (two or more others) is a poor fit: a print of its own.
# Done again when prints.json is older than this file, solve.json or serials.json.
# Usage: prints.py [--sample]
import argparse, html, itertools, json, os, sys
from collections import Counter
import cv2, numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photos, steps, straighten, shapes

TILE_MM = 2
TEXTURE = 6.0
CORRELATION = 0.5
COLOR_DIFF = 15.0
POOR_SHARE = 0.6
MIN_SHARED = 0.15
COMMON = 0.75   # tiles alike between this share of a family's print pairs are common (a frame), left out of pair images
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


def alike(va, vb, ca, cb):
    """Per tile, whether two label photos are alike there."""
    textured = (va[2] > TEXTURE) & (vb[2] > TEXTURE)
    za = va[0] - va[0].mean(2, keepdims=True)
    zb = vb[0] - vb[0].mean(2, keepdims=True)
    corr = (za * zb).sum(2) / np.sqrt((za ** 2).sum(2) * (zb ** 2).sum(2) + 1e-9)
    return np.where(textured, corr > CORRELATION, np.abs(ca - cb).mean(2) < COLOR_DIFF)


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


def split_family(keys, A, releases, textured):
    """A family's prints: [[member index...]], its poor fits (indices) and its print-difference tiles. A: n x n x
    tiles booleans (alike); textured: n x tiles."""
    n = len(keys)
    share = np.array([[A[i, j].mean() if i != j else 1.0 for j in range(n)] for i in range(n)])
    # a poor fit: alike with the others of its release on under POOR_SHARE of tiles (two or more others needed:
    # different releases of a family, a series sharing a layout, agree only in part)
    poor = set()
    for i in range(n):
        same = [j for j in range(n) if j != i and releases[i] and releases[j] == releases[i]]
        if len(same) >= 2 and np.median([share[i, j] for j in same]) < POOR_SHARE:
            poor.add(i)
    good = [i for i in range(n) if i not in poor]
    tiles = A.shape[2]
    # per tile, the groups among the good members; a print difference is a split into two or more groups of at least
    # two, on a tile textured in all of them, recurring on MIN_DIFF_TILES tiles or more (glare or an artefact two
    # photos share rarely covers several tiles the same way; a moved logo or text does)
    group = np.zeros((n, tiles), int) - 1
    splits = {}
    for t in range(tiles):
        edges = [(a, b) for a, b in itertools.combinations(good, 2) if A[a, b, t]]
        roots = components(n, edges)
        sizes = Counter(roots[i] for i in good)
        for i in good:
            group[i, t] = roots[i] if sizes[roots[i]] >= 2 else -1   # -1: a defect (alone) at this tile
        big = [r for r, c in sizes.items() if c >= 2]
        if len(big) >= 2 and all(textured[i, t] for i in good):
            split = frozenset(frozenset(i for i in good if roots[i] == r) for r in big)
            splits.setdefault(split, []).append(t)
    differs = np.zeros(tiles, bool)
    for split, ts in splits.items():
        if len(ts) >= MIN_DIFF_TILES:
            differs[ts] = True
    def compatible(a, b):
        if releases[a] and releases[b] and releases[a] != releases[b]:
            return False
        both = differs & (group[a] >= 0) & (group[b] >= 0)
        return bool(np.all(group[a][both] == group[b][both]))
    # merge into prints, most alike pairs first, only where every cross pair is compatible
    prints = [[i] for i in good]
    order = sorted(itertools.combinations(good, 2), key=lambda p: -share[p])
    where = {i: k for k, p in enumerate(prints) for i in p}
    for a, b in order:
        pa, pb = where[a], where[b]
        if pa == pb:
            continue
        if all(compatible(x, y) for x in prints[pa] for y in prints[pb]):
            prints[pa] += prints[pb]
            for i in prints[pb]:
                where[i] = pa
            prints[pb] = []
    return [p for p in prints if p] + [[i] for i in sorted(poor)], sorted(poor), differs


def pair_masks(groups, A):
    """{(p, q): tiles alike} for the pairs of a family's prints (groups: their member indices; A: n x n x tiles) worth
    a pair image: alike where most cross pairs are; kept where what they share beyond the family's common tiles (alike
    between COMMON of its print pairs: a frame) is at least MIN_SHARED of the label. Common tiles only mean something
    with three or more prints: with one pair every shared tile would be common, and nothing pooled."""
    masks = {}
    for p, q in itertools.combinations(range(len(groups)), 2):
        masks[(p, q)] = np.mean([A[i, j] for i in groups[p] for j in groups[q]], 0) > 0.5
    if not masks:
        return {}
    common = np.mean(list(masks.values()), 0) >= COMMON if len(groups) >= 3 else np.zeros_like(next(iter(masks.values())))
    return {pq: m for pq, m in masks.items() if (m & ~common).mean() >= MIN_SHARED}


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
        all_prints, poor_fits, pair_images, differences = [], [], {}, {}
        for fam, keys in sorted(families.items()):
            keys = sorted(keys)
            shape = solved[keys[0]]["shape"]
            releases = [serial.get(k, {}).get("release") for k in keys]
            if len(keys) == 1:
                all_prints.append({"keys": keys, "family": fam})
                continue
            views = [tile_views(os.path.join(gen, "straighten", straighten.file_name(k)), shape) for k in keys]
            ref = np.median(np.stack([v[1] for v in views]), 0)
            colors = [even_colors(v[1], ref) for v in views]
            n = len(keys)
            A = np.ones((n, n) + views[0][2].shape, bool)
            for i, j in itertools.combinations(range(n), 2):
                A[i, j] = A[j, i] = alike(views[i], views[j], colors[i], colors[j])
            A = A.reshape(n, n, -1)
            textured = np.stack([v[2].ravel() > TEXTURE for v in views])
            groups, poor, differs = split_family(keys, A, releases, textured)
            if differs.any():
                differences[fam] = {"grid": list(views[0][2].shape), "tiles": np.flatnonzero(differs).tolist()}
            poor_fits += [keys[i] for i in poor]
            fam_prints = [{"keys": [keys[i] for i in g], "family": fam, "_idx": g} for g in groups]
            # pooling masks between this family's prints: alike where most cross pairs are
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
        steps.write_json(out, {"prints": sorted(all_prints, key=lambda p: p["id"]), "poor_fits": sorted(poor_fits), "tile_mm": TILE_MM,
                               "differences": differences})
        steps.write_json(os.path.join(out_dir, "few-photos.json"), sorted(p["id"] for p in all_prints if len(p["keys"]) < FEW))
    result = json.load(open(out))
    page(out_dir, result, gen)
    print(f"{len(result['prints'])} prints of {sum(len(p['keys']) for p in result['prints'])} label photos; {len(result['poor_fits'])} poor fits; page: {os.path.join(out_dir, 'index.html')}")


def page(out_dir, result, gen):
    """index.html: per family of several label photos, its prints side by side, the tiles that split them outlined in
    red; for a family of several prints, a viewer stacking one label photo per print in the same place, flipped by a
    click or by itself (they share ink coordinates, so only real differences move)."""
    by_family = {}
    for p in result["prints"]:
        by_family.setdefault(p["family"], []).append(p)
    rel = os.path.relpath(os.path.join(gen, "straighten"), out_dir)
    poor = set(result["poor_fits"])
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
        figure = lambda k: f'<div class="ph"><img loading="lazy" src="{rel}/{straighten.file_name(k)}" class="{"poor" if k in poor else ""}">{overlay}</div>'
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
.ph{{position:relative;display:inline-block;margin:2px}} .ph img{{width:150px;display:block}} .ph svg, .stack svg{{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}} img.poor{{outline:3px solid #fa0}}
.viewer{{display:inline-block;vertical-align:top;margin:0 16px 12px 0;cursor:pointer}} .stack{{position:relative;width:420px}} .stack img{{width:420px}} .caption{{font-weight:bold}}</style>
<script>
function flip(v){{const imgs=v.querySelectorAll('.stack img');let i=[...imgs].findIndex(x=>x.style.display!='none');imgs[i].style.display='none';i=(i+1)%imgs.length;imgs[i].style.display='block';v.querySelector('.caption').textContent=imgs[i].dataset.label;}}
function auto(box){{const v=box.closest('.viewer');if(box.checked){{v._t=setInterval(()=>flip(v),700);}}else{{clearInterval(v._t);}}}}
</script>
<h1>prints</h1>
<p>{n} prints; families with more than one print: {multi}; poor fits: {len(poor)}. Tiles of {result["tile_mm"]} mm.</p>
{steps.legend([("#f33", "a tile that splits the family into prints (a square on every image of the family)"), ("#fa0", "a poor fit (outline around the image; a print of its own)")])}
<p>The large viewer stacks one label photo per print in the same place: click it, or tick "flip by itself", to switch between them. Families of one label photo left out.</p>
{"".join(blocks)}""")


if __name__ == "__main__":
    main()
