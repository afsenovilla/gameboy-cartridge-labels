# gbdb_fetch: cartridge photos from game-boy-database.com for the Game Boy labels the catalogue lacks, into the
# review inbox (screenscraper-labels/inbox/), where each is straightened, its serial read, and accepted or rejected.
# Run it from the repository folder, with or without serve_catalogue.py running:
#   python run.py py src/gbdb_fetch.py [--limit 100] [--missing-only] [--refresh] [--dry-run]
# game-boy-database.com lists every original Game Boy release by region (fullset-EUR.html, fullset-NOE.html...), each
# a page game-<code>-<id>-<region>.html (game-ACDX-453-EUR.html is DMG-ACDX-EUR), with its cartridge photo at
# cartridges/<id>.jpg. Unlike LaunchBox it goes by serial, so a photo is of the serial it's fetched for. This reads
# the region lists (kept a week in screenscraper-labels/gbdb/, again with --refresh) and fetches the photos of every
# serial the catalogue has no label of: the Missing ones and the variants the database doesn't list
# (--missing-only: just the Missing ones). At most PER_SERIAL photos a serial (a release can have several pages);
# --limit N downloads at most N photos per run, one a second; what's been fetched is remembered in
# screenscraper-labels/gbdb.json, so running it again carries on. The photos are the site's members': local use only.
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

OUT = "screenscraper-labels"
CACHE = os.path.join(OUT, "gbdb")
STATE = os.path.join(OUT, "gbdb.json")
INBOX = os.path.join(OUT, "inbox")
SITE = "https://www.game-boy-database.com/"
AGENT = "gameboy-cartridge-labels (local catalogue; github.com/afsenovilla/gameboy-cartridge-labels)"
REGIONS = ["ASI", "AUS", "BRAZIL", "CAN", "CHN", "ESP", "EUR", "FAH", "FRA", "FRG", "GPS", "HOL", "ITA", "JPN",
           "KOR", "NOE", "SCN", "UKV", "USA", "EUU", "NEU6"]
PER_SERIAL = 2
PAGE = re.compile(r"game-([A-Z0-9]{2,5})-(\d+)-([A-Z0-9]{3,6}(?:-\d)?)\.html")


def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def releases(html):
    """[(serial, page id)] in a region list: game-ACDX-453-EUR.html -> ("DMG-ACDX-EUR", "453"). Old Japanese
    releases print no region on the label (DMG-K2J), but the site still files them under JPN."""
    out, seen = [], set()
    for code, pid, region in PAGE.findall(html):
        serial = f"DMG-{code}-{region}"
        if (serial, pid) not in seen:
            seen.add((serial, pid))
            out.append((serial, pid))
    return out


def region_list(region, refresh=False, log=print):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"fullset-{region}.html")
    fresh = os.path.exists(path) and time.time() - os.path.getmtime(path) < 7 * 86400
    if not fresh or refresh:
        try:
            data = get(f"{SITE}fullset-{region}.html")
        except Exception as e:
            log(f"  fullset-{region}: {e}")
            return []
        with open(path, "wb") as f:
            f.write(data)
        time.sleep(1)
    return releases(open(path, encoding="utf-8", errors="replace").read())


def same(a, b):
    """The site's serial and the catalogue's: equal, or an old Japanese one without its region (DMG-K2J-JPN = DMG-K2J)."""
    strip = lambda s: s[:-4] if s.endswith("-JPN") and len(s.split("-")[1]) <= 3 else s
    return a == b or strip(a) == strip(b)


def todo(found, have, missing, missing_only=False, fetched=frozenset()):
    """[(serial, page id, why)] to fetch: serials with no label in the catalogue, Missing ones first."""
    have_n = {s[:-4] if s.endswith("-JPN") and len(s.split("-")[1]) <= 3 else s for s in have}
    miss_n = {s[:-4] if s.endswith("-JPN") and len(s.split("-")[1]) <= 3 else s: s for s in missing}
    out, per = [], {}
    for serial, pid in found:
        key = serial[:-4] if serial.endswith("-JPN") and len(serial.split("-")[1]) <= 3 else serial
        if key in have_n:
            continue
        why = "missing" if key in miss_n else "variant"
        if missing_only and why != "missing":
            continue
        name = miss_n.get(key, serial)  # the catalogue's spelling, for the review's hint
        per[name] = per.get(name, 0) + 1
        if per[name] <= PER_SERIAL and pid not in fetched:
            out.append((name, pid, why))
    out.sort(key=lambda x: x[2] != "missing")
    return out


def main(args):
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else 100
    labels_path, wanted_path = os.path.join(OUT, "labels.json"), os.path.join(OUT, "wanted.json")
    if not os.path.exists(labels_path) or not os.path.exists(wanted_path):
        sys.exit("No screenscraper-labels/labels.json or wanted.json: run src/screenscraper_site.py first.")
    have = {e["serial"] for e in json.load(open(labels_path, encoding="utf-8")) if e.get("serial")}
    missing = {e["print"] for e in json.load(open(wanted_path, encoding="utf-8")) if (e.get("print") or "").startswith("DMG")}
    state = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else {"fetched": {}}
    found = []
    for region in REGIONS:
        found += region_list(region, "--refresh" in args)
    print(f"{len({s for s, _ in found})} Game Boy serials on game-boy-database.com.")
    jobs = todo(found, have, missing, "--missing-only" in args, set(state["fetched"]))
    print(f"{sum(1 for j in jobs if j[2] == 'missing')} photos for Missing cartridges, "
          f"{sum(1 for j in jobs if j[2] == 'variant')} for variants the catalogue has no label of, not fetched yet.")
    if "--dry-run" in args:
        for serial, pid, why in jobs[:limit]:
            print(f"  {serial}  [{why}]  {SITE}cartridges/{pid}.jpg")
        return
    os.makedirs(INBOX, exist_ok=True)
    done = 0
    for serial, pid, why in jobs[:limit]:
        try:
            data = get(f"{SITE}cartridges/{pid}.jpg")
        except urllib.error.HTTPError as e:  # no cartridge photo on that page
            state["fetched"][pid] = {"serial": serial, "error": e.code}
            data = None
        except Exception as e:
            print(f"  skipped {serial} ({pid}): {e}")
            data = None
        if data and data[:3] == b"\xff\xd8\xff":
            name = f"{serial}__gbdb_{pid}.jpg"  # the serial in the name is the review's hint
            with open(os.path.join(INBOX, name + ".part"), "wb") as f:
                f.write(data)
            os.replace(os.path.join(INBOX, name + ".part"), os.path.join(INBOX, name))
            state["fetched"][pid] = {"serial": serial, "file": name}
            done += 1
            print(f"  [{done}] {serial}  [{why}]")
        elif data:
            state["fetched"][pid] = {"serial": serial, "error": "not a photo"}
        with open(STATE + ".tmp", "w", encoding="utf-8", newline="\n") as s:
            json.dump(state, s, indent=1, ensure_ascii=False)
        os.replace(STATE + ".tmp", STATE)
        time.sleep(1)
    left = max(0, len(jobs) - limit)
    print(f"{done} photos put in screenscraper-labels/inbox/ for review"
          + (f" ({left} left: run it again)." if left else ": nothing left to fetch from game-boy-database.com."))


if __name__ == "__main__":
    main(sys.argv[1:])
