import concurrent.futures, glob, json, os, sys, cv2, numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fits, images, photos
from cartridge import project, shell_of
from fit_cartridge import load

# rectify: straightens the label of every photo whose plastic and label are known to be right (accepted, or placed by
# hand: nothing else), into generated/labels/<photo>.png at SCALE px/mm, its colors evened out as the fits saw them, and
# measures it, into generated/labels/<photo>.json. A label is done again when its photo or its fit changes, or this
# code; files of labels no longer good are removed.
# Usage: rectify.py
OUT = "generated/labels"
SCALE = 20
VERSION = 1


def native_scale(H, label):
    """The photo's real pixels per mm on the label: along its shortest side, and the least of the two directions, so a
    label shot at an angle, or upscaled to SCALE, doesn't look better than it is."""
    x0, y0, x1, y1 = label
    q = project(H, [[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
    width = min(np.linalg.norm(q[1] - q[0]), np.linalg.norm(q[2] - q[3])) / (x1 - x0)
    height = min(np.linalg.norm(q[3] - q[0]), np.linalg.norm(q[2] - q[1])) / (y1 - y0)
    return float(min(width, height))


def warp(photo, H, label, scale=SCALE):
    """The label's rectangle straightened, at scale px/mm. Larger photos are first shrunk, or warping would alias."""
    x0, y0, x1, y1 = label
    H = np.asarray(H, np.float64)
    native = native_scale(H, label)
    shrink = min(1.0, 1.5 * scale / native)
    if shrink < 1:
        photo = cv2.resize(photo, None, fx=shrink, fy=shrink, interpolation=cv2.INTER_AREA)
        H = np.diag([shrink, shrink, 1]) @ H
    out_to_mm = np.array([[1 / scale, 0, x0], [0, 1 / scale, y0], [0, 0, 1]])
    size = (round((x1 - x0) * scale), round((y1 - y0) * scale))
    return cv2.warpPerspective(photo, H @ out_to_mm, size, flags=cv2.INTER_LANCZOS4 | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REPLICATE)


def measures(raw, native):
    """What the quality grade weighs, of a label as photographed (its colors not evened out), away from its edges:
    - sharpness: the Laplacian's variance at 10 px/mm, all labels at one scale;
    - clipped: the share of pixels blown out (every channel 250 or more): glare, or a white area overexposed;
    - contrast: the 1st to the 99th percentile of the grey."""
    h, w = raw.shape[:2]
    middle = raw[h // 20:-h // 20, w // 20:-w // 20]
    grey = cv2.cvtColor(middle, cv2.COLOR_BGR2GRAY)
    even = cv2.resize(grey, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    low, high = np.percentile(grey, [1, 99])
    return {"native_px_per_mm": round(native, 3), "sharpness": round(float(cv2.Laplacian(even, cv2.CV_64F).var()), 2),
            "clipped": round(float((middle.min(axis=2) >= 250).mean()), 5), "contrast": round(float(high - low), 1)}


def rectify(stem, path, sha1, H):
    cv2.setNumThreads(1)
    png, details = os.path.join(OUT, stem + ".png"), os.path.join(OUT, stem + ".json")
    label = shell_of(photos.serial_of(stem)).label
    raw = load(path, even_colors=False)
    if raw is None:
        result = {"error": "the photo can't be read"}
    else:
        native = native_scale(H, label)
        result = measures(warp(raw, H, label), native)
        straight = warp(load(path), H, label)
        images.write(png, straight, cv2.IMWRITE_PNG_COMPRESSION, 9)
        result.update(width=straight.shape[1], height=straight.shape[0])
    result.update(sha1=sha1, mm_to_photo=H, version=VERSION)
    with open(details, "w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f)
    return stem, result


def wanted():
    """Each good label's (path, SHA-1, homography), by its photo's stem."""
    known, found = fits.load(), {}
    for source, system, name, entry in photos.all_sources():
        stem = photos.stem(name)
        e = fits.of(known, stem, entry.get("sha1"))["fit"]
        if system in ("dmg", "cgb", "unknown") and fits.good(e.get("plastic")) and fits.good(e.get("label")):
            found[stem] = (os.path.join(photos.ROOT, source, system, name), entry.get("sha1"), e["label"]["mm_to_photo"])
    return found


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    labels = wanted()
    for path in glob.glob(os.path.join(OUT, "*")):
        if photos.stem(os.path.basename(path)) not in labels:
            os.remove(path)
    todo = []
    for stem, (path, sha1, H) in sorted(labels.items()):
        details = os.path.join(OUT, stem + ".json")
        old = json.load(open(details, encoding="utf-8")) if os.path.exists(details) else None
        if not old or old["sha1"] != sha1 or old["mm_to_photo"] != H or old["version"] != VERSION:
            todo.append((stem, path, sha1, H))
    print(f"{len(labels)} good labels, {len(todo)} to straighten")
    with concurrent.futures.ProcessPoolExecutor() as pool:
        errors = 0
        for done, (stem, result) in enumerate(pool.map(rectify, *zip(*todo)) if todo else [], 1):
            errors += "error" in result
            if "error" in result:
                print(f"{stem}: {result['error']}")
            if done % 50 == 0 or done == len(todo):
                print(f"straightened {done} of {len(todo)}", flush=True)
    print(f"{errors} errors")
