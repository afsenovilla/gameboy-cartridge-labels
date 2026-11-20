# screenscraper_site: the catalogue of every label, for browsing them locally: build_site's page (the same as for the
# restored labels) over ScreenScraper's label images, plus geon's restored labels of the cartridges ScreenScraper has
# no image of, and a Missing list: the database's releases with no label image at all. Run after screenscraper_match.py:
#   python run.py py src/screenscraper_site.py [--only-screenscraper]      ->  screenscraper-labels/index.html
# Each distinct image is a label: its serial (what screenscraper_match read on it, when it read one), the release's
# title if the serial is known, else ScreenScraper's name for the game, its system. Regions come from the serial, as on
# the main page; an image with no serial read shows as region "other". Images in ignore.txt, or of games left out, are
# not there (screenscraper_match never matched them). Writes screenscraper-labels/labels.json and wanted.json (Missing),
# which build_site reads.
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


RESTORED = os.path.join("published-labels", "labels.json")
GROUP = {"USA": "USA", "CAN": "USA", "JPN": "JPN", "KOR": "KOR", "CHN": "CHN"}
LETTER = {"J": "JPN", "E": "USA", "P": "EUR", "D": "NOE", "F": "FRA", "S": "ESP", "I": "ITA", "K": "KOR", "X": "EUR",
          "Y": "EUR", "U": "AUS", "H": "HOL", "C": "CHN"}
TEXT = {"heading": "Game Boy cartridge labels", "labelsTab": "Labels", "wantedTab": "Missing", "photos": False,
        "labelsLede": "Labels of Game Boy, Game Boy Color and Game Boy Advance cartridges, from ScreenScraper and from "
                      "geon's restorations. Search by title or serial, then open one to see it large.",
        "wantedLede": " cartridges the database knows have no label image yet: a straight, well-lit photo or scan of "
                      "the label would complete them."}


def restored(ss_labels, path=RESTORED, folder="published-labels"):
    """geon's restored labels of the serials (and releases) ScreenScraper has no image of, as entries of this page."""
    if not os.path.exists(path):
        return []
    have = {l["serial"] for l in ss_labels if l["serial"]} | {l["release"] for l in ss_labels if l["release"]}
    out = []
    for e in json.load(open(path, encoding="utf-8")):
        if e.get("serial") in have or (e.get("release") and e["release"] in have and not e.get("serial")):
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


def missing(entries, releases):
    """The database's releases no label of this page is of: the page's Missing list, by title."""
    have = {e["release"] for e in entries if e.get("release")} | {e["serial"] for e in entries if e.get("serial")}
    have |= {e["serial"].rsplit("-", 1)[0] for e in entries if e.get("serial", "").count("-") >= 2}
    out = []
    for r in releases.values():
        if r["id"] in have or any(s in have for s in r.get("cartridgeSerials") or []):
            continue
        region = region_of(r)
        serial_list = list(r.get("cartridgeSerials") or []) or [r["id"]]
        system = (r.get("system") or "")[:3].lower()
        query = " ".join(w for w in (r.get("title") or "", {"dmg": "Game Boy", "cgb": "Game Boy Color", "agb": "Game Boy Advance"}.get(system, ""),
                                     "Japan" if region == "JPN" else "", "cartridge") if w)
        out.append({"print": r["id"], "release": r["id"], "title": r.get("title") or r["id"], "system": system,
                    "region": GROUP.get(region, "USA/EUR" if region not in ("other",) else "other"),
                    "serials": serial_list, "needed": 1, "photos": 0,
                    "search": [{"label": "eBay", "url": "https://www.ebay.com/sch/i.html?" + urllib.parse.urlencode({"_nkw": query})}]
                              + [{"label": f"Google Images: {s}", "url": "https://www.google.com/search?" + urllib.parse.urlencode({"tbm": "isch", "q": f'"{s}"'})}
                                 for s in serial_list]})
    return sorted(out, key=lambda w: (w["title"].casefold(), w["print"]))


def main(args):
    with open(os.path.join(OUT, "matches.json"), encoding="utf-8") as f:
        matches = json.load(f)
    entries = labels(matches, dl.ignored())
    for e in entries:
        e["source"] = f"ScreenScraper (game {e.pop('screenscraper')})"
    if "--only-screenscraper" not in args:
        entries += restored(entries)
    releases = {}
    if os.path.exists(serials.DATABASE):
        for r in json.load(open(serials.DATABASE, encoding="utf-8")):
            releases[r["id"]] = r
    wanted = missing(entries, releases)
    with open(os.path.join(OUT, "labels.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(entries, f, indent=1, ensure_ascii=False)
    with open(os.path.join(OUT, "wanted.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(wanted, f, indent=1, ensure_ascii=False)
    out, n, w = build_site.build(OUT, upload="", credit=CREDIT, title="Game Boy cartridge labels", text=TEXT)
    print(f"{n} labels, {w} missing: open {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
