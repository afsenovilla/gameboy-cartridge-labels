"""Cartridge photos from eBay searches, for releases no label photo has.

The searches run inside an eBay tab (driven through the Claude in Chrome extension); this script makes the
query list and takes in the search results, downloading each listing's first photo at eBay's largest size.

    python3 src/ebay_photos.py queries USA > queries.json
    python3 src/ebay_photos.py ingest results.json queries.json

Photos go to save-new-images-here/ebay-search/ with a listing.json there, for make add-photos.
ebay-photos/sources.json: one record per downloaded file (kept, or deleted by hand afterwards: never downloaded again) (release, query, listing, image URL, size, date).
ebay-photos/searches.json: every release searched, so a run can be stopped and resumed.
"""
import datetime
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import serials  # noqa: E402

OUT = os.environ.get("EBAY_OUT", "ebay-photos")  # the downloader's own records
DROP = os.environ.get("EBAY_DROP", "save-new-images-here/ebay-search")  # the photos, for make add-photos
LISTING = os.path.join(DROP, "listing.json")
SOURCES = os.path.join(OUT, "sources.json")
SEARCHES = os.path.join(OUT, "searches.json")
MISSING = "generated/read-serials/missing.json"
PER_RELEASE = 5
MIN_SIDE = 1000  # px, longest side
OTHER_REGIONS = {  # listing titles naming another region than the release's
    "USA": r"\b(japan|japanese|jpn|jp|ntsc-j|pal|eur|europe|european|uk|german|deutsch|french|fran[cç]ais|spanish|italian|import|chinese|korean)\b|AGB-P-\w{3}[^E\W]"}
SYSTEM = {"agb": "GBA", "cgb": "Game Boy Color", "dmg": "Game Boy"}
OTHER_SYSTEMS = {"agb": r"\b(gbc|game ?boy colou?r|nds|ds|3ds|psp|gamecube|sega)\b",  # listing titles naming another system
                 "cgb": r"\b(gba|advance|nds|ds|3ds|psp|n64|sega)\b", "dmg": r"\b(gba|advance|nds|ds|3ds|psp|n64|sega)\b"}


def load(path):
    return json.load(open(path)) if os.path.exists(path) else {}


def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def query_title(title):
    t = re.sub(r"^(.*), (The|A|An)( - |$)", r"\2 \1\3", title)
    return re.sub(r"\s+", " ", t.replace(" - ", " ")).strip()


def queries(region):
    db = json.load(open(serials.DATABASE))
    missing = set(json.load(open(MISSING)))
    searched = load(SEARCHES)
    out = []
    for r in db:
        if r["id"] not in missing or r["id"] in searched:
            continue
        cart = [s for s in r.get("cartridgeSerials", []) if s.endswith("-" + region)]
        if not cart:
            continue
        out.append({"release": r["id"], "serial": cart[0], "title": r["title"],
                    "query": f"{query_title(r['title'])} {SYSTEM[r['system']]} cartridge",
                    "exclude": OTHER_SYSTEMS[r["system"]]})
    return out


def size(path):
    o = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", path], capture_output=True, text=True).stdout
    w, h = (int(re.search(rf"{k}: (\d+)", o).group(1)) for k in ("pixelWidth", "pixelHeight"))
    return [w, h]


def ingest(results_file, queries_file):
    """results: {release: [{item, title, image}]}, items already filtered and ranked in the eBay tab."""
    sources, searches = load(SOURCES), load(SEARCHES)
    query_of = {q["release"]: q for q in json.load(open(queries_file))}
    have_items = {v["listing"].rsplit("/", 1)[1] for v in sources.values()}
    today = datetime.date.today().isoformat()
    for release, items in json.load(open(results_file)).items():
        res = dict(query_of[release], items=items)
        if res["release"] in searches:
            continue
        kept, small = 0, 0
        other_region = re.compile(OTHER_REGIONS[res["serial"].rsplit("-", 1)[1]], re.I)
        for it in res["items"]:
            if other_region.search(it["title"]):
                continue
            if kept >= PER_RELEASE:
                break
            if it["item"] in have_items:
                continue
            name = f"ebay-{it['item']}.jpg"
            os.makedirs(DROP, exist_ok=True)
            path = os.path.join(DROP, name)
            url = f"https://i.ebayimg.com/images/g/{it['image']}/s-l1600.jpg"
            if subprocess.run(["curl", "-sSf", "-o", path, url]).returncode != 0:
                continue
            time.sleep(1)
            wh = size(path)
            if max(wh) < MIN_SIDE:
                os.remove(path)
                small += 1
                continue
            sources[name] = {"release": res["release"], "serial": res["serial"], "query": res["query"],
                             "listing": f"https://www.ebay.com/itm/{it['item']}", "listing_title": it["title"],
                             "image": url, "size": wh, "fetched": today}
            listing = load(LISTING)
            listing[name] = {"page_url": sources[name]["listing"], "image_url": url, "title_on_page": it["title"],
                             "searched_release": res["release"], "searched_serial": res["serial"],
                             "query": res["query"], "fetched": today}
            save(LISTING, listing)
            have_items.add(it["item"])
            kept += 1
        searches[res["release"]] = {"query": res["query"], "candidates": len(res["items"]), "kept": kept,
                                    "too_small": small, "date": today}
        save(SOURCES, sources)
        save(SEARCHES, searches)
        print(res["release"], len(res["items"]), "candidates,", kept, "kept,", small, "too small", flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "queries":
        json.dump(queries(sys.argv[2]), sys.stdout, ensure_ascii=False)
    elif sys.argv[1] == "ingest":
        ingest(sys.argv[2], sys.argv[3])
