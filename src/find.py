# find: the label photos in every photo, from the evidence, into <generated>/find/label-photos.json:
#   {"label_photos": [{"key", "photo", "centre" [x, y], "radius", "outline" [[x, y]...] (rough: the hull of the
#                      evidence), "shape", "found_by" ("serial", "near serial", "string and match", "match"),
#                      "strings": [{"text", "serial", "kind" (exact, near, unknown), "cost", "release", "corners"}],
#                      "matches": [{"to" (key), "inliers"}]}],
#    "sets": [[key...]] (label photos linked by matches),
#    "rejected": [{"photo", "centre", "strings", "why"}]}
# The evidence, in this order:
#   1. Seeds: the serial-looking strings each photo's text holds (read-text): exact serials the database knows, near
#      serials (serials.near) and strings it doesn't know. Strings of one label (within MERGE line heights) are one
#      candidate. A candidate with an exact or near serial is a label photo; one with only unknown strings is one if a
#      match links it to a serial-looking string in another photo (possibly a new release).
#   2. Its area: a circle around the strings, RADIUS line heights (a label's diagonal: the serial's line is about
#      2.2 mm tall on DMG labels and sits anywhere on the label); the matched points inside it make the outline.
#   3. Spreading: a match whose points in one photo lie mostly inside a label photo's circle makes a label photo where
#      they lie in the other photo (its circle and outline carried over through the match's homography), or links the
#      one already there; repeated until nothing changes. A match that touches no label photo (a watermark, a
#      background, embossing) starts nothing.
#   4. Label photos of one photo whose outlines (the hull of their evidence) share MERGE_OVERLAP of the smaller are
#      one: spreading's circles are rough and may land a second label photo on one already there.
# The shape is the serial's platform (DMG-, CGB-, AGB-); a label photo found by matching takes its linked ones' (most).
# Keys: <sha1>@<x>,<y>, the centre in whole percent of the photo's width and height.
# Done again when label-photos.json is older than this file or than any of its inputs.
# Usage: find.py [--sample]
import argparse, html, json, os, re, sys
import numpy as np, cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photos, serials, steps, match

MERGE = 12          # line heights: strings closer than this are one label's
RADIUS = 28         # line heights: a label's diagonal around its serial
INSIDE = 0.5        # the share of a match's points that must lie in a label photo's circle for it to spread
MIN_POINTS = 15
MERGE_OVERLAP = 0.5  # label photos of one photo sharing this much of the smaller outline are one


def seeds(lines, release_of, regions):
    """The serial-looking strings of a photo's lines: [{"text", "serial", "kind", "cost", "release", "corners",
    "centre", "height"}]."""
    out = []
    for line in lines:
        c = np.array(line["corners"], float)
        centre, height = c.mean(0), (np.hypot(*(c[3] - c[0])) + np.hypot(*(c[2] - c[1]))) / 2
        base = {"text": line["text"], "corners": line["corners"], "centre": centre.tolist(), "height": float(height)}
        reads = serials.reads(line["text"])
        exact = [s for s in reads if serials.release(s, release_of)]
        for s in exact[:1]:
            out.append({**base, "serial": s, "kind": "exact", "cost": 0, "release": serials.release(s, release_of)["id"]})
        if exact:
            continue
        near = serials.near(line["text"], regions)
        for s, cost, _ in near[:1]:
            out.append({**base, "serial": s, "kind": "near", "cost": cost, "release": serials.release(s, release_of)["id"]})
        if not near and reads:
            out.append({**base, "serial": reads[0], "kind": "unknown", "cost": None, "release": None})
    return out


def group(strings):
    """Strings of one label (within MERGE line heights of each other) as candidates: [[string...]]."""
    groups = []
    for s in strings:
        near = [g for g in groups if any(np.hypot(*np.subtract(s["centre"], t["centre"])) < MERGE * max(s["height"], t["height"]) for t in g)]
        merged = [s] + [t for g in near for t in g]
        groups = [g for g in groups if g not in near] + [merged]
    return groups


def key(sha1, centre, size):
    return f"{sha1}@{int(centre[0] / size[0] * 100)},{int(centre[1] / size[1] * 100)}"


def inside(points, lp):
    return np.hypot(*(np.asarray(points) - lp["centre"]).T) < lp["radius"]


def shape_of(serial):
    m = re.match(r"(?:DIS-)?(DMG|CGB|AGB)", serial or "")
    return m.group(1).lower() if m else None


def outline(lp):
    """The hull of a label photo's evidence: its matched points and its strings' corners."""
    pts = [np.asarray(p) for p in lp["points"]] + [np.array(t["corners"], float) for t in lp["strings"]]
    pts = np.vstack(pts) if pts else lp["centre"].reshape(1, 2)
    return cv2.convexHull(pts.astype(np.float32)).reshape(-1, 2).round(1).tolist() if len(pts) >= 3 else pts.tolist()


def overlap(a, b):
    """The share of the smaller outline that the two outlines share."""
    pa, pb = np.float32(a).reshape(-1, 2), np.float32(b).reshape(-1, 2)
    if len(pa) < 3 or len(pb) < 3:
        return 0.0
    area, _ = cv2.intersectConvexConvex(pa, pb)
    smaller = min(cv2.contourArea(pa), cv2.contourArea(pb))
    return float(area / smaller) if smaller > 0 else 0.0


FOUND_BY = ["serial", "near serial", "string and match", "match"]


def merge_overlapping(lps):
    """Label photos of one photo whose outlines share MERGE_OVERLAP of the smaller are merged: strings, points and
    links combined; the centre and circle of the one with strings (else the first); found by the strongest."""
    out = []
    for lp in lps:
        same = next((o for o in out if o["photo"] == lp["photo"] and overlap(o["outline"], lp["outline"]) >= MERGE_OVERLAP), None)
        if same is None:
            out.append(lp)
            continue
        keep, other = (same, lp) if same["strings"] or not lp["strings"] else (lp, same)
        keep["strings"] = keep["strings"] + other["strings"]
        keep["points"] = keep["points"] + other["points"]
        keep["found_by"] = min(keep["found_by"], other["found_by"], key=FOUND_BY.index)
        for o, n in other.get("links", []):
            o["links"] = [(keep if x is other else x, m) for x, m in o["links"]]
        keep["links"] = [(o, n) for o, n in keep.get("links", []) + other.get("links", []) if o is not keep and o is not other]
        keep["outline"] = outline(keep)
        if keep is lp:
            out[out.index(same)] = lp
    return out


def find(chosen, texts, matches, release_of):
    """The label photos, their sets and the rejected candidates, from the photos' texts and the matches."""
    regions = serials.by_region(release_of)
    sizes = {s: texts[s]["size"] or [1, 1] for s in chosen}
    lps, rejected = [], []  # label photos: dicts with "photo", "centre" (array), "radius", "strings", "found_by"
    unknown = {}            # photo -> candidates with only unknown strings, decided after the matches are known
    for s in chosen:
        for g in group(seeds(texts[s]["lines"], release_of, regions)):
            centre = np.mean([t["centre"] for t in g], 0)
            radius = RADIUS * max(t["height"] for t in g)
            kinds = {t["kind"] for t in g}
            strings = [{k: t[k] for k in ("text", "serial", "kind", "cost", "release", "corners")} for t in g]
            cand = {"photo": s, "centre": centre, "radius": radius, "strings": strings, "points": [],
                    "found_by": "serial" if "exact" in kinds else "near serial" if "near" in kinds else None}
            if cand["found_by"]:
                lps.append(cand)
            else:
                unknown.setdefault(s, []).append(cand)
    by_photo = lambda s: [lp for lp in lps if lp["photo"] == s]
    # both directions of every match: (photo a, photo b, a -> b, points in a, points in b)
    both = []
    for a, b, H, inl in matches:
        both.append((a, b, H, inl[:, :2], inl[:, 2:]))
        both.append((b, a, np.linalg.inv(H), inl[:, 2:], inl[:, :2]))
    # candidates with only unknown strings: a label photo if a match links them to a serial-looking string elsewhere
    for a, b, H, pa, pb in both:
        for cand in unknown.get(a, []):
            if cand["found_by"] or inside(pa, cand).mean() < INSIDE:
                continue
            others = by_photo(b) + unknown.get(b, [])
            if any(inside(pb, o).mean() >= INSIDE for o in others):
                cand["found_by"] = "string and match"
                lps.append(cand)
    for cands in unknown.values():
        rejected += [{"photo": c["photo"], "centre": c["centre"].tolist(), "strings": c["strings"],
                      "why": "only strings the database doesn't know, and no match to a serial elsewhere"}
                     for c in cands if not c["found_by"]]
    # spreading, until nothing changes
    links = set()
    changed = True
    while changed:
        changed = False
        for a, b, H, pa, pb in both:
            for lp in by_photo(a):
                ins = inside(pa, lp)
                if ins.sum() < MIN_POINTS or ins.mean() < INSIDE:
                    continue
                qa, qb = pa[ins], pb[ins]
                there = [o for o in by_photo(b) if inside([qb.mean(0)], o)[0]]
                if there:
                    other = there[0]
                else:  # a new label photo where the match lands, its circle carried over
                    centre = cv2.perspectiveTransform(lp["centre"].reshape(1, 1, 2), H).reshape(2)
                    edge = cv2.perspectiveTransform((lp["centre"] + [lp["radius"], 0]).reshape(1, 1, 2), H).reshape(2)
                    w, h = sizes[b]
                    if not (0 <= centre[0] < w and 0 <= centre[1] < h):
                        centre = qb.mean(0)
                    other = {"photo": b, "centre": centre, "radius": float(np.hypot(*(edge - centre))), "strings": [],
                             "points": [], "found_by": "match"}
                    lps.append(other)
                    changed = True
                link = (id(lp), id(other)) if id(lp) < id(other) else (id(other), id(lp))
                if link not in links:
                    links.add(link)
                    lp.setdefault("links", []).append((other, len(qa)))
                    other.setdefault("links", []).append((lp, len(qa)))
                    lp["points"].append(qa)
                    other["points"].append(qb)
    # outlines; label photos of one photo whose outlines mostly overlap are one (spreading's circles are rough)
    for lp in lps:
        lp["outline"] = outline(lp)
    lps = merge_overlapping(lps)
    for lp in lps:
        lp["outline"] = outline(lp)
        lp["key"] = key(lp["photo"], lp["centre"], sizes[lp["photo"]])
    for lp in lps:
        own = [shape_of(t["serial"]) for t in lp["strings"] if t["kind"] != "unknown"]
        lp["shape"] = max(set(own), key=own.count) if own else None
    for _ in range(len(lps)):  # shapes spread along links
        moved = False
        for lp in lps:
            if lp["shape"] is None:
                linked = [o["shape"] for o, _ in lp.get("links", []) if o["shape"]]
                if linked:
                    lp["shape"] = max(set(linked), key=linked.count)
                    moved = True
        if not moved:
            break
    parent = {id(lp): id(lp) for lp in lps}
    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for lp in lps:
        for o, _ in lp.get("links", []):
            parent[root(id(lp))] = root(id(o))
    sets = {}
    for lp in lps:
        sets.setdefault(root(id(lp)), []).append(lp["key"])
    out = [{"key": lp["key"], "photo": lp["photo"], "centre": np.round(lp["centre"], 1).tolist(),
            "radius": round(float(lp["radius"]), 1), "outline": lp["outline"], "shape": lp["shape"],
            "found_by": lp["found_by"], "strings": lp["strings"],
            "matches": [{"to": o["key"], "inliers": n} for o, n in lp.get("links", [])]} for lp in lps]
    return {"label_photos": out, "sets": sorted(sets.values(), key=len, reverse=True), "rejected": rejected}


def page(out_dir, chosen, result, texts):
    lps = result["label_photos"]
    by_photo = {}
    for lp in lps:
        by_photo.setdefault(lp["photo"], []).append(lp)
    none = [s for s in chosen if s not in by_photo]
    several = [s for s in chosen if len(by_photo.get(s, [])) > 1]
    counts = {}
    for lp in lps:
        counts[lp["found_by"]] = counts.get(lp["found_by"], 0) + 1
    shapes = {}
    for lp in lps:
        shapes[lp["shape"]] = shapes.get(lp["shape"], 0) + 1
    rel = os.path.relpath(".", out_dir)
    colours = {"serial": "#2a2", "near serial": "#6c2", "string and match": "#c80", "match": "#28c"}

    def figure(s):
        w, h = texts[s]["size"] or [1, 1]
        shapes_svg = ""
        for lp in by_photo.get(s, []):
            pts = " ".join(f"{x},{y}" for x, y in lp["outline"])
            c = colours[lp["found_by"]]
            shapes_svg += (f'<circle cx="{lp["centre"][0]}" cy="{lp["centre"][1]}" r="{lp["radius"]}" fill="none" stroke="{c}" stroke-dasharray="8 8" stroke-width="{max(w, h) / 300}"/>'
                           f'<polygon points="{pts}" fill="{c}" fill-opacity="0.15" stroke="{c}" stroke-width="{max(w, h) / 200}"/>')
        label = "<br>".join(html.escape(f'{lp["found_by"]}: {", ".join(t["serial"] for t in lp["strings"]) or "-"} ({lp["shape"]}, {len(lp["matches"])} links)') for lp in by_photo.get(s, []))
        return (f'<figure><div class="ph"><img loading="lazy" src="{rel}/{chosen[s]}"><svg viewBox="0 0 {w} {h}" preserveAspectRatio="none">{shapes_svg}</svg></div>'
                f'<figcaption><code>{s[:10]}</code><br>{label}</figcaption></figure>')

    rejected = "".join(f'<li><code>{r["photo"][:10]}</code>: {html.escape(", ".join(t["text"] for t in r["strings"]))}</li>' for r in result["rejected"])
    with open(os.path.join(out_dir, "index.html"), "w") as f:
        f.write(f"""<!doctype html><meta charset="utf-8"><title>find</title>
<style>body{{font:14px system-ui;margin:16px}} figure{{display:inline-block;margin:6px;vertical-align:top;width:260px}}
.ph{{position:relative;display:inline-block}} .ph img{{max-width:260px;max-height:260px;display:block}} .ph svg{{position:absolute;inset:0;width:100%;height:100%}}
figcaption{{font-size:12px}}</style>
<h1>find</h1>
<p>{len(chosen)} photos, {len(lps)} label photos (found by: {", ".join(f"{k} {v}" for k, v in counts.items())}; shapes: {", ".join(f"{k} {v}" for k, v in shapes.items())}), {len(result["sets"])} linked sets (largest {len(result["sets"][0]) if result["sets"] else 0}). Photos with no label photo: {len(none)}; with several: {len(several)}.</p>
<p>Outline filled: the hull of the evidence; dashed: the circle the evidence was looked for in. Green: serial, light green: near serial, orange: unknown string and match, blue: found by a match.</p>
<h2>No label photo ({len(none)})</h2>{"".join(figure(s) for s in none)}
<h2>Several label photos ({len(several)})</h2>{"".join(figure(s) for s in several)}
<h2>Rejected candidates ({len(result["rejected"])})</h2><ul>{rejected}</ul>
<h2>All</h2>{"".join(figure(s) for s in chosen if s in by_photo and s not in several)}
""")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true")
    args = ap.parse_args()
    chosen = photos.chosen(args.sample)
    gen = photos.generated(args.sample)
    out_dir = os.path.join(gen, "find")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "label-photos.json")
    text_files = {s: os.path.join(gen, "read-text", s + ".json") for s in chosen}
    match_files = [os.path.join(gen, "match", s + ".npz") for s in chosen]
    missing = [p for p in list(text_files.values()) + match_files if not os.path.exists(p)]
    if missing:
        sys.exit(f"{len(missing)} inputs missing: run make read-text and make match first")
    newest = max(os.path.getmtime(p) for p in list(text_files.values()) + match_files)
    texts = {s: json.load(open(p)) for s, p in text_files.items()}
    if steps.stale(out, __file__) or os.path.getmtime(out) < newest:
        result = find(chosen, texts, match.read_matches(os.path.join(gen, "match"), list(chosen)), serials.load_database())
        steps.write_json(out, result)
    result = json.load(open(out))
    page(out_dir, chosen, result, texts)
    print(f"{len(result['label_photos'])} label photos; page: {os.path.join(out_dir, 'index.html')}")


if __name__ == "__main__":
    main()
