import glob, hashlib, os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photos, serials, text

# add-photos: files the photos left in save-new-images-here/ into photos/ (src/photos.py). A subfolder names their
# source (save-new-images-here/ebay-elrocinante/ -> photos/ebay-elrocinante/); photos straight in the folder go to
# photos/unrecorded/. Each photo is stored as it came (never re-encoded) under the serial read on its label
# (src/serials.py: exact, or one character off); without one, as UNKNOWN. A photo already in photos/ (the same file,
# by SHA-1) is deleted; anything not a photo stays, and is listed. The folder is left empty: filed photos and emptied
# subfolders are removed.
# Usage: add_photos.py
DROP_OFF = "save-new-images-here"
WORK = "generated/add-photos"
PHOTO = (".jpg", ".jpeg", ".png", ".webp", ".avif", ".heic", ".heif")

photos.reconcile()
known = {e[k] for _, _, _, e in photos.all_sources() for k in ("sha1", "original_sha1") if e.get(k)}

# The photos to file: (source, path, SHA-1).
os.makedirs(DROP_OFF, exist_ok=True)
incoming, left, duplicates = [], [], 0
for folder in [DROP_OFF] + sorted(d for d in glob.glob(os.path.join(DROP_OFF, "*")) if os.path.isdir(d)):
    source = "unrecorded" if folder == DROP_OFF else photos.tidy(os.path.basename(folder)).lower()
    for path in sorted(glob.glob(os.path.join(folder, "*"))):
        name = os.path.basename(path)
        if os.path.isdir(path) or name == "README.md":
            continue
        if os.path.splitext(name)[1].lower() not in PHOTO:
            left.append(path)
            continue
        sha1 = hashlib.sha1(open(path, "rb").read()).hexdigest()
        if sha1 in known:
            os.remove(path)
            duplicates += 1
            continue
        known.add(sha1)
        incoming.append((source, path, sha1))

# The serial on each label, read from links to the photos (src/ocr reads every format here, HEIC and AVIF too).
reads = {}
if incoming:
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(os.path.join(WORK, "photos"))
    links = []
    for k, (_, path, _) in enumerate(incoming):
        links.append(os.path.join(WORK, "photos", f"p{k}{os.path.splitext(path)[1].lower()}"))
        os.symlink(os.path.abspath(path), links[-1])
    text.read(links, os.path.join(WORK, "ocr"))
    reads = {row[0]: (row[1], row[2]) for row in serials.serials(os.path.join(WORK, "ocr"))}
    shutil.rmtree(WORK)

filed = {}
for k, (source, path, sha1) in enumerate(incoming):
    status, serial = reads.get(f"p{k}", ("none", ""))
    original = os.path.basename(path)
    if status in ("exact", "near") and serial:
        name_by, how = serial, f"the serial read on it ({status})"
    else:
        name_by, how = "UNKNOWN", "nothing: no serial read"
    entry = dict(original_name=original, serial_on_label=serial or None, note=f"named by {how}")
    name = photos.add(name_by, open(path, "rb").read(), os.path.splitext(original)[1], {key: value for key, value in entry.items() if value is not None}, source)
    os.remove(path)
    filed.setdefault(source, []).append(name)
    print(f"{source}/{original}\t-> {name}\t({how})")

# The emptied subfolders.
for folder in sorted(d for d in glob.glob(os.path.join(DROP_OFF, "*")) if os.path.isdir(d)):
    if not [n for n in os.listdir(folder) if n != ".DS_Store"]:
        shutil.rmtree(folder)
for source, names in sorted(filed.items()):
    print(f"{source}: {len(names)} filed, {sum(n.startswith('UNKNOWN') for n in names)} of them as UNKNOWN")
if duplicates:
    print(f"{duplicates} already in photos/, deleted")
for path in left:
    print(f"left, not a photo: {path}")
if not (incoming or duplicates or left):
    print(f"nothing to file in {DROP_OFF}/")
