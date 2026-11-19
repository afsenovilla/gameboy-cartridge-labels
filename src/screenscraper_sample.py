# A test, not a step: downloads the cartridge images ScreenScraper has for a few Game Boy games, to see whether their
# labels are readable. Two kinds: "support-2D" (a render of the whole cartridge) and "support-texture" (the media's flat
# texture, which should be just the label). python src/screenscraper_sample.py "Tetris" "Pokemon Red" ...
# Needs a ScreenScraper account and the developer credentials its API asks for, in screenscraper.json (not in git):
#   {"devid": "...", "devpassword": "...", "softname": "gameboy-cartridge-labels", "ssid": "<your user>", "sspassword": "..."}
# Free accounts have daily request limits, so this is slow on purpose (one request every 2 s). Images go to
# screenscraper-sample/<game id>-<region>[-texture].<ext>, with the list of what each game had, and every media type it
# offers, in screenscraper-sample/index.json.
import json, os, sys, time, urllib.parse, urllib.request

API = "https://api.screenscraper.fr/api2/"
SYSTEMS = {"gb": 9, "gbc": 10, "gba": 12}
OUT = "screenscraper-sample"
CREDENTIALS = "screenscraper.json"
PAUSE = 2.0


def credentials():
    with open(CREDENTIALS, encoding="utf-8") as f:
        return json.load(f)


def call(endpoint, creds, **params):
    query = {"output": "json", **{k: creds[k] for k in ("devid", "devpassword", "softname", "ssid", "sspassword")},
             **params}
    with urllib.request.urlopen(API + endpoint + "?" + urllib.parse.urlencode(query), timeout=60) as r:
        data = r.read()
    time.sleep(PAUSE)
    return json.loads(data.decode("utf-8"))


def support_images(game, kind="support-2D"):
    """[(region, url, format)] of the game's images of one media type in the response of jeuInfos."""
    return [(m.get("region") or "xx", m["url"], m.get("format") or "png")
            for m in game.get("medias", []) if m.get("type") == kind and m.get("url")]


def search(name, system, creds):
    """The ids of the games ScreenScraper finds for a name on a system."""
    found = call("jeuRecherche.php", creds, recherche=name, systemeid=SYSTEMS[system])
    return [int(g["id"]) for g in found.get("response", {}).get("jeux", []) if g.get("id")]


def main(names, system="gb"):
    creds = credentials()
    os.makedirs(OUT, exist_ok=True)
    index = {}
    for name in names:
        for game_id in search(name, system, creds)[:3]:
            game = call("jeuInfos.php", creds, gameid=game_id, systemeid=SYSTEMS[system]).get("response", {}).get("jeu", {})
            entry = index[str(game_id)] = {"name": name, "media types": sorted({m.get("type") for m in game.get("medias", []) if m.get("type")})}
            count = 0
            for kind, suffix in (("support-2D", ""), ("support-texture", "-texture")):
                images = support_images(game, kind)
                entry[kind] = [(r, u.split("?")[0]) for r, u, _ in images]
                count += len(images)
                for region, url, fmt in images:
                    path = os.path.join(OUT, f"{game_id}-{region}{suffix}.{fmt}")
                    if not os.path.exists(path):
                        with urllib.request.urlopen(url, timeout=60) as r, open(path, "wb") as f:
                            f.write(r.read())
                        time.sleep(PAUSE)
            print(name, game_id, count, "support image(s)")
    with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(index, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1:])
