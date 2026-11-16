"""Photos from Reddit posts (r/gameboy, r/gameboyadvance), from listing pages saved by hand.

The Claude in Chrome extension won't open reddit.com and Reddit refuses automated requests to its pages, so the
listing pages (reddit-searches.html: subreddit listings and searches as .json) are opened and saved in a browser by the
user. This script reads every saved page and downloads each post's photos from i.redd.it, which serves the uploaded
original (seen 2026-11-16: 3000x4000, 3024x3049) to curl. A gallery post gives all its photos, in the gallery's order;
a crosspost gives its original post's. Videos, links and NSFW posts are skipped. A photo under MIN_SIDE is not kept.
No filter on the title: most posts show no cartridge, and those photos go unused (make remove-photos).

    python3 src/reddit_photos.py <saved page or folder>...

Photos go to downloaded-photos/reddit-search/ as reddit-<post id>-<n>.<ext> with a listing.json there (page_url: the
post), moved to save-new-images-here/ by make move-downloads for make add-photos. Record of every photo downloaded or
found too small, also those deleted by hand afterwards (never downloaded again): downloaded-photos/reddit-sources.json.
"""
import datetime
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import ebay_photos  # noqa: E402
from ebay_photos import load, locked, save, size  # noqa: E402

OUT = os.environ.get("REDDIT_OUT", ebay_photos.DOWNLOADED)
DROP = os.environ.get("REDDIT_DROP", os.path.join(ebay_photos.DOWNLOADED, "reddit-search"))
LISTING = os.path.join(DROP, "listing.json")
SOURCES = os.path.join(OUT, "reddit-sources.json")
MIN_SIDE = ebay_photos.MIN_SIDE
EXT = {"image/jpg": "jpg", "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def pages(paths):
    """Every saved listing page under the given files and folders."""
    for p in paths:
        if os.path.isdir(p):
            for name in sorted(os.listdir(p)):
                if name.endswith(".json"):
                    yield os.path.join(p, name)
        else:
            yield p


def read_page(path):
    """The posts on a saved page (raw JSON, or the JSON inside the <pre> of a page saved as HTML)."""
    text = open(path, encoding="utf-8").read()
    if not text.lstrip().startswith("{"):
        text = text[text.index("{"):text.rindex("}") + 1]
    data = json.loads(text)
    return [c["data"] for c in data.get("data", {}).get("children", []) if c.get("kind") == "t3"]


def photos(post):
    """[(media id, image url)] of a post's photos, in order."""
    post = (post.get("crosspost_parent_list") or [post])[0]
    if post.get("over_18") or post.get("is_video"):
        return []
    if post.get("is_gallery"):
        meta = post.get("media_metadata") or {}
        order = [it["media_id"] for it in (post.get("gallery_data") or {}).get("items", [])] or list(meta)
        out = []
        for mid in order:
            m = meta.get(mid) or {}
            if m.get("status") == "valid" and m.get("e") == "Image" and m.get("m") in EXT:
                out.append((mid, f"https://i.redd.it/{mid}.{EXT[m['m']]}"))
        return out
    url = post.get("url_overridden_by_dest") or post.get("url") or ""
    if url.startswith("https://i.redd.it/") and url.rsplit(".", 1)[-1].lower() in ("jpg", "jpeg", "png", "webp"):
        return [(url.rsplit("/", 1)[1].rsplit(".", 1)[0], url)]
    return []


def main(paths):
    sources = load(SOURCES)
    have = {v["media"] for v in sources.values()}
    today = datetime.date.today().isoformat()
    seen, kept, small, failed = set(), 0, 0, 0
    for page in pages(paths):
        for post in read_page(page):
            if post["id"] in seen:
                continue
            seen.add(post["id"])
            for n, (mid, image_url) in enumerate(photos(post), 1):
                if mid in have:
                    continue
                have.add(mid)
                ext = image_url.rsplit(".", 1)[1].lower().replace("jpeg", "jpg")
                name = f"reddit-{post['id']}-{n}.{ext}"
                os.makedirs(DROP, exist_ok=True)
                path = os.path.join(DROP, name)
                ok = subprocess.run(["curl", "-sSf", "-o", path, image_url], stderr=subprocess.DEVNULL).returncode == 0
                time.sleep(1)
                if not ok:
                    failed += 1
                    if os.path.exists(path):
                        os.remove(path)
                    have.discard(mid)
                    continue
                wh = size(path)
                page_url = "https://www.reddit.com" + post["permalink"]
                posted = datetime.datetime.fromtimestamp(post["created_utc"], datetime.timezone.utc).date().isoformat()
                record = {"media": mid, "post": post["id"], "page_url": page_url, "image_url": image_url,
                          "subreddit": post["subreddit"], "title_on_page": post["title"], "posted": posted,
                          "size": wh, "fetched": today}
                if max(wh) < MIN_SIDE:
                    os.remove(path)
                    sources[name] = {**record, "too_small": True}
                    small += 1
                else:
                    sources[name] = record
                    with locked(DROP):
                        listing = load(LISTING)
                        listing[name] = {k: record[k] for k in
                                         ("page_url", "image_url", "title_on_page", "subreddit", "posted", "fetched")}
                        save(LISTING, listing)
                    kept += 1
                save(SOURCES, sources)
        print(f"{page}: {kept} kept, {small} too small, {failed} failed so far", flush=True)
    print(f"{len(seen)} posts; {kept} photos kept, {small} too small, {failed} failed")


if __name__ == "__main__":
    main(sys.argv[1:])
