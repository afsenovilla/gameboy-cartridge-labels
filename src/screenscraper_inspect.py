# screenscraper_inspect: what ScreenScraper says about a game, minus images and links (which carry your credentials).
# To tell official games from hacks and homebrew, compare one of each:
#   python run.py py src/screenscraper_inspect.py <system> <game id> [<game id> ...]     e.g.  gb 1234 5678
# --medias also lists the images it has (type, region, format...), still without their links.
# --search <system> <words> shows what a search finds:  python run.py py src/screenscraper_inspect.py --search gbc 10 pin bowling
# The game ids are the first number of the file names in screenscraper-labels/<system>/.
import json
import sys

import screenscraper_sample as ss


def strip(x, medias=False):
    """The answer without anything that looks like a link, and without the medias unless asked for."""
    if isinstance(x, dict):
        return {k: strip(v, medias) for k, v in x.items()
                if (medias or k != "medias") and not (isinstance(v, str) and v.startswith("http"))}
    if isinstance(x, list):
        return [strip(v, medias) for v in x]
    return x


def search(system, query, creds, call=ss.call):
    """What a search on ScreenScraper returns, one line per game: id, system, names, label images, or its message."""
    answer = call("jeuRecherche.php", creds, recherche=query, systemeid=ss.SYSTEMS[system])
    if "error" in answer:
        return ["ScreenScraper says: " + answer["error"][:200]]
    games = answer.get("response", {}).get("jeux", [])
    out = [f"{len(games)} games for {query!r} on {system}:"]
    for g in games:
        names = sorted({n.get("text") for n in g.get("noms", []) if n.get("text")})
        labels = sorted({m.get("region") for m in g.get("medias", []) if m.get("type") == "support-texture"})
        out.append(f"  {g.get('id')}  system {(g.get('systeme') or {}).get('id')}  {' / '.join(names)[:90]}  labels: {', '.join(labels) or 'none'}")
    return out


def main(args):
    if args and args[0] == "--search":  # --search <system> <words...>: what ScreenScraper finds for them
        print("\n".join(search(args[1], " ".join(args[2:]), ss.credentials())))
        return
    medias = "--medias" in args
    args = [a for a in args if a != "--medias"]
    system, ids = args[0], args[1:]
    creds = ss.credentials()
    for gid in ids:
        answer = ss.call("jeuInfos.php", creds, gameid=int(gid), systemeid=ss.SYSTEMS[system])
        print(json.dumps(strip(answer.get("response", {}).get("jeu", answer), medias), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
