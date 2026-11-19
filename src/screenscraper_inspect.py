# screenscraper_inspect: what ScreenScraper says about a game, minus images and links (which carry your credentials).
# To tell official games from hacks and homebrew, compare one of each:
#   python run.py py src/screenscraper_inspect.py <system> <game id> [<game id> ...]     e.g.  gb 1234 5678
# --medias also lists the images it has (type, region, format...), still without their links.
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


def main(args):
    medias = "--medias" in args
    args = [a for a in args if a != "--medias"]
    system, ids = args[0], args[1:]
    creds = ss.credentials()
    for gid in ids:
        answer = ss.call("jeuInfos.php", creds, gameid=int(gid), systemeid=ss.SYSTEMS[system])
        print(json.dumps(strip(answer.get("response", {}).get("jeu", answer), medias), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
