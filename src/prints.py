# prints: the label photos of each family (solve) split into prints, into <generated>/prints/:
#   prints.json: {"prints": [{"id" (its persistent id: src/print_ids.py, print-ids.json), "keys", "release", "serial", "shape", "family"}], "tile_mm": TILE_MM,
#                 "differences": {family: {"grid": [rows, columns], "tiles": [index...]}} (the tiles telling its prints apart)}
#   few-photos.json: [print ids] of prints with fewer than FEW label photos
# Comparing, in each family's ink coordinates (straighten's images): the label, 1 mm in from its edges, in TILE_MM
# tiles (the outermost millimetre left out: the cut wanders about 1 mm). Two label photos differ at a tile where both
# are textured (gray spread over TEXTURE) and their lighting-evened gray (minus the local mean, over the local spread,
# 0.25 mm blur) doesn't correlate over CORRELATION. Only that counts as evidence of a print difference: a tile textured
# in one photo only is blur, glare or dirt as often as other text. Different prints: different on MIN_DIFF_TILES tiles
# or more. Only the pixels decide: serials and releases are only the prints' labels. (Where another print's label
# photos may be used in a restored print is restore's own comparison, not this one.) Measured on the full set at 1 mm
# tiles (pairs within a family, by their serials read): 3 or more different tiles on 10 % of same-serial pairs (dirt,
# misfits: split, then pooled back), 86 % of one release's region variants (many of the rest misread serials of one
# print: IPN for JPN, a cut-off serial) and 95 % of different releases. At 2 mm tiles a region code hardly showed (one tile, often still correlating).
#   pairs.npz: the pair cache (below)
#   id-changes.json: this run's id changes ([{"kind": new, kept, split, merged, renamed or gone, "id", ...}]), on the page
# The ids are kept between runs in print-ids.json (the repo root, committed; with --sample in <generated>/prints/).
# Done again when prints.json is older than this file, solve.json or serials.json.
# Usage: prints.py [--sample]
import argparse, html, itertools, json, os, sys
from collections import Counter
import cv2, numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photos, steps, straighten, shapes, print_ids

TILE_MM = 1
TEXTURE = 6.0
CORRELATION = 0.0
FEW = 3
MIN_DIFF_TILES = 3


def tile_views(image_path, shape):
    """A straightened label photo's tiles: (lighting-evened gray per tile, flattened; gray spread per tile)."""
    P, M = straighten.PX_PER_MM, straighten.MARGIN
    img = cv2.imread(image_path).astype(np.float32)
    lw, lh = shapes.LABEL_MM[shape]
    x0, y0, x1, y1 = int((M + 1) * P), int((M + 1) * P), int((M + lw - 1) * P), int((M + lh - 1) * P)
    g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (0, 0), 0.25 * P)
    mean = cv2.GaussianBlur(g, (0, 0), P)
    spread = np.sqrt(cv2.GaussianBlur((g - mean) ** 2, (0, 0), P)) + 2
    hp = ((g - mean) / spread)[y0:y1, x0:x1]
    g = g[y0:y1, x0:x1]
    t = TILE_MM * P
    h, w = hp.shape[0] // t, hp.shape[1] // t
    cut = lambda a: a[:h * t, :w * t]
    return (cut(hp).reshape(h, t, w, t).transpose(0, 2, 1, 3).reshape(h, w, -1),
            cut(g).reshape(h, t, w, t).std((1, 3)))


def tiles_textured_in_both_and_not_correlating(va, vb):
    """Per tile, whether two label photos (their tile_views) show different detail there: textured in both (gray
    spread over TEXTURE) and their lighting-evened gray not correlating over CORRELATION. The outermost ring of tiles
    left out: the cut wanders up to about 1 mm past them."""
    textured = (va[1] > TEXTURE) & (vb[1] > TEXTURE)
    za = va[0] - va[0].mean(2, keepdims=True)
    zb = vb[0] - vb[0].mean(2, keepdims=True)
    corr = (za * zb).sum(2) / np.sqrt((za ** 2).sum(2) * (zb ** 2).sum(2) + 1e-9)
    differing = textured & ~(corr > CORRELATION)
    differing[0, :] = differing[-1, :] = differing[:, 0] = differing[:, -1] = False
    return differing


# The pair cache (the user, 2026-11-13): a pair's differing tiles depend only on the two straightened images, the shape
# and the comparison (COMPARISON's functions and settings), so each pair's result is kept in <generated>/prints/pairs.npz,
# named by both keys and each image's fingerprint (straighten writes an image only when it's drawn again: its file's
# size and modification time), all of it dropped when the comparison's fingerprint changes. A run compares only the
# pairs it hasn't seen; pairs no longer in a family are dropped. Saved every SAVE_EVERY families that compared anything.
SAVE_EVERY = 200


def comparison_version():
    """A fingerprint of what a pair's result depends on but its images."""
    import hashlib, inspect
    h = hashlib.sha1(inspect.getsource(tile_views).encode() + inspect.getsource(tiles_textured_in_both_and_not_correlating).encode())
    h.update(repr((TILE_MM, TEXTURE, CORRELATION, straighten.PX_PER_MM, straighten.MARGIN, shapes.LABEL_MM)).encode())
    return h.hexdigest()[:16]


def image_fingerprint(path):
    st = os.stat(path)
    return f"{st.st_size}:{st.st_mtime_ns}"


def load_pairs(path, version):
    """name -> differing tiles (bool array), from the cache, if it's of this comparison."""
    if not os.path.exists(path):
        return {}
    z = np.load(path)
    if str(z["version"]) != version:
        return {}
    out = {}
    for name, (h, w), a, b in zip(z["names"], z["grids"], z["starts"][:-1], z["starts"][1:]):
        out[str(name)] = np.unpackbits(z["bits"][a:b])[:h * w].astype(bool).reshape(h, w)
    return out


def save_pairs(path, version, pairs):
    names = sorted(pairs)
    packed = [np.packbits(pairs[n].ravel()) for n in names]
    starts = np.concatenate([[0], np.cumsum([len(b) for b in packed])]).astype(np.int64)
    steps.write_npz(path, version=np.array(version), names=np.array(names, dtype="U200"),
                    grids=np.array([pairs[n].shape for n in names], np.int32).reshape(-1, 2),
                    starts=starts, bits=np.concatenate(packed) if packed else np.zeros(0, np.uint8))


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


def split_family(D):
    """A family's prints: [[member index...]], and the tiles that tell its prints apart. D: n x n x tiles booleans
    (tiles_textured_in_both_and_not_correlating). Two label photos are different prints where they differ on
    MIN_DIFF_TILES tiles or more (dirt or glare rarely does; other text does). Prints are merged, the pairs with the
    fewest differing tiles first, where most cross pairs aren't different."""
    n = D.shape[0]
    count = D.sum(2)
    same = count < MIN_DIFF_TILES
    prints = [[i] for i in range(n)]
    where = list(range(n))
    for a, b in sorted(itertools.combinations(range(n), 2), key=lambda p: count[p]):
        pa, pb = where[a], where[b]
        if pa == pb or not same[a, b]:
            continue
        if np.mean([same[x, y] for x in prints[pa] for y in prints[pb]]) > 0.5:
            prints[pa] += prints[pb]
            for i in prints[pb]:
                where[i] = pa
            prints[pb] = []
    prints = [p for p in prints if p]
    differs = np.zeros(D.shape[2], bool)   # tiles where most cross pairs of some two prints differ
    for p, q in itertools.combinations(prints, 2):
        differs |= np.mean([D[i, j] for i in p for j in q], 0) > 0.5
    return prints, differs


def keep_ids(all_prints, ids_file, gen):
    """Each print's persistent id (print_ids), the registry in ids_file updated; this run's changes."""
    registry = print_ids.load(ids_file)
    found = json.load(open(os.path.join(gen, "find", "label-photos.json")))["label_photos"]
    outlines = {lp["key"]: lp["outline"] for lp in found}
    new_keys = {k for p in all_prints for k in p["keys"]}
    of_photo = {}
    for k in new_keys:
        of_photo.setdefault(k.split("@")[0], []).append(k)
    old_keys = {k for e in registry["prints"].values() for k in e["keys"]}
    sizes = {}
    for s in {k.split("@")[0] for k in old_keys - new_keys}:
        f = os.path.join(gen, "read-text", s + ".json")
        if os.path.exists(f):
            sizes[s] = json.load(open(f))["size"]
    key_map = {k: print_ids.same_label_photo(k, of_photo.get(k.split("@")[0], []), outlines, sizes) for k in old_keys}
    registry, changes = print_ids.assign(all_prints, registry, key_map)
    print_ids.save(registry, ids_file)
    counts = Counter(c["kind"] for c in changes)
    print("print ids: " + ", ".join(f"{n} {kind}" for kind, n in sorted(counts.items())), flush=True)
    return changes


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
        all_prints, differences = [], {}
        several = sum(1 for keys in families.values() if len(keys) > 1)
        pairs_file, version = os.path.join(out_dir, "pairs.npz"), comparison_version()
        cached = load_pairs(pairs_file, version)
        print(f"{len(families)} families, {several} of several label photos to compare; {len(cached)} pairs cached", flush=True)
        pairs, compared, unsaved, done = {}, 0, 0, 0
        for fam, keys in sorted(families.items()):
            keys = sorted(keys)
            shape = solved[keys[0]]["shape"]
            if len(keys) == 1:
                all_prints.append({"keys": keys, "family": fam})
                continue
            done += 1
            if done % 50 == 0 or done == several:
                print(f"compared {done} of {several} families ({len(keys)} label photos in this one)", flush=True)
            paths = [os.path.join(gen, "straighten", straighten.file_name(k)) for k in keys]
            fps = [image_fingerprint(f) for f in paths]
            views = {}
            view = lambda i: views[i] if i in views else views.setdefault(i, tile_views(paths[i], shape))
            n, found = len(keys), {}
            for i, j in itertools.combinations(range(n), 2):
                name = f"{keys[i]}|{keys[j]}|{fps[i]}|{fps[j]}"
                if name not in cached:
                    cached[name] = tiles_textured_in_both_and_not_correlating(view(i), view(j))
                    compared += 1
                    unsaved += 1
                found[i, j] = pairs[name] = cached[name]
            grid = next(iter(found.values())).shape
            D = np.zeros((n, n) + grid, bool)
            for (i, j), m in found.items():
                D[i, j] = D[j, i] = m
            groups, differs = split_family(D.reshape(n, n, -1))
            if differs.any():
                differences[fam] = {"grid": list(grid), "tiles": np.flatnonzero(differs).tolist()}
            if unsaved and done % SAVE_EVERY == 0:
                save_pairs(pairs_file, version, cached)
                unsaved = 0
            all_prints += [{"keys": [keys[i] for i in g], "family": fam} for g in groups]
        save_pairs(pairs_file, version, pairs)  # this run's pairs only: those no longer in a family dropped
        print(f"{compared} pairs compared, {len(pairs) - compared} from the cache", flush=True)
        for p in all_prints:
            rel = Counter(serial.get(k, {}).get("release") for k in p["keys"] if serial.get(k, {}).get("release"))
            p["release"] = rel.most_common(1)[0][0] if rel else None
            ser = Counter(serial.get(k, {}).get("serial") for k in p["keys"] if serial.get(k, {}).get("serial"))
            p["serial"] = ser.most_common(1)[0][0] if ser else None
            p["shape"] = solved[p["keys"][0]]["shape"]
        ids_file = print_ids.IDS_FILE if not args.sample else os.path.join(out_dir, print_ids.IDS_FILE)
        changes = keep_ids(all_prints, ids_file, gen)
        for d in os.listdir(out_dir):  # pair images (pooling masks) of earlier versions
            if os.path.isdir(os.path.join(out_dir, d)):
                for f in os.listdir(os.path.join(out_dir, d)):
                    os.remove(os.path.join(out_dir, d, f))
                os.rmdir(os.path.join(out_dir, d))
        steps.write_json(out, {"prints": sorted(all_prints, key=lambda p: p["id"]), "tile_mm": TILE_MM,
                               "differences": differences})
        steps.write_json(os.path.join(out_dir, "few-photos.json"), sorted(p["id"] for p in all_prints if len(p["keys"]) < FEW))
        steps.write_json(os.path.join(out_dir, "id-changes.json"), changes)
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
    changes_file = os.path.join(out_dir, "id-changes.json")
    changes = json.load(open(changes_file)) if os.path.exists(changes_file) else []
    counts = Counter(c["kind"] for c in changes)
    words = {"split": lambda c: f'{c["id"]} split from {c["from"]}', "merged": lambda c: f'{c["id"]} merged into {c["into"]}',
             "renamed": lambda c: f'{c["from"]} renamed {c["id"]}', "gone": lambda c: f'{c["id"]}: no label photo left'}
    listed = "".join(f"<li>{html.escape(words[c['kind']](c))}</li>" for c in changes if c["kind"] in words)
    ids = (f'<p>Print ids this run: {", ".join(f"{v} {k}" for k, v in sorted(counts.items()))}.</p>'
           + (f"<ul>{listed}</ul>" if listed else "")) if changes else ""
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
{ids}
{steps.legend([("#f33", "a tile that tells the family's prints apart (a square on every image of the family)")])}
<p>The large viewer stacks one label photo per print in the same place: click it, or tick "flip by itself", to switch between them. Families of one label photo left out.</p>
{"".join(blocks)}""")


if __name__ == "__main__":
    main()
