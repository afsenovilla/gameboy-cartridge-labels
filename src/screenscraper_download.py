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
# Regions of a game with the identical image (ScreenScraper's md5) are downloaded once, under the region that says best
# where that label was sold (keeper: eu and fr is the French label; de, fr and it, the European one); index.json notes
# the others in the game's "same" ({that region's file: the file kept}). The same goes across games, as ScreenScraper
# has some twice (Bomberman GB and Wario Blast share the Japanese label): "md5" in index.json remembers what's saved. --dedupe does the same for the
# images downloaded before this, removing the identical copies (don't run it while a download is running); with
# --dry-run it only lists what it would remove.
# screenscraper-labels/ignore.txt lists images that are ScreenScraper's mistakes (a GBA label filed under a GB game),
# one per line, e.g. gb/82269-us.png: never downloaded, and --dedupe removes those already there.
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
    """[(region, url, format, md5)] of a game's flat label images."""
    return [(m.get("region") or "xx", m["url"], m.get("format") or "png", m.get("md5"))
            for m in game.get("medias", []) if m.get("type") == "support-texture" and m.get("url")]


GENERAL = {"wor": 0, "ss": 0, "xx": 0, "eu": 1, "asi": 1}  # regions that aren't one country: the rest are
EUROPE = {"de", "fr", "sp", "it", "nl", "uk", "se", "dk", "fi", "no", "pt", "gr", "pl", "be", "ch", "at", "au"}
FIRST = ["us", "jp", "uk", "de", "fr", "sp", "it", "nl", "se", "dk", "fi", "no", "au", "ca", "br", "kr", "cn", "tw"]


def region_of(name):
    return os.path.splitext(name)[0].rsplit("-", 1)[-1]


def keeper(names):
    """Of files holding the same image, the one whose region says best where that label was sold: the only country
    among them (eu and fr: a French label), Europe when several European countries share it (de, fr, it: a European
    one), else the first country (us before ca, which mostly copies it), else Europe before the world."""
    countries = [n for n in names if region_of(n) not in GENERAL]
    if len(countries) == 1:
        return countries[0]
    if countries:
        eu = [n for n in names if region_of(n) == "eu"]
        if eu and all(region_of(n) in EUROPE for n in countries):
            return eu[0]
        return min(countries, key=lambda n: FIRST.index(region_of(n)) if region_of(n) in FIRST else len(FIRST))
    return max(names, key=lambda n: GENERAL.get(region_of(n), 0))


IGNORE = os.path.join(OUT, "ignore.txt")


def ignored(path=IGNORE):
    """The images never to keep, one per line ("gb/82269-us.png"; # starts a comment): ScreenScraper's mistakes."""
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {l.split("#")[0].strip().replace("\\", "/") for l in f} - {""}


def drop_ignored(state, ignore, out=OUT, remove=os.remove):
    """Remove the ignored images already downloaded, and forget them. Returns how many."""
    n = 0
    for g in state["games"].values():
        for name in [x for x in g.get("labels", []) if x in ignore]:
            if os.path.exists(os.path.join(out, name)):
                remove(os.path.join(out, name))
            g["labels"].remove(name)
            n += 1
        for name in [x for x, kept in g.get("same", {}).items() if x in ignore or kept in ignore]:
            del g["same"][name]
    return n


def save_textures(system, gid, info, fetch, seen=None, ignore=frozenset()):
    """Download a game's label images, one file per distinct image: (files, same), same = {region's file: the file of
    the identical image that was kept (keeper)}. ScreenScraper often gives several regions the same image (eu and fr,
    us and wor)."""
    groups = {}
    for region, url, fmt, md5 in textures(info):
        name = f"{system}/{gid}-{region}.{fmt}"
        if name not in ignore:
            groups.setdefault(md5 or url, []).append((name, url))
    files, same = [], {}
    seen = {} if seen is None else seen  # md5 -> file kept, over every game: ScreenScraper has some games twice
    for md5, group in groups.items():
        if md5 in seen:  # another game's (Bomberman GB and Wario Blast carry the same Japanese label)
            same.update({n: seen[md5] for n, _ in group})
            continue
        name = keeper([n for n, _ in group])
        url = dict(group)[name]
        if fetch is None or fetch(url, name) is not False:
            files.append(name)
            same.update({n: name for n, _ in group if n != name})
            if md5 and not md5.startswith("http"):
                seen[md5] = name
    return files, same


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


SYSTEM_OF_ID = {str(v): k for k, v in ss.SYSTEMS.items()}


def system_of_game(game):
    """The game's own system as ScreenScraper says (gb, gbc, gba), False for another system's, None if it doesn't say."""
    sid = str((game.get("systeme") or {}).get("id") or "")
    return SYSTEM_OF_ID.get(sid, False) if sid else None


def run(todo, creds, state, limit, call=ss.call, fetch=None, save=lambda: None, ignore=frozenset()):
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
                own = system_of_game(g)
                if own is False:  # another system's game altogether
                    continue
                system_here = own or system  # a Game Boy search also finds Game Boy Color games: file them as theirs
                info = g if g.get("medias") and described(g) else ask("jeuInfos.php", creds, gameid=int(gid), systemeid=ss.SYSTEMS[system_here]).get("response", {}).get("jeu", {})
                system_here = system_of_game(info) or system_here
                why = verdict(info)
                if why:
                    state["games"][gid] = {"system": system_here, "names": names_of(g) or names_of(info), "labels": [], "excluded": why}
                    continue
                files, same = save_textures(system_here, gid, info, fetch, state.setdefault("md5", {}), ignore)
                state["games"][gid] = {"system": system_here, "names": names_of(g) or names_of(info), "labels": files, "checked": True}
                if same:
                    state["games"][gid]["same"] = same
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
                g["labels"], same = save_textures(g["system"], gid, info, fetch, state.setdefault("md5", {}), ignored())
                if same:
                    g["same"] = same
        save()
    return used


def dedupe(state, out=OUT, remove=os.remove):
    """The label images downloaded before duplicates were skipped: of identical files (of one game or of several, as
    ScreenScraper has some games twice), keep one (keeper; the lowest game id on a tie), remove the others and note
    them in their game's "same". Returns how many were removed."""
    import hashlib
    groups, owner = {}, {}
    for gid, g in sorted(state["games"].items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0):
        for name in g.get("labels", []):
            path = os.path.join(out, name)
            if os.path.exists(path):
                with open(path, "rb") as f:
                    groups.setdefault(hashlib.sha1(f.read()).hexdigest(), []).append(name)
                owner[name] = g
    n = 0
    for group in groups.values():
        kept = keeper(group)
        for name in group:
            if name != kept:
                remove(os.path.join(out, name))
                g = owner[name]
                g["labels"] = [x for x in g["labels"] if x != name]
                g.setdefault("same", {})[name] = kept
                n += 1
    return n


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

    if "--dedupe" in args:
        if "--dry-run" in args:  # only say what would go: nothing removed, index.json untouched
            import copy
            n = dedupe(copy.deepcopy(state), remove=lambda path: print("  would remove", path))
            print(n, "identical images would be removed (run without --dry-run to remove them).")
            return
        gone = drop_ignored(state, ignored())
        n = dedupe(state)
        save()
        print(n, "identical images removed; index.json notes which image each region shares.")
        if gone:
            print(gone, "images listed in screenscraper-labels/ignore.txt removed.")
        return

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
        used = run(todo, creds, state, limit, fetch=fetch, save=save, ignore=ignored())
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
