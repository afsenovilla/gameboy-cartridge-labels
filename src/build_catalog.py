import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photos, serials

# catalog: catalog/releases.json, the releases known, for when gb-game-list isn't there (src/serials.py), in its format,
# each with where it's known from ("sources"), best first:
# - "gbdb": gbdb.org's part numbers (catalog/sources/gbdb.txt: title, part number, publisher, date, variants), almost all North American: a serial confirmed elsewhere;
# - "label": a serial read on a photo's label and agreeing with the photo's name: seen, on Japanese releases mostly, but
#   confirmed only by that one reading;
# - "name": a serial only in a photo's name: nothing confirms it.
# Titles come from gbdb.org, or else from gb-rom-database (No-Intro's names, MIT: catalog/sources/gb-rom-database.json), by
# the four-letter code in a game's header, which only part of the games have: "title_source" says which, and such a title
# may be wrong. This catalog is partial: it can't say which Japanese or European releases are missing.
# Usage: build_catalog.py
OUT = "catalog/releases.json"
GBDB = "catalog/sources/gbdb.txt"
ROMS = "catalog/sources/gb-rom-database.json"
SERIAL = re.compile(r"^(DMG|CGB)-[A-Z0-9]{1,5}(-[A-Z]{3})?(-\d)?$")
RANK = {"gbdb": 0, "label": 1, "name": 2}


def base(serial):
    """A serial without its variant number and region: DMG-NY-USA-1 -> DMG-NY."""
    return serials.without_region(re.sub(r"-\d$", "", serial))


def rom_titles(games):
    """Each four-letter header code -> the game's name, without No-Intro's tags; prototypes and the like left out."""
    found = {}
    for g in games:
        code = g.get("manufacturer_code", "").strip().upper()
        if re.fullmatch(r"[A-Z0-9]{4}", code) and not re.search(r"\((Proto|Beta|Demo|Sample|Unl|Pirate|Aftermarket)", g["name"]):
            found.setdefault(code, re.sub(r"\s*\(.*$", "", g["name"]))
    return found


def build(gbdb, roms, named):
    """The releases, from gbdb.org's rows ({"t", "s", "p", "d", "v"}), the ROMs' codes, and (serial, read on its label) of
    the photos."""
    releases = {}

    def add(serial, source, title=None, publisher=None, date=None):
        if not SERIAL.match(serial):
            return
        serial = re.sub(r"-\d$", "", serial)
        r = releases.setdefault(base(serial), {"id": base(serial), "gameId": base(serial), "title": "", "titles": [], "cartridgeSerials": [], "sources": []})
        if serial not in r["cartridgeSerials"]:
            r["cartridgeSerials"].append(serial)
        if source not in r["sources"]:
            r["sources"].append(source)
        if title and not r["title"]:
            r.update(title=title, titles=[{"title": title}], title_source="gbdb")
        if publisher:
            r.setdefault("publisher", publisher)
        if date:
            r.setdefault("date", date)

    for row in gbdb:
        for serial in [s for s in [row.get("s", "")] + row.get("v", []) if s]:
            add(serial, "gbdb", row.get("t"), row.get("p"), row.get("d"))
    for serial, read in named:
        add(serial, "label" if read and base(read) == base(serial) else "name")
    for r in releases.values():
        r["sources"].sort(key=RANK.get)
        code = r["id"].split("-")[1]
        if not r["title"] and code in roms:
            r.update(title=roms[code], titles=[{"title": roms[code]}], title_source="gb-rom-database")
    return [releases[k] for k in sorted(releases)]


if __name__ == "__main__":
    gbdb = []
    with open(GBDB, encoding="utf-8") as f:
        for line in f:
            t, s, p, d, v = line.rstrip("\n").split("|")
            gbdb.append({"t": t, "s": s, "p": p, "d": None if d.startswith("00/") else d, "v": v.split()})
    with open(ROMS, encoding="utf-8") as f:
        roms = rom_titles(json.load(f))
    named = [(photos.serial_of(n), e.get("serial_on_label")) for s, _, n, e in photos.all_sources() if s not in photos.FAKES]
    releases = build(gbdb, roms, named)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("[\n" + ",\n".join(json.dumps(r, ensure_ascii=False) for r in releases) + "\n]\n")
    count = lambda test: sum(bool(test(r)) for r in releases)
    print(f"{len(releases)} releases: {count(lambda r: 'gbdb' in r['sources'])} from gbdb.org, {count(lambda r: r['sources'][0] == 'label')} only from labels, "
          f"{count(lambda r: r['sources'] == ['name'])} only from names; {count(lambda r: r['title'])} with a title, {count(lambda r: r.get('title_source') == 'gb-rom-database')} of them from ROM codes")
