# inbox: label photos waiting for a yes or no, for serve_catalogue's review page (/review).
# A photo of a cartridge goes into screenscraper-labels/inbox/ (dropped there, uploaded on the review page, or fetched
# from eBay later). Each is processed once: the label found and straightened (label_crop), the serial read on it
# (read_text, as screenscraper_match does; a serial in the file name, like CGB-BSFP-HOL_photo.jpg, is used when none
# is read), and compared with the catalogue: is that serial missing, or is there a label of it already, and how wide.
# The candidates are listed in screenscraper-labels/candidates.json, their straightened previews in candidates/.
# On the page, the corners can be moved and the label straightened again; accepting it adds it to added.json (as
# "Add label" does) and removes the photo from the inbox; rejecting it leaves the photo listed as rejected.
import json
import os
import re
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import label_crop
import serials

OUT = "screenscraper-labels"
INBOX = os.path.join(OUT, "inbox")
PREVIEWS = os.path.join(OUT, "candidates")
LIST = os.path.join(OUT, "candidates.json")
IMAGES = (".png", ".jpg", ".jpeg", ".webp", ".avif", ".bmp")
SERIAL = re.compile(r"(DMG|CGB|AGB)-[A-Z0-9]{2,5}-[A-Z]{3}(?:-\d)?", re.I)


def load():
    if not os.path.exists(LIST):
        return []
    with open(LIST, encoding="utf-8") as f:
        return json.load(f)


def save(cands):
    with open(LIST + ".tmp", "w", encoding="utf-8", newline="\n") as f:
        json.dump(cands, f, indent=1, ensure_ascii=False)
    os.replace(LIST + ".tmp", LIST)


def imread(path):
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)  # imread fails on some Windows paths


def read_serial(image):
    """(serial, text) read on a straightened label: the first whole serial OCR finds, if any."""
    try:
        import read_text
    except Exception:  # OCR not installed: the serial is typed on the page
        return None, []
    lines = [l["text"] for l in read_text.read(image)]
    for line in lines:
        for s in serials.reads(line):
            if serials.region_of(s):
                return s, lines
    return None, lines


def catalogue():
    """What the page shows: {serial: [(label id, width)]} and the set of Missing serials, and titles by release."""
    have, missing, titles = {}, set(), {}
    for name, put in (("labels.json", True), ("wanted.json", False)):
        path = os.path.join(OUT, name)
        if not os.path.exists(path):
            continue
        for e in json.load(open(path, encoding="utf-8")):
            if put and e.get("serial"):
                have.setdefault(e["serial"], []).append((e["id"], (e.get("size") or [0])[0], e.get("source_width")))
            if not put:
                missing.add(e["print"])
            if e.get("release") and e.get("title"):
                titles[e["release"]] = e["title"]
    if os.path.exists(serials.DATABASE):
        for r in json.load(open(serials.DATABASE, encoding="utf-8")):
            titles.setdefault(r["id"], r.get("title"))
    return have, missing, titles


LOOKALIKE = {"8": "B", "B": "8", "0": "O", "O": "0", "1": "I", "I": "1", "5": "S", "S": "5", "2": "Z", "Z": "2", "6": "G", "G": "6"}


def lookalike(serial, titles):
    """A serial the database knows that differs from this one by one look-alike character (8 for B, 0 for O...)."""
    parts = serial.split("-")
    if len(parts) < 2:
        return ""
    code = parts[1]
    for i, ch in enumerate(code):
        if ch in LOOKALIKE:
            fixed = code[:i] + LOOKALIKE[ch] + code[i + 1:]
            if f"{parts[0]}-{fixed}" in titles:
                return "-".join([parts[0], fixed] + parts[2:])
    return ""


def describe(c, have, missing, titles):
    """The candidate's standing against the catalogue, for the page."""
    s = c.get("serial") or ""
    rel = s.rsplit("-", 1)[0] if s.count("-") >= 2 and len(s.rsplit("-", 1)[1]) == 3 else "-".join(s.split("-")[:2])
    c["title"] = titles.get(rel) or c.get("title") or ""
    c["known"] = rel in titles  # a serial the database doesn't know is often an OCR slip (8 for B, 0 for O)
    c["suggest"] = ""
    if s and not c["known"]:
        c["suggest"] = lookalike(s, titles)
    c["missing"] = s in missing
    c["existing"] = [{"id": i, "width": sw or w} for i, w, sw in have.get(s, [])]
    return c


def preview(c, image):
    out = label_crop.crop(image, c["quad"])
    path = os.path.join(PREVIEWS, c["id"] + ".png")
    os.makedirs(PREVIEWS, exist_ok=True)
    cv2.imencode(".png", out)[1].tofile(path)
    c["preview"] = os.path.relpath(path, OUT).replace("\\", "/")
    c["width"] = label_crop.source_width(c["quad"])
    c["v"] = c.get("v", 0) + 1  # so the page reloads the image
    return out


def process(log=lambda s: None):
    """Process the photos in the inbox not seen yet. Returns how many."""
    if not os.path.isdir(INBOX):
        return 0
    cands = load()
    # a photo already seen: still in the inbox (pending or rejected) with the same name and size. Accepted ones have
    # left for done/, so a new photo of the same name (eBay's are all s-l1200.jpg) is a new photo.
    seen = {(c["file"], c.get("bytes")) for c in cands if c["status"] != "accepted"}
    old = {c["file"] for c in cands if c["status"] != "accepted" and "bytes" not in c}
    def is_new(f):
        return f.lower().endswith(IMAGES) and f not in old and (f, os.path.getsize(os.path.join(INBOX, f))) not in seen
    new = [f for f in sorted(os.listdir(INBOX)) if is_new(f)]
    if not new:
        return 0
    have, missing, titles = catalogue()
    for f in new:
        image = imread(os.path.join(INBOX, f))
        if image is None:
            continue
        c = {"id": re.sub(r"[^A-Za-z0-9_-]", "_", os.path.splitext(f)[0])[:60] + f"-{len(cands)}", "file": f,
             "photo": f"inbox/{f}", "bytes": os.path.getsize(os.path.join(INBOX, f)), "size": [image.shape[1], image.shape[0]], "quad": label_crop.detect(image), "status": "pending"}
        label = preview(c, image)
        serial, text = read_serial(label)
        hint = SERIAL.search(f)
        c["serial"] = (serial or (hint.group(0).upper() if hint else ""))
        c["read"] = text
        cands.append(describe(c, have, missing, titles))
        log(f"  inbox: {f} -> {c['serial'] or 'no serial read'}")
        save(cands)
    return len(new)


def find(cands, cid):
    for c in cands:
        if c["id"] == cid:
            return c
    raise KeyError(cid)


def recrop(cid, quad, typed=""):
    """Straighten the label again from moved corners, and read its serial again unless one was typed: a first crop
    that missed the label had nothing to read."""
    cands = load()
    c = find(cands, cid)
    c["quad"] = [[float(x), float(y)] for x, y in quad][:4]
    label = preview(c, imread(os.path.join(INBOX, c["file"])))
    if typed:
        c["serial"] = typed.strip().upper()
    else:
        serial, text = read_serial(label)
        c["read"] = text
        if serial:
            c["serial"] = serial
    have, missing, titles = catalogue()
    describe(c, have, missing, titles)
    save(cands)
    return c


def lookup(cid, serial):
    """The candidate described with a typed serial: title, missing, already there."""
    cands = load()
    c = find(cands, cid)
    c["serial"] = serial.strip().upper()
    have, missing, titles = catalogue()
    describe(c, have, missing, titles)
    save(cands)
    return c


def refresh_all():
    """Re-check every pending candidate against the catalogue (after one is accepted, say)."""
    cands = load()
    have, missing, titles = catalogue()
    for c in cands:
        if c["status"] == "pending":
            describe(c, have, missing, titles)
    save(cands)
    return cands


def accept(cid, serial, title, add):
    """Straighten the label once more at full size and hand it to add() (serve_catalogue's); the photo leaves the inbox."""
    cands = load()
    c = find(cands, cid)
    image = imread(os.path.join(INBOX, c["file"]))
    ok, png = cv2.imencode(".png", label_crop.crop(image, c["quad"]))
    entry = add(serial, "", title or c.get("title"), "", png.tobytes(), "image/png", source_width=c.get("width"))
    c.update(status="accepted", serial=entry["serial"], added=entry["file"])
    os.makedirs(os.path.join(INBOX, "done"), exist_ok=True)
    base, ext = os.path.splitext(c["file"])
    done, n = c["file"], 1
    while os.path.exists(os.path.join(INBOX, "done", done)):  # an earlier s-l1200.jpg is there already
        n += 1
        done = f"{base}_{n}{ext}"
    os.replace(os.path.join(INBOX, c["file"]), os.path.join(INBOX, "done", done))
    c["photo"] = "inbox/done/" + done
    save(cands)
    return entry


def reject(cid):
    cands = load()
    c = find(cands, cid)
    c["status"] = "rejected"
    save(cands)
    return c
