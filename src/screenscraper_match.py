# screenscraper_match: which cartridge of the catalogue each ScreenScraper label image is. ScreenScraper says which game
# and region an image is of, not which print: the serial printed on the label does. Run it from the repository folder,
# after screenscraper_download.py:
#   python run.py py src/screenscraper_match.py
# For every image in screenscraper-labels/index.json:
#   serial: the label's text is read (read_text, RapidOCR; the images are flat and upright already) and its serials
#     (serials.reads) looked up in the catalogue (published-labels/labels.json and wanted.json) and, when it's there,
#     the database (../gb-game-list/database/releases.json);
#   near: no exact serial, a near one (serials.near: OCR's look-alikes, a cut-off platform);
#   unknown: a whole serial was read, but neither the catalogue nor the database has it (a print we don't have; its
#     release could still be the title's guess, with another serial);
#   title: no serial at all, the releases whose titles best match ScreenScraper's names for the game on its system,
#     those of the image's region first. Only a guess, for checking by hand;
#   none: nothing.
# Into screenscraper-labels/matches.json: {image: {"game", "system", "region" (ScreenScraper's), "how", "serial",
#   "printed_region" (the serial's: where the label was really sold, FRA on a label ScreenScraper files as eu), "release", "title",
#   "labels" (restored prints of that serial or release), "wanted" (wanted prints), "text", "guesses" (title only)}},
# the page screenscraper-labels/matches.html: each image beside our restored label, unmatched ones first; and
# screenscraper-labels/unknown-serials.txt: the serials read that the database lacks (serial, title, images).
# A region whose image is the same as another's (index.json's "same") gets that image's answer, with "same_as"; the
# page shows such images once, with every region's name.
# The text read is cached by the image's content in screenscraper-labels/ocr/<sha1>.json (several regions often share
# one image), so running it again only reads new images.
import hashlib
import html
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import serials

OUT = "screenscraper-labels"
LABELS = os.path.join("published-labels", "labels.json")
WANTED = os.path.join("published-labels", "wanted.json")
SYSTEMS = {"gb": "dmg", "gbc": "cgb", "gba": "agb"}
# ScreenScraper's regions -> the serial regions that can be printed on a label sold there (wor: any)
REGIONS = {"us": {"USA", "CAN"}, "ca": {"CAN", "USA"}, "jp": {"JPN"}, "kr": {"KOR"}, "cn": {"CHN"}, "tw": {"HKG", "ASI"},
           "asi": {"ASI", "HKG"}, "br": {"BRA"}, "au": {"AUS", "EUR"}, "de": {"NOE", "FRG", "EUR"},
           "fr": {"FRA", "FAH", "EUR"}, "sp": {"ESP", "SPA", "EUR"}, "it": {"ITA", "EUR"}, "nl": {"HOL", "EUR"},
           "uk": {"UKV", "EUU", "EUR"}, "se": {"SCN", "EUR"}, "dk": {"SCN", "DAN", "EUR"}, "fi": {"SCN", "EUR"},
           "no": {"SCN", "EUR"},
           "eu": {"EUR", "EUU", "EUB", "UKV", "NOE", "FRG", "FRA", "FAH", "ESP", "SPA", "ITA", "HOL", "SCN", "DAN", "AUS"}}


def catalogue(labels_path=LABELS, wanted_path=WANTED):
    """The catalogue's prints: [{"print", "kind" (labels/wanted), "serials", "release", "title", "system", "file"}]."""
    out = []
    for path, kind in ((labels_path, "labels"), (wanted_path, "wanted")):
        if os.path.exists(path):
            for e in json.load(open(path, encoding="utf-8")):
                out.append({"print": e.get("id") or e.get("print"), "kind": kind, "release": e.get("release"),
                            "serials": [s for s in ([e.get("serial")] + list(e.get("serials") or [])) if s],
                            "title": e.get("title"), "system": e.get("system"), "file": e.get("file")})
    return out


def release_index(prints, database=serials.DATABASE):
    """Every known serial and release id -> {"id", "title", "titles", "system"}: the database's, else the catalogue's."""
    release_of = serials.load_database(database) if database and os.path.exists(database) else {}
    for p in prints:
        r = release_of.get(p["release"]) or {"id": p["release"], "title": p["title"], "titles": [], "system": p["system"]}
        for key in p["serials"] + [p["release"]]:
            if key:
                release_of.setdefault(key, r)
    return release_of


def system_of(release):
    s = (release.get("system") or release.get("id") or "").lower()
    return {"dmg": "dmg", "cgb": "cgb", "agb": "agb", "gb": "dmg", "gbc": "cgb", "gba": "agb"}.get(s[:3], s[:3])


def found_serials(lines, release_of, regions):
    """(how, serial, release) of a label's text: an exact serial the index knows, else a near one, else (none, ...)."""
    for line in lines:
        for s in serials.reads(line):
            r = serials.release(s, release_of)
            if r:
                return "serial", s, r
    for line in lines:
        for s, cost, read in serials.near(line, regions):
            return "near", s, release_of[s]
    unknown = [s for line in lines for s in serials.reads(line) if serials.region_of(s)]
    if unknown:  # a whole serial nobody knows: a release missing from the catalogue (and the database, if it's there)
        return "unknown", unknown[0], None
    return "none", None, None


def prints_of(serial, release, prints, region):
    """The catalogue's prints of a serial (exact), else of its release, those whose serial fits the image's region first."""
    exact = [p for p in prints if serial and serial in p["serials"]]
    if exact:
        return exact
    same = [p for p in prints if release and p["release"] == release.get("id")]
    fits = REGIONS.get(region)
    return sorted(same, key=lambda p: 0 if not fits or any(serials.region_of(s) in fits for s in p["serials"]) else 1)


def guesses(names, system, titles, top=3):
    """[(score, release)] of the releases whose titles best match ScreenScraper's names, on the image's system."""
    best = {}
    for n in names:
        for score, r in titles.search(serials.plain(n), systems=None, top=12):
            if system_of(r) == system and score > best.get(r["id"], (0, None))[0]:
                best[r["id"]] = (score, r)
    return sorted(best.values(), key=lambda x: -x[0])[:top]


def read_cached(path, cache_dir, reader):
    """The lines of text on an image, cached by its content."""
    with open(path, "rb") as f:
        sha1 = hashlib.sha1(f.read()).hexdigest()
    cached = os.path.join(cache_dir, sha1 + ".json")
    if os.path.exists(cached):
        with open(cached, encoding="utf-8") as f:
            return json.load(f)
    lines = reader(path)
    os.makedirs(cache_dir, exist_ok=True)
    with open(cached, "w", encoding="utf-8") as f:
        json.dump(lines, f, ensure_ascii=False)
    return lines


def ocr(path):
    import cv2
    import numpy as np
    import read_text
    image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)  # imread fails on some Windows paths
    return [l["text"] for l in read_text.read(image)] if image is not None else []


def match(state, prints, release_of, read, out=OUT):
    regions = serials.by_region(release_of)
    titles = serials.TitleIndex(list({id(r): r for r in release_of.values() if r.get("id")}.values()))
    result = {}
    for gid, g in state["games"].items():
        for name in g.get("labels", []):
            path = os.path.join(out, name)
            if not os.path.exists(path):
                continue
            region = os.path.splitext(name)[0].rsplit("-", 1)[-1]
            system = SYSTEMS.get(g["system"], g["system"])
            lines = read(path)
            how, serial, release = found_serials(lines, release_of, regions)
            if release and system_of(release) not in (system, ""):  # a GB serial on a GBA label is a misread
                how, serial, release = "none", None, None
            entry = {"game": gid, "system": g["system"], "region": region, "names": g.get("names", []), "how": how,
                     "serial": serial, "printed_region": serials.region_of(serial), "release": release and release.get("id"), "title": release and release.get("title"),
                     "text": lines}
            if release:
                ps = prints_of(serial, release, prints, region)
            else:
                found = guesses(g.get("names", []), system, titles)
                entry["guesses"] = [{"release": r["id"], "title": r.get("title"), "score": round(s, 2)} for s, r in found if s >= 0.5]
                if entry["guesses"] and how == "none":
                    entry["how"] = "title"
                ps = [] if how == "unknown" else [p for x in entry["guesses"][:1] for p in prints_of(None, {"id": x["release"]}, prints, region)]
            entry["labels"] = [p["print"] for p in ps if p["kind"] == "labels"]
            entry["wanted"] = [p["print"] for p in ps if p["kind"] == "wanted"]
            result[name] = entry
    for gid, g in state["games"].items():  # the very same image (another region's, or another game's): its answer
        for name, shared in g.get("same", {}).items():
            if shared in result:
                result[name] = {**result[shared], "game": gid, "names": g.get("names", []),
                                "region": os.path.splitext(name)[0].rsplit("-", 1)[-1], "same_as": shared}
    return result


def unknown_serials(result):
    """Serials read on a label that neither the catalogue nor the database has: {serial: (ScreenScraper's names, images)},
    sorted. Releases missing from the database, mostly."""
    out = {}
    for name, e in result.items():
        if e["how"] == "unknown":
            names, images = out.setdefault(e["serial"], ([], []))
            names += [n for n in e["names"] if n not in names]
            images.append(name)
    return dict(sorted(out.items()))


ORDER = {"none": 0, "unknown": 1, "title": 2, "near": 3, "serial": 4}


def page(result, prints, path):
    files = {p["print"]: p["file"] for p in prints if p["file"]}
    rows = []
    shared = {}
    for name, e in result.items():
        if e.get("same_as"):
            shared.setdefault(e["same_as"], []).append(name)
    for name, e in sorted(result.items(), key=lambda kv: (ORDER[kv[1]["how"]], kv[1]["system"], kv[0])):
        if e.get("same_as"):
            continue
        ours = "".join(f'<figure><img loading="lazy" src="../published-labels/{html.escape(files[p])}"><figcaption>{html.escape(p)}</figcaption></figure>'
                       for p in e["labels"][:2] if p in files)
        guessed = ", ".join(f'{g["release"]} {g["title"]} ({g["score"]})' for g in e.get("guesses", []))
        what = " — ".join(x for x in (e["serial"], guessed) if x) or "—"
        rows.append(f'<tr class="{e["how"]}"><td><img loading="lazy" src="{html.escape(name)}"><br>{html.escape(", ".join([name] + shared.get(name, [])))}<br>'
                    f'{html.escape((e["names"] or [""])[0])}</td><td><b>{e["how"]}</b><br>{html.escape(what)}<br>'
                    f'{html.escape(e["title"] or "")}<br>wanted: {html.escape(", ".join(e["wanted"]) or "—")}'
                    f'<details><summary>text read</summary>{html.escape(" | ".join(e["text"]))}</details></td><td>{ours}</td></tr>')
    counts = {k: sum(1 for e in result.values() if e["how"] == k) for k in ORDER}
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"""<!doctype html><meta charset="utf-8"><title>ScreenScraper matches</title>
<style>body{{font:14px system-ui;margin:16px}}table{{border-collapse:collapse}}td{{border-top:1px solid #ccc;padding:8px;vertical-align:top}}
td img{{max-width:300px;max-height:180px}}figure{{display:inline-block;margin:0 8px 0 0}}tr.none td:nth-child(2) b{{color:#b00}}
tr.title td:nth-child(2) b,tr.unknown td:nth-child(2) b{{color:#b60}}tr.near td:nth-child(2) b{{color:#06a}}tr.serial td:nth-child(2) b{{color:#080}}</style>
<h1>ScreenScraper label images and the catalogue</h1>
<p>{len(result)} images: {counts["serial"]} by serial, {counts["near"]} by a near serial, {counts["title"]} guessed by title, {counts["unknown"]} with a serial we don't have, {counts["none"]} unmatched.</p>
<table>{"".join(rows)}</table>""")


def main(args):
    with open(os.path.join(OUT, "index.json"), encoding="utf-8") as f:
        state = json.load(f)
    prints = catalogue()
    release_of = release_index(prints)
    if not os.path.exists(serials.DATABASE):
        print("No", serials.DATABASE, "- matching against the catalogue only.")
    cache = os.path.join(OUT, "ocr")
    done = [0]

    def read(path):
        done[0] += 1
        if done[0] % 50 == 0:
            print(done[0], "images...")
        return read_cached(path, cache, ocr)

    result = match(state, prints, release_of, read)
    with open(os.path.join(OUT, "matches.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, indent=1, ensure_ascii=False)
    page(result, prints, os.path.join(OUT, "matches.html"))
    unknown = unknown_serials(result)
    with open(os.path.join(OUT, "unknown-serials.txt"), "w", encoding="utf-8", newline="\n") as f:
        for serial, (names, images) in unknown.items():
            f.write(f"{serial}\t{names[0] if names else '?'}\t{' '.join(images)}\n")
    counts = {k: sum(1 for e in result.values() if e["how"] == k) for k in ORDER}
    print(f"{len(result)} images: {counts['serial']} by serial, {counts['near']} near, {counts['title']} by title, {counts['unknown']} unknown serial, "
          f"{counts['none']} unmatched. See screenscraper-labels/matches.html")
    print(f"{len(unknown)} serials the database doesn't have: screenscraper-labels/unknown-serials.txt")


if __name__ == "__main__":
    main(sys.argv[1:])
