# Downloads the restored label images of the published site (https://geon.github.io/gameboy-cartridge-labels/): the
# images listed in its index.json (prints/<id>.avif) into published-labels/, with labels.json (id, serial, release,
# title, system, file) beside them. Stops where it left off: a file already there isn't fetched again.
#
#   python run.py py src/download_published.py [--png] [--limit N] [--system dmg|cgb|agb] [--base URL]
#
# --png also saves each image as PNG (needs Pillow: the .venv has it), for programs that don't open AVIF.
# One request every 0.3 s: the site is GitHub Pages, run by one person's project; no need to hurry. The images are the
# project's work from other people's photos: for your own use, ask before publishing them anywhere.
import argparse, json, os, sys, time, urllib.request

BASE = "https://geon.github.io/gameboy-cartridge-labels/"
OUT = "published-labels"
PAUSE = 0.3


def fetch(url, tries=4):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "gameboy-cartridge-labels-downloader"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def listing(index, system=None):
    """[{id, serial, release, title, system, image, size, photos}] of the prints that have an image."""
    out = []
    for pid, p in sorted(index["prints"].items()):
        if not p.get("image") or (system and p.get("shape") != system):
            continue
        out.append({"id": pid, "serial": p.get("serial"), "release": p.get("release"), "title": p.get("title"),
                    "system": p.get("shape"), "image": p["image"], "size": p.get("size"),
                    "photos": len(p.get("label_photos") or [])})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--png", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--system", choices=["dmg", "cgb", "agb"])
    args = ap.parse_args()
    base = args.base if args.base.endswith("/") else args.base + "/"
    index = json.loads(fetch(base + "index.json").decode("utf-8"))
    labels = listing(index, args.system)
    if args.limit:
        labels = labels[:args.limit]
    os.makedirs(OUT, exist_ok=True)
    done = failed = 0
    for n, label in enumerate(labels, 1):
        file = os.path.join(OUT, os.path.basename(label["image"]))
        label["file"] = os.path.basename(file)
        if not os.path.exists(file):
            try:
                data = fetch(base + label["image"])
            except Exception as e:
                print("failed", label["id"], e, flush=True)
                failed += 1
                continue
            with open(file + ".tmp", "wb") as f:
                f.write(data)
            os.replace(file + ".tmp", file)
            time.sleep(PAUSE)
            done += 1
        if args.png and not os.path.exists(os.path.splitext(file)[0] + ".png"):
            from PIL import Image
            try:
                import pillow_heif
                pillow_heif.register_heif_opener()
            except ImportError:
                pass
            with Image.open(file) as im:
                im.convert("RGB").save(os.path.splitext(file)[0] + ".png")
        if n % 100 == 0 or n == len(labels):
            print(f"{n} of {len(labels)} ({done} downloaded now, {failed} failed)", flush=True)
    with open(os.path.join(OUT, "labels.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump([l for l in labels if "file" in l], f, indent=1, ensure_ascii=False)
    try:  # the cartridges still needing photos (wanted.json), for the browsing page's Wanted tab
        data = fetch(base + "wanted.json")
        json.loads(data.decode("utf-8"))
        with open(os.path.join(OUT, "wanted.json"), "wb") as f:
            f.write(data)
    except Exception as e:
        print("no wanted.json:", e)
    print(f"{len(labels)} labels in {os.path.abspath(OUT)}")


if __name__ == "__main__":
    main()
