import glob, json, os, re, unicodedata
from difflib import SequenceMatcher

# The serial on each photo's label, for add-photos: the serial-like strings in its text (src/text.py)
# matched against gb-game-list's serials: "exact", "near" (one character off, e.g. DMG-UKJ for DMG-HKJ, with a single
# closest serial), or "unknown" (a serial-like read that matches nothing: a misread, or a serial missing from the list);
# "none" when nothing serial-like was read. O and 0, I and 1 are tried both ways. Early Japanese labels print the serial
# without its region (DMG-KGA), which gb-game-list may only list in full (DMG-KGA-JPN): a release's id and game id count
# as its serials too. A misread can be another release's serial (DMG-UKJ, Yu Yu Hakusho, for DMG-HKJ, Hokuto no Ken), so
# the matched release's titles are looked for in the photo's text: "title" when some run of 4 characters (3 for short
# titles; letters and kana alike) of one was read, and a "near" match only counts with its title read; without it, the
# read is "unknown". The text is normalized first: full-width characters, dashes read as ー, – or :, and spaces dropped
# (vertical text on the strips is read with gaps, "DMG-Z G-NOE"), and also kept, for text after the serial ("DMG-PVJ
# MADE IN JAPAN"). A region code read without its dash (AGB・A20JJPN for AGB-A2OJ-JPN) is read too, for the known region
# codes, and every read with a region also without it, as gb-game-list lists some serials only so (AGB-A2OJ).
# Where gb-game-list's database is: next to this repository, or wherever GB_GAME_LIST says.
# Without it, this repository's own partial catalog (make catalog, src/build_catalog.py).
RELEASES = os.path.join(os.environ.get("GB_GAME_LIST", os.path.join("..", "gb-game-list")), "database", "releases.json")
OWN_CATALOG = os.path.join("catalog", "releases.json")
if not os.path.exists(RELEASES) and os.path.exists(OWN_CATALOG):
    RELEASES = OWN_CATALOG
RANK = {"exact": 0, "near": 1, "unknown": 2}
REGIONS = ("ASI", "AUS", "BRA", "CAN", "CHN", "DAN", "ESA", "ESP", "EUB", "EUR", "EUU", "FAH", "FRA", "FRG", "GPS", "HKG",
           "HOL", "ITA", "JPG", "JPN", "KOR", "MSA", "NOE", "SCN", "SPA", "UKV", "USA")
SERIAL = re.compile(r"(DMG|CGB|AGB)-?([A-Z0-9]{1,5})(?:-([A-Z]{3}))?(?:-([0-9]))?")
NO_DASH = re.compile(r"(DMG|CGB|AGB)-?([A-Z0-9]{1,5})(" + "|".join(REGIONS) + r")(?:-([0-9]))?")


def without_region(serial):
    """A serial without its region: DMG-HKJ-JPN -> DMG-HKJ; DMG-HKJ stays (its last letters are its code, not a region)."""
    return re.sub(r"^([A-Za-z]{3}-[^-]+)-[A-Z]{3}$", r"\1", serial)


def known_from_photos():
    """Without gb-game-list: releases made from the photos' names, one per serial without its region, with no titles. A
    read can then only match a serial already in photos/, and nothing checks the names themselves."""
    import photos
    found = {}
    for _, _, name, _ in photos.all_sources():
        serial = photos.serial_of(name)
        if re.match(r"(DMG|CGB|AGB)-", serial):
            id = without_region(serial)
            release = found.setdefault(id, {"id": id, "gameId": id, "title": "(gb-game-list missing)", "titles": [], "cartridgeSerials": []})
            if serial not in release["cartridgeSerials"]:
                release["cartridgeSerials"].append(serial)
    return [found[k] for k in sorted(found)]


def releases_by_serial():
    """Each serial in gb-game-list, and each release's id and game id, -> its release."""
    if os.path.exists(RELEASES):
        releases = json.load(open(RELEASES, encoding="utf-8"))
    else:
        print(f"warning: {RELEASES} not found (put gb-game-list there, or set GB_GAME_LIST): using only the serials in photos/'s names", flush=True)
        releases = known_from_photos()
    release_of = {}
    for r in releases:
        for s in r["cartridgeSerials"]:
            release_of.setdefault(s, r)
    for key in ("id", "gameId"):  # a release's own id before another's game id (DMG-AVBJ, not DMG-AVBE of game DMG-AVBJ)
        for r in releases:
            release_of.setdefault(r[key], r)
    return release_of


def reads(text):
    """The serial-like strings in a line of text."""
    t = unicodedata.normalize("NFKC", text).upper()
    t = re.sub(r"[ー―–—:・.]", "-", t)
    found = []
    for u in (t.replace(" ", ""), t):
        for m in [*SERIAL.finditer(u), *NO_DASH.finditer(u)]:
            found.append("-".join(p for p in m.groups() if p))
            if m.group(3):
                found.append(f"{m.group(1)}-{m.group(2)}")
    return found


def distance(a, b):
    row = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, cb in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (ca != cb))
    return row[-1]


def match(found, release_of):
    prefix, rest = found[:4], found[4:]
    for variant in (rest, rest.replace("0", "O"), rest.replace("O", "0"), rest.replace("1", "I"), rest.replace("I", "1")):
        if prefix + variant in release_of:
            return "exact", prefix + variant
    near = [s for s in release_of if s[:3] == found[:3] and abs(len(s) - len(found)) <= 1 and distance(s, found) == 1]
    return ("near", near[0]) if len(near) == 1 else ("unknown", found)


def plain(text):
    return re.sub(r"[^0-9A-Z぀-ヿ一-鿿]", "", unicodedata.normalize("NFKC", text).upper())


def title_seen(release, text):
    """Whether some run of characters of one of the release's titles was read in text."""
    for t in release["titles"]:
        t = plain(t["title"])
        need = min(4, max(3, len(t) // 2))
        if len(t) >= need and SequenceMatcher(None, t, text, autojunk=False).find_longest_match(0, len(t), 0, len(text)).size >= need:
            return True
    return False


def serials(text_dir):
    """The serial on each photo's label, from its text in text_dir (src/text.py): rows of photo, status, serial, release
    id, title, whether the title was read too ("title"), and the serial-like strings found (space-separated)."""
    release_of = releases_by_serial()
    rows = []
    for path in sorted(glob.glob(os.path.join(text_dir, "*.json"))):
        name = os.path.basename(path)[:-5]
        lines = [l["text"] for l in json.load(open(path, encoding="utf-8"))]
        found = sorted({r for line in lines for r in reads(line)})
        if not found:
            rows.append((name, "none", "", "", "", "", ""))
            continue
        label = plain(" ".join(lines))
        matches = []
        for r in found:
            status, serial = match(r, release_of)
            if status == "near" and not title_seen(release_of[serial], label):
                status, serial = "unknown", r
            matches.append((status, serial))
        # The longest of the best-matching reads (DMG-AJYJ-JPN rather than DMG-AJYJ).
        status, serial = min(matches, key=lambda m: (RANK[m[0]], -len(m[1])))
        r = release_of.get(serial)
        seen = "title" if r and title_seen(r, label) else ""
        rows.append((name, status, serial, r["id"] if r else "", r["title"] if r else "", seen, " ".join(found)))
    return rows
