# launchbox_fetch: cartridge photos from the LaunchBox Games Database for the catalogue's Missing cartridges, into
# the review inbox (screenscraper-labels/inbox/), where each is straightened, its serial read, and accepted or
# rejected by hand. Run it from the repository folder, with or without serve_catalogue.py running:
#   python run.py py src/launchbox_fetch.py [--limit 40] [--refresh] [--any-region] [--dry-run]
# LaunchBox has no API, but publishes its whole database as Metadata.zip (gamesdb.launchbox-app.com/Metadata.zip,
# refreshed daily): every game with its platform, names in other regions and images, each image with its type and
# region; images are at images.launchbox-app.com/<file name>. This downloads Metadata.zip once (again with
# --refresh, or when over a week old), keeps the Game Boy, Game Boy Color and Game Boy Advance games, and for each
# Missing cartridge (screenscraper-labels/wanted.json, made by screenscraper_site.py) finds the game by title and
# takes its "Cart - Front" photos of the cartridge's region (of any region with --any-region). They're matched by
# title and region only, not serial: the review reads the serial and says when it's not the one expected.
# --limit N downloads at most N photos per run (one a second); what's been downloaded is remembered in
# screenscraper-labels/launchbox.json, so running it again carries on. --dry-run only says what it would download.
# The images are LaunchBox users' uploads, for local use: don't publish them.
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET

OUT = "screenscraper-labels"
CACHE = os.path.join(OUT, "launchbox")
ZIP = os.path.join(CACHE, "Metadata.zip")
STATE = os.path.join(OUT, "launchbox.json")
INBOX = os.path.join(OUT, "inbox")
URL = "https://gamesdb.launchbox-app.com/Metadata.zip"
IMAGES = "https://images.launchbox-app.com/"
AGENT = "gameboy-cartridge-labels (local catalogue; github.com/afsenovilla/gameboy-cartridge-labels)"
PLATFORMS = {"nintendo game boy": "dmg", "nintendo game boy color": "cgb", "nintendo game boy advance": "agb"}
CART_TYPES = {"cart - front"}
PER_CARTRIDGE = 3
# a serial's region -> LaunchBox's regions its labels were sold in
REGIONS = {
    "USA": {"north america", "united states", "usa", "canada"}, "CAN": {"canada", "north america"},
    "JPN": {"japan"}, "KOR": {"korea", "south korea"}, "CHN": {"china"}, "AUS": {"australia", "oceania"},
    "EUR": {"europe"}, "EUU": {"europe", "united kingdom"}, "UKV": {"united kingdom", "europe"},
    "NOE": {"germany", "europe"}, "FRG": {"germany", "europe"}, "FRA": {"france", "europe"}, "FAH": {"france", "europe"},
    "ESP": {"spain", "europe"}, "SPA": {"spain", "europe"}, "ITA": {"italy", "europe"}, "HOL": {"netherlands", "europe"},
    "SCN": {"scandinavia", "sweden", "norway", "denmark", "finland", "europe"}, "DAN": {"denmark", "scandinavia", "europe"},
}


def plain(title):
    """A title for comparing: no accents, articles, punctuation or case ("Addams Family, The" = "The Addams Family")."""
    t = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r",\s*(the|a|an|le|la|les|der|die|das)\b", " ", t)
    t = re.sub(r"^(the|a|an|le|la|les|der|die|das)\s+", "", t.strip())
    t = t.replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "", t)


def text(el, *names):
    for n in names:
        v = el.findtext(n)
        if v is not None:
            return v.strip()
    return ""


def read_metadata(xml_file):
    """The Game Boy family's games: {database id: {"name", "system", "names": set, "images": [(file, type, region)]}}.
    Streamed, as the XML is big."""
    games, alternates, images = {}, [], []
    for _, el in ET.iterparse(xml_file, events=("end",)):
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "Game":
            system = PLATFORMS.get(text(el, "Platform").lower())
            gid = text(el, "DatabaseID", "DatabaseId", "ID")
            if system and gid:
                games[gid] = {"name": text(el, "Name"), "system": system, "names": {plain(text(el, "Name"))}, "images": []}
            el.clear()
        elif tag == "GameAlternateName":
            alternates.append((text(el, "DatabaseID", "DatabaseId"), text(el, "AlternateName", "Name")))
            el.clear()
        elif tag == "GameImage":
            images.append((text(el, "DatabaseID", "DatabaseId"), text(el, "FileName"), text(el, "Type").lower(), text(el, "Region").lower()))
            el.clear()
    for gid, name in alternates:
        if gid in games and name:
            games[gid]["names"].add(plain(name))
    for gid, file, kind, region in images:
        if gid in games and file:
            games[gid]["images"].append((file, kind, region))
    return games


def candidates(wanted, games, any_region=False):
    """[(missing entry, image file, region)] for the Missing cartridges whose game is found by title on its system."""
    by_name = {}
    for g in games.values():
        for n in g["names"]:
            if n:  # a title in Japanese script alone has no letters left: it would match every such game
                by_name.setdefault((g["system"], n), []).append(g)
    out, taken = [], set()
    for w in wanted:
        key = plain(w.get("title"))
        found = by_name.get((w.get("system"), key), []) if key else []
        serial = (w.get("serials") or [w.get("print")])[0] or ""
        parts = serial.split("-")
        fits = REGIONS.get(parts[2] if len(parts) > 2 else "", set())
        if not fits and len(parts) == 2 and parts[1].endswith("J"):
            fits = REGIONS["JPN"]  # an old Japanese serial with no region
        mine = []
        for g in found:
            for file, kind, region in g["images"]:
                if kind in CART_TYPES and file not in taken and (region in fits or (any_region and not fits) or (any_region and not region)):
                    mine.append((w, file, region))
        mine.sort(key=lambda x: 0 if x[2] in fits and x[2] != "europe" else 1)  # the cartridge's own country first
        for x in mine[:PER_CARTRIDGE]:  # one photo shared by two serials (Chuck Rock UKV and NOE) is downloaded once
            taken.add(x[1])
            out.append(x)
    return out


def download_metadata(refresh=False, log=print):
    os.makedirs(CACHE, exist_ok=True)
    old = os.path.exists(ZIP) and time.time() - os.path.getmtime(ZIP) > 7 * 86400
    if os.path.exists(ZIP) and not refresh and not old:
        return
    log("Downloading LaunchBox's Metadata.zip (about 100 MB)…")
    req = urllib.request.Request(URL, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(req, timeout=300) as r, open(ZIP + ".part", "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    os.replace(ZIP + ".part", ZIP)


def load_games(log=print):
    with zipfile.ZipFile(ZIP) as z:
        name = next(n for n in z.namelist() if n.lower().endswith("metadata.xml"))
        with z.open(name) as f:
            games = read_metadata(f)
    kinds = {}
    for g in games.values():
        for _, kind, _ in g["images"]:
            kinds[kind] = kinds.get(kind, 0) + 1
    log(f"{len(games)} Game Boy, Game Boy Color and Game Boy Advance games in LaunchBox; "
        f"{kinds.get('cart - front', 0)} cartridge photos.")
    return games


def safe(name):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[-80:]


def main(args):
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else 40
    wanted_path = os.path.join(OUT, "wanted.json")
    if not os.path.exists(wanted_path):
        sys.exit("No screenscraper-labels/wanted.json: run src/screenscraper_site.py first.")
    wanted = json.load(open(wanted_path, encoding="utf-8"))
    state = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else {"fetched": {}}
    download_metadata("--refresh" in args)
    games = load_games()
    found = candidates(wanted, games, "--any-region" in args)
    todo = [(w, f, r) for w, f, r in found if f not in state["fetched"]]
    print(f"{len({w['print'] for w, _, _ in found})} of {len(wanted)} Missing cartridges have a LaunchBox cartridge photo "
          f"({len(found)} photos, {len(todo)} not downloaded yet).")
    if "--dry-run" in args:
        for w, f, r in todo[:limit]:
            print(f"  {w['print']}  {w['title']}  [{r or 'no region'}]  {IMAGES}{f}")
        return
    os.makedirs(INBOX, exist_ok=True)
    done = 0
    for w, f, r in todo[:limit]:
        serial = (w.get("serials") or [w["print"]])[0]
        name = f"{serial}__launchbox_{safe(os.path.basename(f))}"  # the serial in the name is the review's hint
        try:
            req = urllib.request.Request(IMAGES + urllib.parse.quote(f), headers={"User-Agent": AGENT})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
        except Exception as e:
            print(f"  skipped {f}: {e}")
            state["fetched"][f] = {"serial": serial, "error": str(e)}
            continue
        with open(os.path.join(INBOX, name + ".part"), "wb") as out:
            out.write(data)
        os.replace(os.path.join(INBOX, name + ".part"), os.path.join(INBOX, name))
        state["fetched"][f] = {"serial": serial, "region": r, "file": name}
        done += 1
        print(f"  [{done}/{min(limit, len(todo))}] {serial}  {w['title']}  [{r or 'no region'}]")
        with open(STATE, "w", encoding="utf-8", newline="\n") as s:
            json.dump(state, s, indent=1, ensure_ascii=False)
        time.sleep(1)
    print(f"{done} photos put in screenscraper-labels/inbox/ for review ({max(0, len(todo) - done)} left: run it again).")


if __name__ == "__main__":
    main(sys.argv[1:])
