# A stand-in for gb-game-list's releases.json (the serials database serials.py reads from ../gb-game-list/database/),
# for when that repo isn't available: built from the published site's index.json (every print the site lists: its
# release id, serial, title and shape). python src/bootstrap_database.py [index.json path or URL]
# Only knows the cartridges the site already lists, so a cartridge it doesn't list reads as an unknown serial.
import json, os, sys, urllib.request

URL = "https://geon.github.io/gameboy-cartridge-labels/index.json"
OUT = "../gb-game-list/database/releases.json"


def releases_of(index):
    """[{id, gameId, title, system, cartridgeSerials}] from the prints of an index.json."""
    out = {}
    for p in index["prints"].values():
        r = out.setdefault(p["release"], {"id": p["release"], "gameId": p["release"], "title": p.get("title") or "",
                                          "system": p["shape"], "cartridgeSerials": []})
        if p["serial"] != p["release"] and p["serial"] not in r["cartridgeSerials"]:
            r["cartridgeSerials"].append(p["serial"])
    return sorted(out.values(), key=lambda r: r["id"])


def read(source):
    if source.startswith("http"):
        req = urllib.request.Request(source, headers={"User-Agent": "gameboy-cartridge-labels"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode("utf-8"))
    with open(source, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    releases = releases_of(read(sys.argv[1] if len(sys.argv) > 1 else URL))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(releases, f, indent=1, ensure_ascii=False)
    print(len(releases), "releases,", sum(len(r["cartridgeSerials"]) for r in releases), "serials ->", os.path.abspath(OUT))
