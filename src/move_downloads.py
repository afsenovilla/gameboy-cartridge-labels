# move-downloads (a tool): moves the photos the downloaders (ebay_photos, mercari_photos, jauce_photos) saved in
# downloaded-photos/<site>-search/ to save-new-images-here/<site>-search/, for make add-photos, with their listing.json
# entries (merged into the listing.json there). The downloaders keep saving into downloaded-photos/, so a download
# running meanwhile never lands in an add-photos run (the user, 2026-11-12). Only photos whose listing entry is written
# are moved (a photo still downloading has none yet), under the folder's lock (ebay_photos.locked).
# Usage: move_downloads.py
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ebay_photos import DOWNLOADED, load, locked, save

TARGET = "save-new-images-here"


def move(downloaded=DOWNLOADED, target=TARGET):
    """{subfolder: photos moved}."""
    moved = {}
    for sub in sorted(os.listdir(downloaded)) if os.path.isdir(downloaded) else []:
        src = os.path.join(downloaded, sub)
        if not os.path.isdir(src):
            continue
        with locked(src):
            listing = load(os.path.join(src, "listing.json"))
            names = [n for n in listing if os.path.exists(os.path.join(src, n))]
            if not names:
                continue
            dst = os.path.join(target, sub)
            os.makedirs(dst, exist_ok=True)
            dst_listing = load(os.path.join(dst, "listing.json"))
            for n in names:
                os.replace(os.path.join(src, n), os.path.join(dst, n))
                dst_listing[n] = listing.pop(n)
            save(os.path.join(dst, "listing.json"), dst_listing)
            save(os.path.join(src, "listing.json"), listing)
        moved[sub] = len(names)
    return moved


def main():
    moved = move()
    for sub, n in moved.items():
        print(f"{n} photos moved to {os.path.join(TARGET, sub)}/")
    print(f"{sum(moved.values())} photos moved in all; run make add-photos to add them" if moved else "nothing to move")


if __name__ == "__main__":
    main()
