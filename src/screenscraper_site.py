# screenscraper_site: the catalogue of every label, for browsing them locally: build_site's page (the same as for the
# restored labels) over ScreenScraper's label images, plus geon's restored labels of the cartridges ScreenScraper has
# no image of, and a Missing list: the database's releases with no label image at all. Run after screenscraper_match.py:
#   python run.py py src/screenscraper_site.py [--only-screenscraper]      ->  screenscraper-labels/index.html
# Each distinct image is a label: its serial (what screenscraper_match read on it, when it read one), the release's
# title if the serial is known, else ScreenScraper's name for the game, its system. Regions come from the serial, as on
# the main page; an image with no serial read shows as region "other". Images in ignore.txt, or of games left out, are
# not there (screenscraper_match never matched them). Writes screenscraper-labels/labels.json and wanted.json (Missing),
# which build_site reads. A label under 450 px wide in its source (added.json's "source_width", else the image's
# width) is marked low resolution: the page can show those alone, for a second pass. Labels added on the page (serve_catalogue's "Add label") come from added.json. Each label can be reported as wrong ("Report a problem"): the reports stay in the browser and
# "Copy for ignore.txt" gives the lines for screenscraper-labels/ignore.txt; run this again (after --dedupe for
# ScreenScraper's images) and they're gone. A restored label is left out by its file name the same way.
# ScreenScraper's images, for local use: don't publish this page.
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import urllib.parse

import build_site
import screenscraper_download as dl
import serials

OUT = "screenscraper-labels"
SYSTEMS = {"gb": "dmg", "gbc": "cgb", "gba": "agb"}
SERIAL_SYSTEM = {"DMG": "dmg", "CGB": "cgb", "AGB": "agb"}
CREDIT = ('Label images from <a href="https://www.screenscraper.fr/">ScreenScraper</a> (matched to serials by reading '
          'the text on them) and restored by geon (<a href="https://geon.github.io/gameboy-cartridge-labels/">his site</a>). '
          'For local use: not to publish.')


def size_of(path):
    """[width, height] of a PNG or JPEG, from its header; None if it can't tell."""
    with open(path, "rb") as f:
        head = f.read(26)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            return list(struct.unpack(">II", head[16:24]))
        if head[:2] != b"\xff\xd8":
            return None
        f.seek(2)
        while True:
            marker = f.read(4)
            if len(marker) < 4 or marker[0] != 0xFF:
                return None
            if marker[1] in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">xHH", f.read(5))
                return [w, h]
            f.seek(struct.unpack(">H", marker[2:])[0] - 2, 1)


def labels(matches, ignore=frozenset(), out=OUT, exists=os.path.exists):
    """The labels.json entries for build_site: one per distinct image."""
    result, ids = [], set()
    for name, e in sorted(matches.items()):
        if e.get("same_as") or os.path.basename(name) in ignore or e.get("game") in ignore or not exists(os.path.join(out, name)):
            continue
        serial = e.get("serial") if e.get("how") in ("serial", "near", "unknown") else None
        system = SERIAL_SYSTEM.get((serial or "")[:3]) or SYSTEMS.get(e["system"], e["system"])
        base = serial or f"SS-{e['game']}-{e['region']}"
        uid, n = base, 1
        while uid in ids:  # several images of one serial (two scans, two of ScreenScraper's games)
            n += 1
            uid = f"{base}-{n}"
        ids.add(uid)
        result.append({"id": uid, "serial": serial or "", "release": e.get("release") or "", "system": system,
                       "title": e.get("title") or (e.get("names") or [""])[0], "file": name.replace("\\", "/"),
                       "size": size_of(os.path.join(out, name)) if exists(os.path.join(out, name)) else None, "photos": 0,
                       "screenscraper": e["game"]})
    return result


LOW_WIDTH = 450  # a label narrower than this in its source image is low resolution (ScreenScraper's are mostly 600)
RESTORED = os.path.join("published-labels", "labels.json")
GROUP = {"USA": "USA", "CAN": "USA", "JPN": "JPN", "KOR": "KOR", "CHN": "CHN"}
LETTER = {"J": "JPN", "E": "USA", "P": "EUR", "D": "NOE", "F": "FRA", "S": "ESP", "I": "ITA", "K": "KOR", "X": "EUR",
          "Y": "EUR", "U": "AUS", "H": "HOL", "C": "CHN"}
TEXT = {"heading": "Game Boy cartridge labels", "labelsTab": "Labels", "wantedTab": "Missing", "photos": False,
        "labelsLede": "Labels of Game Boy, Game Boy Color and Game Boy Advance cartridges, from ScreenScraper and from "
                      "geon's restorations. Search by title or serial, then open one to see it large.",
        "wantedLede": " cartridges the database knows have no label image yet: a straight, well-lit photo or scan of "
                      "the label would complete them."}


def restored(ss_labels, path=RESTORED, folder="published-labels", ignore=frozenset()):
    """geon's restored labels of the serials (and releases) ScreenScraper has no image of, as entries of this page."""
    if not os.path.exists(path):
        return []
    have = {l["serial"] for l in ss_labels if l["serial"]} | {l["release"] for l in ss_labels if l["release"]}
    out = []
    for e in json.load(open(path, encoding="utf-8")):
        if e.get("serial") in have or (e.get("release") and e["release"] in have and not e.get("serial")) or e["file"] in ignore:
            continue
        out.append({**{k: e.get(k) for k in ("id", "serial", "release", "title", "system", "size", "photos")},
                    "file": os.path.relpath(os.path.join(folder, e["file"]), OUT).replace("\\", "/"),
                    "source": f"restored by geon from {e.get('photos') or '?'} photos"})
    return out


def region_of(release):
    for s in release.get("cartridgeSerials") or []:
        r = s.rsplit("-", 1)[-1]
        if len(r) == 3 and r.isalpha():
            return r
    return LETTER.get(release["id"][-1:], "other")


FIXES = os.path.join(OUT, "database-fixes.json")


def database_fixes(path=FIXES):
    """Serials the database has wrong, and what they should be ("" to drop one): {"DMG-A4RJ-JPI": "DMG-A4RJ-JPN"}.
    The database came from reading photos, so a few serials were misread; this file corrects them here without
    touching the database itself."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def game_of(code):
    """The game a release or serial is of, across regions: its system and code without the region letter
    (DMG-AAUE, DMG-AAUP-EUR and DMG-AAUJ are all DMG-AAU; DMG-T3J, the Japanese DMG-T3, is DMG-T3)."""
    parts = (code or "").upper().split("-")
    if len(parts) < 2:
        return code
    c = parts[1]
    if len(c) == 4 or (len(c) == 3 and c.endswith("J")):
        c = c[:-1]
    return parts[0] + "-" + c


def missing(entries, releases):
    """The cartridges of the database no label of this page is of: the page's Missing list, one per serial (a German
    and a French label of one release are two cartridges), by title. A release the database knows no serial of is one
    entry, covered by any label of that release. A label whose serial was read without its region (AGB-A2CE, cut
    off) covers its release's serial only if the release has just one."""
    serials_have = {e["serial"] for e in entries if e.get("serial")}
    releases_have = {e["release"] for e in entries if e.get("release")} | {s.rsplit("-", 1)[0] for s in serials_have if s.count("-") >= 2}
    cut = {s for s in serials_have if s.count("-") == 1}  # read without the region
    out = []
    for r in releases.values():
        known = list(r.get("cartridgeSerials") or [])
        if not known:
            todo = [] if r["id"] in releases_have else [r["id"]]
        elif len(known) == 1 and (known[0].rsplit("-", 1)[0] in cut or r["id"] in cut):
            todo = []
        else:
            todo = [s for s in known if s not in serials_have]
        system = (r.get("system") or "")[:3].lower()
        for serial in todo:
            region = serial.rsplit("-", 1)[-1] if serial.count("-") >= 2 else region_of(r)
            query = " ".join(w for w in (r.get("title") or "", {"dmg": "Game Boy", "cgb": "Game Boy Color", "agb": "Game Boy Advance"}.get(system, ""),
                                         "Japan" if region == "JPN" else "", "cartridge") if w)
            out.append({"print": serial, "release": r["id"], "title": r.get("title") or r["id"], "system": system,
                        "region": GROUP.get(region, "USA/EUR" if region != "other" else "other"),
                        "serials": [serial], "needed": 1, "photos": 0,
                        "search": [{"label": "eBay", "url": "https://www.ebay.com/sch/i.html?" + urllib.parse.urlencode({"_nkw": query})},
                                   {"label": f"Google Images: {serial}", "url": "https://www.google.com/search?" + urllib.parse.urlencode({"tbm": "isch", "q": f'"{serial}"'})}]})
    have_games = {game_of(e.get("release") or e.get("serial")) for e in entries if e.get("release") or e.get("serial")}
    for w in out:  # a game with no label at all, or another version (region, revision) of one we have
        w["kind"] = "variant" if game_of(w["release"]) in have_games else "game"
    return sorted(out, key=lambda w: (w["title"].casefold(), w["print"]))


def main(args):
    with open(os.path.join(OUT, "matches.json"), encoding="utf-8") as f:
        matches = json.load(f)
    ignore = dl.ignored()
    entries = labels(matches, ignore)
    for e in entries:
        e["source"] = f"ScreenScraper (game {e.pop('screenscraper')})"
    added_path = os.path.join(OUT, "added.json")
    if os.path.exists(added_path):  # labels added on the page (serve_catalogue)
        for e in json.load(open(added_path, encoding="utf-8")):
            if os.path.basename(e["file"]) not in ignore and os.path.exists(os.path.join(OUT, e["file"])):
                entries.append({**e, "size": size_of(os.path.join(OUT, e["file"])), "photos": 0})
    for e in entries:  # small in the photo or scan it came from: worth a better one
        width = e.get("source_width") or (e.get("size") or [LOW_WIDTH])[0]
        e["lowres"] = width < LOW_WIDTH
    if "--only-screenscraper" not in args:
        entries += restored(entries, ignore=ignore)
    releases = {}
    fixes = database_fixes()
    if os.path.exists(serials.DATABASE):
        for r in json.load(open(serials.DATABASE, encoding="utf-8")):
            r["cartridgeSerials"] = [fixes.get(x, x) for x in r.get("cartridgeSerials") or [] if fixes.get(x, x)]
            releases[r["id"]] = r
    wanted = missing(entries, releases)
    with open(os.path.join(OUT, "labels.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(entries, f, indent=1, ensure_ascii=False)
    with open(os.path.join(OUT, "wanted.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(wanted, f, indent=1, ensure_ascii=False)
    out, n, w = build_site.build(OUT, issues="local", upload="", credit=CREDIT, title="Game Boy cartridge labels", text=TEXT)
    print(f"{n} labels, {w} missing: open {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
