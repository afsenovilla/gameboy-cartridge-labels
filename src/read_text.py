import glob, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photos, text

# read-text: reads the text on every photo in photos/ (src/text.py) into generated/read-text/<photo>.json: every line
# of text found, with its corners in the photo. A photo is read again only when its file is missing or older than the
# photo or src/ocr.swift. Files of photos no longer in photos/ (renamed or deleted) are removed.
# Usage: read_text.py
OUT = "generated/read-text"

photos.reconcile()
os.makedirs(OUT, exist_ok=True)
paths = {photos.stem(n): os.path.join(photos.ROOT, s, system, n) for s, system, n, _ in photos.all_sources()}
for path in glob.glob(os.path.join(OUT, "*.json")):
    if photos.stem(os.path.basename(path)) not in paths:
        os.remove(path)
tool = os.path.getmtime("src/ocr.swift")
todo = []
for stem, path in sorted(paths.items()):
    out = os.path.join(OUT, stem + ".json")
    if not os.path.exists(out) or os.path.getmtime(out) < max(os.path.getmtime(path), tool):
        todo.append(path)
print(f"{len(paths)} photos, {len(todo)} to read")
if todo:
    text.read(todo, OUT)
