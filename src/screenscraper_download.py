# screenscraper_download: ScreenScraper's flat label images ("support-texture") for the Game Boy, Game Boy Color and Game Boy
# Advance games. Run it from the repository folder; it needs screenscraper.json (see screenscraper_sample.py).
#   python run.py py src/screenscraper_download.py [--limit N] [--sweep]
# ScreenScraper has no list of a system's games, so the games to look for come from what the project already knows: every title in
# published-labels/labels.json (restored labels) and published-labels/wanted.json (cartridges still short of photos). Each title is
# searched on its system; every game the search returns is kept, with every region's label image:
#   screenscraper-labels/<system>/<game id>-<region>.<ext>   and   screenscraper-labels/index.json
# --sweep also searches every two-letter and digit combination, to find games no title of ours led to. It is long.
# --limit N stops after N requests to ScreenScraper (the daily quota is the real limit: when it answers 429 or 430 the run saves
# and stops). Progress is in index.json, so running it again carries on; nothing is asked twice.
# These are other people's images, usually 600 px wide where our restorations are 800+: they stay apart from the restored labels.
import itertools
import json
import os
import re
import string
import sys
import unicodedata
import urllib.error
import urllib.request

import screenscraper_sample as ss

OUT = "screenscraper-labels"
SOURCES = [os.path.join("published-labels", "labels.json"), os.path.join("published-labels", "wanted.json")]
SYSTEM = {"dmg": "gb", "cgb": "gbc", "agb": "gba", "gb": "gb", "gbc": "gbc", "gba": "gba"}


def query_of(title):
    """What to search for a title: no trailing ", The", no punctuation ScreenScraper's search might trip on."""
    t = re.sub(r",\s*(the|a|an)\s*$", "", (title or "").strip(), flags=re.I)
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9' ]+", " ", t)).strip()


def titles(paths=SOURCES):
    """[(system, query)] for every title in the labels and the wanted list, each once, in file order."""
    seen, out = set(), []
    for path in paths:
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for e in json.load(f):
                system, q = SYSTEM.get(e.get("system")), query_of(e.get("title"))
                if system and q and (system, q.lower()) not in seen:
                    seen.add((system, q.lower()))
                    out.append((system, q))
    return out


def sweep_queries():
    chars = string.ascii_lowercase + string.digits
    return ["".join(p) for p in itertools.product(chars, repeat=2)]


def names_of(game):
    return [n.get("text") for n in game.get("noms", []) if n.get("text")]


def textures(game):
    return ss.support_images(game, "support-texture")


class Refused(Exception):
    """ScreenScraper answered with a message that means we must stop (quota, closed API, bad login)."""


def check(answer):
    text = str(answer.get("error", "")).lower() if isinstance(answer, dict) else ""
    if any(w in text for w in ("quota", "closed", "limit", "maximum", "identifiants", "login", "password", "blacklist", "trop")):
        raise Refused(answer["error"])
    return answer


class Out(Exception):
    """The request limit was reached."""


def run(todo, creds, state, limit, call=ss.call, fetch=None, save=lambda: None):
    """Search each (system, query) not searched yet; keep the games found and every region's label of each. Returns requests made."""
    used = 0

    def ask(*a, **k):
        nonlocal used
        if used >= limit:
            raise Out()
        used += 1
        return check(call(*a, **k))

    try:
        for system, q in todo:
            key = f"{system}|{q.lower()}"
            if key in state["searched"]:
                continue
            found = ask("jeuRecherche.php", creds, recherche=q, systemeid=ss.SYSTEMS[system]).get("response", {}).get("jeux", [])
            for g in found:
                gid = str(g.get("id") or "")
                if not gid or gid in state["games"]:
                    continue
                info = g if g.get("medias") else ask("jeuInfos.php", creds, gameid=int(gid), systemeid=ss.SYSTEMS[system]).get("response", {}).get("jeu", {})
                files = []
                for region, url, fmt in textures(info):
                    name = f"{system}/{gid}-{region}.{fmt}"
                    if fetch:
                        fetch(url, name)
                    files.append(name)
                state["games"][gid] = {"system": system, "names": names_of(g) or names_of(info), "labels": files}
            state["searched"].append(key)
            save()
    except Out:
        print("Reached the limit of", limit, "requests; run it again to carry on.")
    except Refused as e:
        save()
        print("ScreenScraper says:", e, "- saved; check the message, or run it again later.")
    return used


def main(args):
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else 10 ** 9
    creds = ss.credentials()
    os.makedirs(OUT, exist_ok=True)
    index_path = os.path.join(OUT, "index.json")
    state = {"games": {}, "searched": []}
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as f:
            state = json.load(f)

    def save():
        with open(index_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(state, f, indent=1, ensure_ascii=False)

    def fetch(url, name):
        path = os.path.join(OUT, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            with urllib.request.urlopen(url, timeout=60) as r, open(path, "wb") as f:
                f.write(r.read())

    todo = titles()
    if "--sweep" in args:
        todo += [(s, q) for q in sweep_queries() for s in ("gb", "gbc", "gba")]
    try:
        used = run(todo, creds, state, limit, fetch=fetch, save=save)
    except urllib.error.HTTPError as e:  # 429 and 430: over the quota; anything else is worth seeing
        save()
        print("ScreenScraper answered", e.code, e.reason, "- saved; run it again later to carry on.")
        if e.code not in (429, 430):
            raise
        used = 0
    save()
    n = sum(len(g["labels"]) for g in state["games"].values())
    print(f"{len(state['games'])} games, {n} label images, {len(state['searched'])} of {len(todo)} searches done ({used} requests this run).")


if __name__ == "__main__":
    main(sys.argv[1:])
