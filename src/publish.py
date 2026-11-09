# publish: the outputs collected into <generated>/publish/:
#   prints/<print>.avif: each restored print, restore's image as it is (paper white where found, else median colours)
#   label-photos/<key>.avif: each label photo straightened, cut from its straightened image to its print's crop
#     (restore's, its family's: the same as the print's): whole pixels, no resampling. Poor fits (solve's "a poor" fallbacks) get no
#     image, as restore leaves them out; they're listed in index.json with poor_fit true.
#   index.json: {"prints": {id: {serial, release, shape, image, paper, label_photos}}, "label_photos": {key: {print,
#     serial, source, page_url, image_url, image, poor_fit}}}. Ids and keys hold within a run only.
#   missing.json, unknown-serials.json (read-serials), few-photos.json (prints): the lists, copied as they are.
#   index.html: the counts, and every print with its label photos.
# The source and URLs come from photo-sources.json (by SHA-1): for output only, never read by a detection step.
# An image is made again when it's missing or older than what it's made from or this file; files of prints and label
# photos no longer there are removed.
# Usage: publish.py [--sample]
import argparse, html, json, os, shutil, sys
import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photos, steps, shapes, straighten

SOURCES = "photo-sources.json"
QUALITY = straighten.QUALITY
LISTS = [("read-serials", "missing.json"), ("read-serials", "unknown-serials.json"), ("prints", "few-photos.json")]


def crop_box(shape, crop=None):
    """The crop in a straightened image: x, y, w, h in whole pixels (restore's crop, else the canonical label)."""
    if crop:
        return crop["x"], crop["y"], crop["w"], crop["h"]
    lw, lh = shapes.LABEL_MM[shape]
    m = round(straighten.MARGIN * straighten.PX_PER_MM)
    return m, m, round(lw * straighten.PX_PER_MM), round(lh * straighten.PX_PER_MM)


def cut(img, shape, crop=None):
    x, y, w, h = crop_box(shape, crop)
    return img[y:y + h, x:x + w]


def sources(path=SOURCES):
    """SHA-1 -> {source, page_url, image_url}, from photo-sources.json (src/add_photos.py)."""
    return {k: {"source": e.get("source"), "page_url": e.get("page_url"), "image_url": e.get("image_url")}
            for k, e in json.load(open(path)).items()}


def poor_fits(solved):
    return {k for k, r in solved.items() if (r.get("fallback") or "").startswith("a poor")}


def newer(out, *ins):
    return os.path.exists(out) and all(os.path.getmtime(out) >= os.path.getmtime(i) for i in ins)


def crop_one(job):
    src, out, shape, crop, _ = job
    img = cv2.imread(src)
    tmp = out + ".tmp.avif"
    cv2.imwrite(tmp, cut(img, shape, crop), [cv2.IMWRITE_AVIF_QUALITY, QUALITY])
    os.replace(tmp, out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    gen = photos.generated(args.sample)
    need = [os.path.join(gen, "prints", "prints.json"), os.path.join(gen, "solve", "solve.json"),
            os.path.join(gen, "read-serials", "serials.json"), os.path.join(gen, "restore", "index.html")]
    for f in need:
        if not os.path.exists(f):
            sys.exit(f"no {f}: run the steps before publish")
    prints = json.load(open(need[0]))
    solved = json.load(open(need[1]))["label_photos"]
    serials = json.load(open(need[2]))
    src = sources()
    poor = poor_fits(solved)
    out_dir = os.path.join(gen, "publish")
    for d in ("prints", "label-photos"):
        os.makedirs(os.path.join(out_dir, d), exist_ok=True)

    index = {"prints": {}, "label_photos": {}}
    copies, crops = [], []
    for p in prints["prints"]:
        name = straighten.file_name(p["id"])
        restored = os.path.join(gen, "restore", name)
        desc_file = restored[:-5] + ".json"
        desc = json.load(open(desc_file)) if os.path.exists(desc_file) else {}
        image = None
        if os.path.exists(restored):
            image = "prints/" + name
            copies.append((restored, os.path.join(out_dir, image)))
        index["prints"][p["id"]] = {"serial": p["serial"], "release": p["release"], "shape": p["shape"], "image": image,
                                    "paper": desc.get("paper") is not None if desc else None, "label_photos": p["keys"]}
        for k in p["keys"]:
            sha1 = k.split("@")[0]
            s = src.get(sha1, {})
            img = None
            straightened = os.path.join(gen, "straighten", straighten.file_name(k))
            if k not in poor and os.path.exists(straightened):
                img = "label-photos/" + straighten.file_name(k)
                crops.append((straightened, os.path.join(out_dir, img), p["shape"], desc.get("crop"), desc_file))
            index["label_photos"][k] = {"print": p["id"], "serial": (serials.get(k) or {}).get("serial"),
                                        "source": s.get("source"), "page_url": s.get("page_url"),
                                        "image_url": s.get("image_url"), "image": img, "poor_fit": k in poor}

    for d, files in (("prints", copies), ("label-photos", crops)):
        wanted = {os.path.basename(f[1]) for f in files}
        for f in os.listdir(os.path.join(out_dir, d)):
            if f not in wanted:
                os.remove(os.path.join(out_dir, d, f))
    for a, b in copies:
        if not newer(b, a):
            shutil.copyfile(a, b + ".tmp")
            os.replace(b + ".tmp", b)
    steps.run(crop_one, [c for c in crops if not newer(c[1], c[0], __file__, *([c[4]] if os.path.exists(c[4]) else []))],
              args.workers, what="cut")
    for step, f in LISTS:
        if os.path.exists(os.path.join(gen, step, f)):
            shutil.copyfile(os.path.join(gen, step, f), os.path.join(out_dir, f))
    steps.write_json(os.path.join(out_dir, "index.json"), index)
    page(out_dir, index)
    print(f"{len(copies)} prints, {len(crops)} label photos ({len(poor & set(index['label_photos']))} poor fits without image)")
    print(f"page: {os.path.join(out_dir, 'index.html')}")


def page(out_dir, index):
    lists = {f: json.load(open(os.path.join(out_dir, f))) for _, f in LISTS if os.path.exists(os.path.join(out_dir, f))}
    lp = index["label_photos"]
    with_url = sum(1 for r in lp.values() if r["page_url"] or r["image_url"])
    figs = []
    for pid, p in sorted(index["prints"].items(), key=lambda kv: -len(kv[1]["label_photos"])):
        if not p["image"]:
            continue
        thumbs = "".join(
            f'<a href="{html.escape(lp[k]["page_url"] or lp[k]["image_url"] or "")}" title="{html.escape(lp[k]["source"] or "")}">'
            f'<img loading="lazy" class="lp" src="{lp[k]["image"]}"></a>' if lp[k]["image"] else
            '<span class="poor">poor fit</span>' for k in p["label_photos"])
        figs.append(f'<figure><img loading="lazy" class="print" src="{p["image"]}"><figcaption><b>{html.escape(str(p["serial"] or p["release"] or "?"))}</b>, '
                    f'{len(p["label_photos"])} label photos{"" if p["paper"] else "; no paper found: median colours"}</figcaption>'
                    f'<div>{thumbs}</div></figure>')
    counts = "".join(f"<li>{html.escape(f)}: {len(v)}</li>" for f, v in lists.items())
    with open(os.path.join(out_dir, "index.html"), "w") as f:
        f.write(f"""<!doctype html><meta charset="utf-8"><title>publish</title>
<style>body{{font:14px system-ui;margin:16px;background:#333;color:#eee}} figure{{margin:12px 0 24px}} .print{{width:340px;display:block}}
.lp{{width:120px;margin:2px}} .poor{{display:inline-block;width:120px;color:#fa0;font-size:11px}} figcaption{{font-size:12px;margin:4px 0}} a{{color:#9cf}}</style>
<h1>publish</h1>
<p>{len(figs)} prints; {len(lp)} label photos, {sum(1 for r in lp.values() if r["image"])} with an image, {with_url} with a URL (a label photo links to its page). Files: index.json, prints/, label-photos/, and the lists:</p>
<ul>{counts}</ul>
{"".join(figs)}""")


if __name__ == "__main__":
    main()
