# screenscraper_inspect: what ScreenScraper says about a game, minus images and links (which carry your credentials).
# To tell official games from hacks and homebrew, compare one of each:
#   python run.py py src/screenscraper_inspect.py <system> <game id> [<game id> ...]     e.g.  gb 1234 5678
# The game ids are the first number of the file names in screenscraper-labels/<system>/.
import json
import sys

import screenscraper_sample as ss


def strip(x):
    """The answer without medias and without anything that looks like a link."""
    if isinstance(x, dict):
        return {k: strip(v) for k, v in x.items() if k != "medias" and not (isinstance(v, str) and v.startswith("http"))}
    if isinstance(x, list):
        return [strip(v) for v in x]
    return x


def main(args):
    system, ids = args[0], args[1:]
    creds = ss.credentials()
    for gid in ids:
        answer = ss.call("jeuInfos.php", creds, gameid=int(gid), systemeid=ss.SYSTEMS[system])
        print(json.dumps(strip(answer.get("response", {}).get("jeu", answer)), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
