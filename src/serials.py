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


# Near serials: OCR garbles or cuts off serials (B-B96J-JPN, COB-B96J-JPN, GAB-896J-JPN for CGB-B96J-JPN). A code with a
# known region and up to 3 characters before it for the platform, compared with the database's serials of that region:
# the code by an edit distance where look-alikes cost half, plus half if the platform isn't read exactly (garbled, cut
# off or missing).
LOOK_ALIKE = [set("8B"), set("0OD"), set("1IL"), set("5S"), set("6G"), set("2Z"), set("UV")]
NEAR = re.compile(r"(?<![A-Z0-9])([A-Z0-9]{0,3})-?([A-Z0-9]{2,5})-?(" + "|".join(REGIONS) + r")(?![A-Z])")
NEAR_MAX = 1.0     # the most a near serial may cost
NEAR_MARGIN = 1.0  # by how much the second best must cost more
PLATFORM_COST = 0.5


def _sub(a, b):
    return 0 if a == b else 0.5 if any(a in s and b in s for s in LOOK_ALIKE) else 1


def edit_cost(a, b):
    """Edit distance, look-alike substitutions costing half."""
    d = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(b) + 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + _sub(a[i - 1], b[j - 1]))
    return d[-1]


def near_cost(platform, code, serial_platform, serial_code):
    return edit_cost(code, serial_code) + (0 if platform == serial_platform else PLATFORM_COST)


def by_region(release_of):
    """Region -> [(platform, code, the serial)] of the database's serials, for near serials."""
    out = {}
    for s in release_of:
        m = re.fullmatch(r"(DMG|CGB|AGB)-([A-Z0-9]{1,5})-([A-Z]{3})", s)
        if m:
            out.setdefault(m.group(3), []).append((m.group(1), m.group(2), s))
    return out


def near(text, regions):
    """The near serials in a line of text (regions: by_region()): [(the database serial, cost, what was read)], only
    where the best costs at most NEAR_MAX and clearly less than the second best; exact reads are left to reads()."""
    t = unicodedata.normalize("NFKC", text).upper()
    t = re.sub(r"[ー―–—一:・.]", "-", t)
    found = []
    for u in dict.fromkeys((t, t.replace(" ", ""))):
        for m in NEAR.finditer(u):
            costs = sorted((near_cost(m.group(1), m.group(2), p, c), s) for p, c, s in regions.get(m.group(3), []))
            if costs and 0 < costs[0][0] <= NEAR_MAX and (len(costs) == 1 or costs[1][0] >= costs[0][0] + NEAR_MARGIN):
                found.append((costs[0][1], costs[0][0], m.group(0)))
    return list(dict.fromkeys(found))
