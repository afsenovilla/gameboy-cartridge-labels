import csv, html, json, os, pathlib, re, sys, unicodedata, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photos, serials

# search-photos: a local page of searches for photos of the Game Boy and Game Boy Color releases still without one: no
# cartridge photo in gb-game-list, and no photo in photos/ (a photo's release from match-serials, else from its name),
# whether or not its fit works. Releases with photos from otakaraou alone are listed apart: they are worth replacing.
# A table, one row per release, with a column per place to search:
# Google's and Bing's image searches, the stores of the eBay sellers elrocinante and Hit-Japan, Allegro (in its Game Boy
# category), and, for Japanese releases, Yahoo! Auctions through Jauce. Japanese releases are searched by their Japanese
# title, with ゲームボーイ and カセット on the image searches (listings there are titled in Japanese, rarely with the serial), the
# others by their English title, with "game boy" and cartridge; the eBay sellers and Allegro's sellers title their
# listings in English, so they get the English title alone. Long titles are cut at their subtitle. Last, Google Lens
# searches by image: with the release's cartridge photo from game-boy-database.com, and with its otakaraou photo (by the
# URLs they're found at, so Lens can fetch them). gb-game-list has only the box photos from game-boy-database.com; the
# cartridge's is next to it, by the same number (vizu/3741.jpg, cartridges/3741.jpg), for most games.
# Usage: search_photos.py
RELEASES = serials.RELEASES
SERIALS = "generated/match-serials/serials.tsv"
OUT = "generated/search-photos/index.html"
SYSTEMS = ("dmg", "cgb")
LENS = "https://lens.google.com/uploadbyurl?url="
# Allegro's category for each system, searched within.
ALLEGRO = {"dmg": "https://allegro.pl/kategoria/nintendo-game-boy-122237", "cgb": "https://allegro.pl/kategoria/nintendo-game-boy-122237",
           "agb": "https://allegro.pl/kategoria/nintendo-game-boy-advance-122234"}
# eBay's sellers: name shown, seller id, store name.
EBAY_SELLERS = (("elrocinante", "elrocinante119", "elrocinantesecondhandshop"), ("Hit-Japan", "hit-japan", "hitjapanvideogamesandanime"))


def short(title):
    """The title before its subtitle, if that leaves enough to search by."""
    t = unicodedata.normalize("NFKC", title).strip()
    head = re.split(r"\s+-\s+|\s{2,}|[~～〜:：「『]|\s(?=[(（])", t)[0].strip()
    return head if len(head) >= 3 else t


def japanese(release):
    return any(s.endswith("-JPN") for s in release["cartridgeSerials"]) or release["id"].endswith("J")


def japanese_title(release):
    return short(next((t["title"] for t in release["titles"] if "ja" in t["languages"]), release["title"]))


def links(release):
    """(label, url) for each place to search for the release's photos, None where there's nothing to search with."""
    q = lambda s: urllib.parse.quote(s)
    if japanese(release):
        title = japanese_title(release)
        image_query = f'"{title}" ゲームボーイ カセット'
    else:
        title = short(release["title"])
        image_query = f'"{title}" "game boy" cartridge'
    found = [("Google", "https://www.google.com/search?udm=2&q=" + q(image_query)),
             ("Bing", "https://www.bing.com/images/search?q=" + q(image_query))]
    found += [(f"eBay {name}", "https://www.ebay.com/sch/i.html?" + urllib.parse.urlencode({"_ssn": seller, "store_name": store, "_nkw": short(release["title"])}))
              for name, seller, store in EBAY_SELLERS]
    found.append(("Allegro", ALLEGRO[release["system"]] + "?string=" + q(short(release["title"]))))
    found.append(("Jauce", "https://www.jauce.com/search/" + urllib.parse.quote(f"{title} ゲームボーイ", safe="")) if japanese(release) else None)
    box = next((i["url"] for i in release["images"] if i["kind"] == "box"), None)
    found.append(("Lens game-boy-database", LENS + q(box.replace("/vizu/", "/cartridges/"))) if box else None)
    found.append(("Lens otakaraou", LENS + q(otakaraou[release["id"]])) if release["id"] in otakaraou else None)
    return found


releases = [r for r in json.load(open(RELEASES)) if r["system"] in SYSTEMS and r["cartridgeSerials"]]
release_of = serials.releases_by_serial()
matched = {row[0]: row[3] for row in csv.reader(open(SERIALS), delimiter="\t") if row[1] in ("exact", "near") and row[3]}
covered, otakaraou = set(), {}  # otakaraou: release -> the URL of its otakaraou photo
for source, _, name, entry in photos.all_sources():
    stem = photos.stem(name)
    release = matched.get(stem) or (release_of[photos.serial_of(stem)]["id"] if photos.serial_of(stem) in release_of else None)
    if release:
        if source == "otakaraou":
            otakaraou.setdefault(release, entry["image_url"])
        else:
            covered.add(release)
missing = [r for r in releases if r["id"] not in covered and not any(i["kind"] == "cartridgePhoto" for i in r["images"])]
replace = [r for r in missing if r["id"] in otakaraou]
missing = [r for r in missing if r["id"] not in otakaraou]

groups = [(f"{system_name}: {label}", [r for r in missing if r["system"] == system and japanese(r) == ja])
          for system, system_name in (("dmg", "Game Boy"), ("cgb", "Game Boy Color"))
          for ja, label in ((True, "Japanese releases"), (False, "Other releases"))]
groups.append(("Only from otakaraou: worth replacing", replace))
sections = []
for heading, group in groups:
    rows = []
    for r in sorted(group, key=lambda r: r["title"]):
        title = japanese_title(r) if japanese(r) else r["title"]
        searches = "".join(f'<td><a href="{html.escape(link[1])}" target="_blank">{link[0]}</a></td>' if link else "<td></td>" for link in links(r))
        rows.append(f'<tr><td>{html.escape(title)}</td><td><small title="{html.escape(r["title"])}">{html.escape(" ".join(r["cartridgeSerials"]))}</small></td>{searches}</tr>')
    sections.append(f"<h2>{heading} ({len(group)})</h2><table>{''.join(rows)}</table>")

page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Photo searches</title>
<style>body{{font:14px system-ui;margin:16px;background:#f4f4f4;color:#222}}table{{border-collapse:collapse}}
td{{padding:3px 8px;white-space:nowrap}}tr:nth-child(odd){{background:#fff}}small{{color:#888}}</style></head><body>
<h1>Photo searches</h1>
<p>{len(missing)} Game Boy and Game Boy Color releases without a cartridge photo in gb-game-list or in photos/, and
{len(replace)} with photos from otakaraou alone. Save the photos found in a subfolder of save-new-images-here/ named after where they came from, and file them with
make add-photos.</p>
{''.join(sections)}
</body></html>"""
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w").write(page)
print(f"{len(missing)} releases to search, {len(replace)} from otakaraou alone -> {pathlib.Path(OUT).resolve().as_uri()}")
