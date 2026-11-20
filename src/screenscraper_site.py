# screenscraper_site: the browsing page (build_site's, the same as for the restored labels) over ScreenScraper's label
# images instead: screenscraper-labels/index.html, for looking at them locally. Run after screenscraper_match.py:
#   python run.py py src/screenscraper_site.py
# Each distinct image is a label: its serial (what screenscraper_match read on it, when it read one), the release's
# title if the serial is known, else ScreenScraper's name for the game, its system. Regions come from the serial, as on
# the main page; an image with no serial read shows as region "other". Images in ignore.txt, or of games left out, are
# not there (screenscraper_match never matched them). Writes screenscraper-labels/labels.json, which build_site reads.
# ScreenScraper's images, for local use: don't publish this page.
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_site
import screenscraper_download as dl

OUT = "screenscraper-labels"
SYSTEMS = {"gb": "dmg", "gbc": "cgb", "gba": "agb"}
SERIAL_SYSTEM = {"DMG": "dmg", "CGB": "cgb", "AGB": "agb"}
CREDIT = ('Label images from <a href="https://www.screenscraper.fr/">ScreenScraper</a>, matched to serials by reading '
          'the text on them. For local use: not to publish.')


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


def main():
    with open(os.path.join(OUT, "matches.json"), encoding="utf-8") as f:
        matches = json.load(f)
    entries = labels(matches, dl.ignored())
    with open(os.path.join(OUT, "labels.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(entries, f, indent=1, ensure_ascii=False)
    out, n, _ = build_site.build(OUT, credit=CREDIT, title="ScreenScraper labels")
    print(f"{n} labels: open {out}")


if __name__ == "__main__":
    main()
