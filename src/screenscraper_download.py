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
# Hacks, translations, homebrew, unlicensed and unreleased games are left out: their labels are fan-made. Each game's verdict
# is in index.json ("excluded": why); the list is also written to screenscraper-labels/excluded.txt so it can be checked.
# --recheck asks again about the games found before this filter existed and moves the images of the excluded ones to
# screenscraper-labels/excluded/ (don't run it while a download is running: both write index.json).
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


FAN_PUBLISHER = re.compile(r"romhack|\bhack|homebrew|translat|traduc|\bfan\b|patch", re.I)
HACK_TEXT = re.compile(r"\b(?:a|this|the)\s+(?:rom)?hack\b(?![-\s]*(?:and|&|'?n'?)[-\s]*slash)|\bhack\s+of\b|\bromhack|\bfan[- ]?(?:made|translation|game)|\bhomebrew\b", re.I)
FLAGS = ("hack", "trad", "unl", "beta", "demo", "proto")
NOT_A_REGION = {"ss", "wor", "", None}


def text(x):
    return (x or {}).get("text", "") if isinstance(x, dict) else ""


def verdict(game):
    """None for a game that was sold in shops; otherwise why it is left out."""
    if str(game.get("notgame", "false")).lower() == "true":
        return "not a game"
    publisher = text(game.get("editeur"))
    if FAN_PUBLISHER.search(publisher):
        return "published by " + publisher
    for s in game.get("synopsis", []) or []:
        if s.get("langue") in ("en", "fr", "es") and HACK_TEXT.search(s.get("text", "")):
            return "described as a hack or homebrew"
    roms = game.get("roms", []) or []
    if roms and all(any(str(r.get(f, "0")) == "1" for f in FLAGS) for r in roms):
        return "every dump is flagged " + "/".join(sorted({f for r in roms for f in FLAGS if str(r.get(f, "0")) == "1"}))
    regions = {n.get("region") for n in game.get("noms", []) or []} | {d.get("region") for d in game.get("dates", []) or []}
    regions |= {x for r in roms for x in (r.get("regions") or {}).get("regions_shortname", [])}
    if not regions - NOT_A_REGION and not publisher:  # a known publisher with no countries is a gap in ScreenScraper, not a hack
        return "no release in any country and no publisher"
    return None


def described(game):
    """Whether an answer about a game has what verdict() looks at, or only a summary."""
    return any(k in game for k in ("editeur", "dates", "roms", "synopsis"))


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
                info = g if g.get("medias") and described(g) else ask("jeuInfos.php", creds, gameid=int(gid), systemeid=ss.SYSTEMS[system]).get("response", {}).get("jeu", {})
                why = verdict(info)
                if why:
                    state["games"][gid] = {"system": system, "names": names_of(g) or names_of(info), "labels": [], "excluded": why}
                    continue
                files = []
                for region, url, fmt in textures(info):
                    name = f"{system}/{gid}-{region}.{fmt}"
                    if fetch is None or fetch(url, name) is not False:
                        files.append(name)
                state["games"][gid] = {"system": system, "names": names_of(g) or names_of(info), "labels": files, "checked": True}
            state["searched"].append(key)
            save()
    except Out:
        print("Reached the limit of", limit, "requests; run it again to carry on.")
    except Refused as e:
        save()
        print("ScreenScraper says:", e, "- saved; check the message, or run it again later.")
    return used


AGAIN = {"no release in any country"}  # verdicts of an earlier, stricter filter, asked about again


def recheck(state, creds, limit, call=ss.call, move=lambda name: None, save=lambda: None, fetch=None):
    """Ask about the games kept before the filter existed; exclude the fan-made ones and move their images aside."""
    used = 0
    for gid, g in state["games"].items():
        if g.get("checked") or (g.get("excluded") and g["excluded"] not in AGAIN):
            continue
        if used >= limit:
            print("Reached the limit of", limit, "requests; run it again to carry on.")
            break
        used += 1
        info = check(call("jeuInfos.php", creds, gameid=int(gid), systemeid=ss.SYSTEMS[g["system"]])).get("response", {}).get("jeu", {})
        if not info:
            continue
        why = verdict(info)
        if why:
            for name in g["labels"]:
                move(name)
            g["labels"], g["excluded"] = [], why
        else:
            g.pop("excluded", None)
            g["checked"] = True
            if not g["labels"] and fetch:  # left out before, kept now: its images were never downloaded
                g["labels"] = [n for region, url, fmt in textures(info)
                               for n in [f"{g['system']}/{gid}-{region}.{fmt}"] if fetch(url, n) is not False]
        save()
    return used


def report(state, path):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for gid, g in sorted(state["games"].items(), key=lambda kv: (kv[1]["system"], (kv[1]["names"] or [""])[0].lower())):
            if g.get("excluded"):
                f.write(f"{g['system']}\t{gid}\t{(g['names'] or ['?'])[0]}\t{g['excluded']}\n")


def main(args):
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else 10 ** 9
    creds = ss.credentials()
    os.makedirs(OUT, exist_ok=True)
    index_path = os.path.join(OUT, "index.json")
    state = {"games": {}, "searched": []}
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as f:
            state = json.load(f)

    def save():  # written beside it and swapped in, so whoever reads it meanwhile (screenscraper_match) never sees half
        with open(index_path + ".tmp", "w", encoding="utf-8", newline="\n") as f:
            json.dump(state, f, indent=1, ensure_ascii=False)
        os.replace(index_path + ".tmp", index_path)

    def fetch(url, name):
        path = os.path.join(OUT, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            return True
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                data = r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 430):
                raise
            print("  skipped", name, "-", e.code, e.reason)
            return False
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            print("  skipped", name, "-", e)
            return False
        with open(path, "wb") as f:  # written only once complete, so a cut never leaves half an image behind
            f.write(data)
        return True

    if "--recheck" in args:
        def move(name):
            src, dst = os.path.join(OUT, name), os.path.join(OUT, "excluded", name)
            if os.path.exists(src):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                os.replace(src, dst)
        try:
            used = recheck(state, creds, limit, move=move, save=save, fetch=fetch)
        except Refused as e:
            used = 0
            print("ScreenScraper says:", e, "- saved; run it again later.")
        save()
        report(state, os.path.join(OUT, "excluded.txt"))
        out = [g for g in state["games"].values() if g.get("excluded")]
        print(f"{len(out)} of {len(state['games'])} games left out (see screenscraper-labels/excluded.txt); {used} requests.")
        return

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
    report(state, os.path.join(OUT, "excluded.txt"))
    n = sum(len(g["labels"]) for g in state["games"].values())
    print(f"{len(state['games'])} games ({sum(1 for g in state['games'].values() if g.get('excluded'))} left out), {n} label images, {len(state['searched'])} of {len(todo)} searches done ({used} requests this run).")


if __name__ == "__main__":
    main(sys.argv[1:])
