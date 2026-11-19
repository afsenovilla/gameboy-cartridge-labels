# screenscraper_download: the flat label images ("support-texture") ScreenScraper has for the cartridges in wanted.json, the ones
# still short of photos. Run it from the repository folder; it needs screenscraper.json (see screenscraper_sample.py).
#   python run.py py src/screenscraper_download.py [published-labels/wanted.json] [--limit N]
# Per cartridge: search the game by title on its system, take the label of the region the serial says (else Europe, else
# world, else any), save it to screenscraper-labels/<print id>.<ext> and note it in screenscraper-labels/index.json.
# Nothing here is a restoration: these are other people's images, usually 600 px wide where ours are 800+, and a match by title is
# a guess (the label's printed serial is the proof). They stay apart from the restored labels. Progress is kept in index.json, so a
# stopped run (the daily quota, say) carries on where it stopped; cartridges with no match are noted as such and not asked again.
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request

import screenscraper_sample as ss

OUT = "screenscraper-labels"
WANTED = os.path.join("published-labels", "wanted.json")
SYSTEM = {"dmg": "gb", "cgb": "gbc", "agb": "gba"}
# Nintendo's serial endings to ScreenScraper's regions, in the order to try; others end by their last letter.
REGIONS = {"USA": ["us"], "EUR": ["eu"], "SCN": ["eu"], "UKV": ["uk", "eu"], "NOE": ["de", "eu"], "FAH": ["fr", "eu"], "FRA": ["fr", "eu"],
           "ESP": ["sp", "eu"], "SPA": ["sp", "eu"], "ITA": ["it", "eu"], "HOL": ["nl", "eu"], "AUS": ["au", "eu"], "KOR": ["kr"],
           "CHN": ["cn"], "JPN": ["jp"]}


def folded(title):
    """A title for comparing: no accents, case or punctuation, and "Tetris, The" as "the tetris" without the article."""
    t = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"^(.*?),\s*(the|a|an)$", r"\1", t.strip())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", re.sub(r"^(the|a|an)\s+", "", t))).strip()


def regions_of(serials):
    """ScreenScraper regions to try for a print, from the endings of its serials, then Europe, world."""
    out = []
    for s in serials or []:
        end = s.split("-")[-1]
        out += REGIONS.get(end, ["jp"] if len(end) == 3 and end.endswith("J") else [])
    return out + ["eu", "wor", "us"]


def pick(images, regions):
    """The (region, url, format) of the first region wanted that there is an image for, else any; None if there is none."""
    for r in regions:
        for img in images:
            if img[0] == r:
                return img
    return images[0] if images else None


def names_of(game):
    return [n.get("text") for n in game.get("noms", []) if n.get("text")]


def best_game(entry, found):
    """The game from a search whose name equals the wanted title, else None: a title that doesn't match is not guessed."""
    want = folded(entry.get("title"))
    for g in found:
        if want and any(folded(n) == want for n in names_of(g)):
            return g
    return None


def main(args):
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else 10 ** 9
    rest = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] != "--limit")]
    path = rest[0] if rest else WANTED
    with open(path, encoding="utf-8") as f:
        wanted = json.load(f)
    creds = ss.credentials()
    os.makedirs(OUT, exist_ok=True)
    index_path = os.path.join(OUT, "index.json")
    index = json.load(open(index_path, encoding="utf-8")) if os.path.exists(index_path) else {}
    done = 0
    try:
        for entry in wanted:
            pid = entry["print"]
            if pid in index or done >= limit or not entry.get("title") or entry.get("system") not in SYSTEM:
                continue
            system = SYSTEM[entry["system"]]
            found = ss.call("jeuRecherche.php", creds, recherche=entry["title"], systemeid=ss.SYSTEMS[system]).get("response", {}).get("jeux", [])
            game = best_game(entry, found)
            done += 1
            if not game:
                index[pid] = None
                print(pid, "no game called", entry["title"])
                continue
            info = ss.call("jeuInfos.php", creds, gameid=int(game["id"]), systemeid=ss.SYSTEMS[system]).get("response", {}).get("jeu", {})
            image = pick(ss.support_images(info, "support-texture"), regions_of(entry.get("serials")))
            if not image:
                index[pid] = None
                print(pid, entry["title"], "has no label image")
                continue
            region, url, fmt = image
            file = f"{pid}.{fmt}"
            with urllib.request.urlopen(url, timeout=60) as r, open(os.path.join(OUT, file), "wb") as f:
                f.write(r.read())
            index[pid] = {"file": file, "game": int(game["id"]), "name": names_of(game)[0] if names_of(game) else entry["title"],
                          "region": region, "title": entry["title"], "serials": entry.get("serials"), "system": entry["system"]}
            print(pid, "->", file, f"({region})")
    except urllib.error.HTTPError as e:  # 429 or 430: over the quota; anything else is worth seeing
        print("ScreenScraper answered", e.code, e.reason, "- stopping; run it again later to carry on.")
        if e.code not in (429, 430):
            raise
    finally:
        with open(index_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(index, f, indent=1, ensure_ascii=False)
    print(sum(1 for v in index.values() if v), "labels,", sum(1 for v in index.values() if not v), "without a match, in", os.path.abspath(OUT))


if __name__ == "__main__":
    main(sys.argv[1:])
