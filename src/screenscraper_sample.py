# A test, not a step: downloads the cartridge images ("support-2D") ScreenScraper has for a few Game Boy games, to see
# whether their labels are readable. python src/screenscraper_sample.py "Tetris" "Pokemon Red" ...
# Needs a ScreenScraper account and the developer credentials its API asks for, in screenscraper.json (not in git):
#   {"devid": "...", "devpassword": "...", "softname": "gameboy-cartridge-labels", "ssid": "<your user>", "sspassword": "..."}
# Free accounts have daily request limits, so this is slow on purpose (one request every 2 s). Images go to
# screenscraper-sample/<game id>-<region>.<ext>, with the list of what each game had in screenscraper-sample/index.json.
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


def support_images(game):
    """[(region, url, format)] of the game's support-2D images (the cartridge) in the response of jeuInfos."""
    return [(m.get("region") or "xx", m["url"], m.get("format") or "png")
            for m in game.get("medias", []) if m.get("type") == "support-2D" and m.get("url")]


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
            images = support_images(game)
            index[str(game_id)] = {"name": name, "images": [(r, u.split("?")[0]) for r, u, _ in images]}
            for region, url, fmt in images:
                path = os.path.join(OUT, f"{game_id}-{region}.{fmt}")
                if not os.path.exists(path):
                    with urllib.request.urlopen(url, timeout=60) as r, open(path, "wb") as f:
                        f.write(r.read())
                    time.sleep(PAUSE)
            print(name, game_id, len(images), "support image(s)")
    with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(index, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1:])
