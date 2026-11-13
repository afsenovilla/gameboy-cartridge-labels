# Frozen prints (persistent-prints.md, stage 2): prints the user accepted. Hand input, written only by remove-photos'
# Freeze and Unfreeze (the user's say), read by find, solve, prints, restore, publish and match:
#   frozen-prints.json: {print id: {"datetime", "serial", "shape", "image" (its SHA-1), "crop" (restore's),
#                        "restored_from" (the label photos the image was restored from: restore's keys),
#                        "label_photos": {key: solve.json's record of it when frozen, plus "found": find's outline}}}
#   frozen/<print id>.avif: the restored image, as restore made it (committed).
# A frozen print's label photos, poses and image are fixed: no step recomputes them. A new photo of it joins the print,
# its image stays as frozen (the user, 2026-11-13). Unfreezing deletes the entry and its image; the next run treats the
# print as open, from its label photos.
import datetime, json, os, shutil, hashlib

FILE = "frozen-prints.json"
DIR = "frozen"


def load(path=None):
    path = path or FILE
    return json.load(open(path)) if os.path.exists(path) else {}


def save(entries, path=None):
    path = path or FILE
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(entries, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def image_path(pid, folder=None):
    return os.path.join(folder or DIR, pid + ".avif")


def freeze(pid, print_entry, solved, found_outlines, restored_base, path=None, folder=None):
    """Freezes a print: its entry from prints.json (print_entry), its label photos' records from solve.json (solved),
    find's outlines (key -> outline), restore's output (restored_base + .avif, .json)."""
    desc = json.load(open(restored_base + ".json"))
    os.makedirs(folder or DIR, exist_ok=True)
    shutil.copyfile(restored_base + ".avif", image_path(pid, folder) + ".tmp")
    os.replace(image_path(pid, folder) + ".tmp", image_path(pid, folder))
    entries = load(path)
    entries[pid] = {"datetime": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                    "serial": print_entry.get("serial") or print_entry.get("release"), "shape": print_entry["shape"],
                    "image": hashlib.sha1(open(image_path(pid, folder), "rb").read()).hexdigest(),
                    "crop": desc["crop"], "restored_from": desc["keys"], "paper": desc.get("paper"),
                    "label_photos": {k: {**solved[k], "found": found_outlines.get(k)} for k in print_entry["keys"] if k in solved}}
    save(entries, path)


def unfreeze(pid, path=None, folder=None):
    entries = load(path)
    entries.pop(pid, None)
    save(entries, path)
    if os.path.exists(image_path(pid, folder)):
        os.remove(image_path(pid, folder))


def cut_corners(record):
    """A frozen label photo's cut in its photo's pixels (top left, top right, bottom right, bottom left)."""
    import numpy as np, cuts
    return cuts.corners_in_ink(np.float64(record["cut_to_photo"]), record["shape"], record.get("width_mm"), record.get("height_mm"))


def label_photos(entries, present=None):
    """key -> (print id, record) of every frozen label photo, those of photos in present only (if given)."""
    return {k: (pid, r) for pid, e in entries.items() for k, r in e["label_photos"].items()
            if present is None or r["photo"] in present}
