# publish: the outputs collected into <generated>/publish/:
#   prints/<serial>_<print>.avif: each restored print, restore's image as it is (paper white where found, else median
#     colours), its file name prefixed with its serial (else its release, else "unknown"; characters other than letters,
#     digits and "-" made "-")
#   No label photo images (the user, 2026-11-10: the straightened photos aren't worth distributing, over 1 GB): each
#     label photo is in index.json, with where it came from. Poor fits (solve's "a poor" fallbacks) are listed with
#     poor_fit true; a print of poor fits only has no image (restore leaves it out).
#   index.json: {"prints": {id: {serial, release, title (the database's), shape, image, size (its w, h px), paper,
#     label_photos}}, "label_photos": {key: {print,
#     serial, source, page_url, image_url, poor_fit}}}. Ids and keys hold within a run only.
#   missing.json, unknown-serials.json (read-serials), few-photos.json (prints): the lists, copied as they are.
#   index.html: per platform (linked from the top, with its image count) every print with an image, by game title,
#     with its label photos' sources.
# The source and URLs come from photo-sources.json (by SHA-1): for output only, never read by a detection step.
# A print's image is copied again when it's missing or older than restore's; files of prints no longer there are
# removed, and the label-photos/ folder an older version wrote.
# Usage: publish.py [--sample]
import argparse, html, json, os, re, shutil, sys
import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photos, steps, shapes, straighten
import serials as serials_module

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


def file_prefix(p):
    """A print's serial for its file name: its serial, else its release, else "unknown", made safe."""
    return re.sub(r"[^A-Za-z0-9-]+", "-", str(p["serial"] or p["release"] or "unknown")).strip("-") or "unknown"


def newer(out, *ins):
    return os.path.exists(out) and all(os.path.getmtime(out) >= os.path.getmtime(i) for i in ins)


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
    titles = {r["id"]: r["title"] for r in json.load(open(serials_module.DATABASE))}
    poor = poor_fits(solved)
    out_dir = os.path.join(gen, "publish")
    os.makedirs(os.path.join(out_dir, "prints"), exist_ok=True)
    if os.path.isdir(os.path.join(out_dir, "label-photos")):  # written by an older version
        shutil.rmtree(os.path.join(out_dir, "label-photos"))

    index = {"prints": {}, "label_photos": {}}
    copies = []
    for p in prints["prints"]:
        name = straighten.file_name(p["id"])
        restored = os.path.join(gen, "restore", name)
        desc_file = restored[:-5] + ".json"
        desc = json.load(open(desc_file)) if os.path.exists(desc_file) else {}
        image = None
        if os.path.exists(restored):
            image = "prints/" + file_prefix(p) + "_" + name
            copies.append((restored, os.path.join(out_dir, image)))
        crop = desc.get("crop") or {}
        index["prints"][p["id"]] = {"serial": p["serial"], "release": p["release"], "title": titles.get(p["release"]),
                                    "shape": p["shape"], "image": image,
                                    "size": [crop["w"], crop["h"]] if image and crop else None,
                                    "paper": desc.get("paper") is not None if desc else None, "label_photos": p["keys"]}
        for k in p["keys"]:
            sha1 = k.split("@")[0]
            s = src.get(sha1, {})
            index["label_photos"][k] = {"print": p["id"], "serial": (serials.get(k) or {}).get("serial"),
                                        "source": s.get("source"), "page_url": s.get("page_url"),
                                        "image_url": s.get("image_url"), "poor_fit": k in poor}

    wanted = {os.path.basename(b) for _, b in copies}
    for f in os.listdir(os.path.join(out_dir, "prints")):
        if f not in wanted:
            os.remove(os.path.join(out_dir, "prints", f))
    for a, b in copies:
        if not newer(b, a):
            shutil.copyfile(a, b + ".tmp")
            os.replace(b + ".tmp", b)
    for step, f in LISTS:
        if os.path.exists(os.path.join(gen, step, f)):
            shutil.copyfile(os.path.join(gen, step, f), os.path.join(out_dir, f))
    steps.write_json(os.path.join(out_dir, "index.json"), index)
    page(out_dir, index)
    print(f"{len(copies)} prints, {len(index['label_photos'])} label photos listed ({len(poor & set(index['label_photos']))} poor fits)")
    print(f"page: {os.path.join(out_dir, 'index.html')}")


PLATFORMS = [("dmg", "Game Boy"), ("cgb", "Game Boy Color"), ("agb", "Game Boy Advance")]
MIN_COLUMN = 260  # px: the grid's columns at least this wide, as many as fit, stretched to the page's width


def page(out_dir, index):
    """index.html: per platform (linked from the top, with its image count) the prints with an image, by game title
    (prints without one last, by serial), in a grid of as many columns as fit (MIN_COLUMN); each image at most half
    its pixel width wide, so it shows at 2x pixel density or more."""
    lp = index["label_photos"]
    used = lambda p: sum(1 for k in p["label_photos"] if not lp[k]["poor_fit"])  # poor fits aren't used
    shown = [p for p in index["prints"].values() if p["image"]]
    order = lambda p: (p["title"] is None, (p["title"] or "").casefold(), str(p["serial"] or p["release"] or ""))
    sections, links = [], []
    for shape, platform in PLATFORMS:
        ps = sorted((p for p in shown if p["shape"] == shape), key=order)
        figs = []
        for p in ps:
            sources = ", ".join(
                (f'<a href="{html.escape(lp[k]["page_url"] or lp[k]["image_url"])}">{html.escape(lp[k]["source"] or "?")}</a>'
                 if lp[k]["page_url"] or lp[k]["image_url"] else html.escape(lp[k]["source"] or "?"))
                + (' <span class="poor">(poor fit)</span>' if lp[k]["poor_fit"] else "") for k in p["label_photos"])
            w = (p.get("size") or [680])[0] / 2
            figs.append(f'<figure><img loading="lazy" src="{p["image"]}" style="max-width:{w:.0f}px">'
                        f'<figcaption><b>{html.escape(p["title"] or "(no title)")}</b><br>{html.escape(str(p["serial"] or p["release"] or "?"))}, '
                        f'Recreated from {used(p)} photo{"" if used(p) == 1 else "s"}{"" if p["paper"] else "; no paper found: median colours"}'
                        f'<div class="src">{sources}</div></figcaption></figure>')
        links.append(f'<li><a href="#{shape}">{platform}</a>: {len(ps)} images</li>')
        sections.append(f'<h2 id="{shape}">{platform} ({len(ps)})</h2><div class="grid">{"".join(figs)}</div>')
    with open(os.path.join(out_dir, "index.html"), "w") as f:
        f.write(f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>publish</title>
<style>body{{font:14px system-ui;margin:16px;background:#333;color:#eee}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax({MIN_COLUMN}px,1fr));gap:16px;align-items:start}}
figure{{margin:0;min-width:0}} figure img{{display:block;width:100%;height:auto;margin:0 auto}} figcaption{{font-size:12px;margin:4px 0}}
.src{{font-size:11px;color:#bbb;margin-top:2px}} .poor{{color:#fa0}} a{{color:#9cf}} h2{{margin-top:32px}}</style>
<ul>{"".join(links)}</ul>
{"".join(sections)}""")


if __name__ == "__main__":
    main()
