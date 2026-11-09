# Serials: the serial-looking strings in a line of text (as OCR reads them: spaces, missing dashes, look-alike
# characters), and the database (gb-game-list's releases.json): which serials it knows, and their releases. Ported from
# main's src/serials.py.
import json, re, unicodedata

DATABASE = "../gb-game-list/database/releases.json"
PREFIXES = ("DIS",)  # DIS-CGB-AZ7E-USA
REGIONS = ("ASI", "AUS", "BRA", "CAN", "CHN", "DAN", "ESA", "ESP", "EUB", "EUR", "EUU", "FAH", "FRA", "FRG", "GPS", "HKG",
           "HOL", "ITA", "JPG", "JPN", "KOR", "MSA", "NOE", "SCN", "SPA", "UKV", "USA")
PREFIX = r"(?:(" + "|".join(PREFIXES) + r")-?)?"
SERIAL = re.compile(PREFIX + r"(DMG|CGB|AGB)-?([A-Z0-9]{1,5})(?:-([A-Z]{3}))?(?:-([0-9]))?")
NO_DASH = re.compile(PREFIX + r"(DMG|CGB|AGB)-?([A-Z0-9]{1,5})(" + "|".join(REGIONS) + r")(?:-([0-9]))?")


def reads(text):
    """The serial-looking strings in a line of text, upper case, dashed (a region read without its dash too); a serial
    with a region also without it."""
    t = unicodedata.normalize("NFKC", text).upper()
    t = re.sub(r"[ー―–—一:・.]", "-", t)
    t = re.sub(r"\bOMG(?=-)", "DMG", t)
    found = []
    for u in (t.replace(" ", ""), t):
        for m in [*SERIAL.finditer(u), *NO_DASH.finditer(u)]:
            found.append("-".join(p for p in m.groups() if p))
            if m.group(4):
                found.append("-".join(p for p in m.groups()[:3] if p))
    return list(dict.fromkeys(found))


def load_database(path=DATABASE):
    """Each serial the database knows (its cartridges' serials, its releases' ids and game ids) -> its release."""
    releases = json.load(open(path))
    release_of = {}
    for r in releases:
        for s in r["cartridgeSerials"]:
            release_of.setdefault(s, r)
    for key in ("id", "gameId"):  # a release's own id before another's game id
        for r in releases:
            release_of.setdefault(r[key], r)
    return release_of


def release(serial, release_of):
    """The database's release of a serial (its prefix dropped; its region dropped if the database lacks it), or None."""
    s = re.sub(r"^(" + "|".join(PREFIXES) + r")-", "", serial)
    for candidate in (s, re.sub(r"-[A-Z]{3}$", "", s)):
        if candidate in release_of:
            return release_of[candidate]
    return None
