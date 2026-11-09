# Details in photos: where each image of details/ (common details of the labels, 20 px/mm, named by hand) is found
# in a photo, for find. Each photo's detections are cached in <generated>/details/<sha1>.json:
#   [{"detail" (its file name), "corners" (the detail image's corners in the photo), "centre", "px_per_mm", "inliers"}]
# A detail is matched against the photo's SIFT keypoints (features) with Lowe's ratio test, then a RANSAC homography:
# kept with MIN_INLIERS or more, plausible, at 2 to 60 photo pixels per mm; repeated without its inliers (a detail on
# several cartridges). A photo's cache is redone when it's missing, or older than this file or any detail image.
# Seals and the CE have too few keypoints for this (18); they're found later, in straightened label photos.
import json, os
import cv2, numpy as np

import steps, match

DETAILS = "details"
DETAIL_PX_PER_MM = 20
MIN_INLIERS = 12
RATIO = 0.8
MAX_PER_PHOTO = 4
PX_PER_MM = (2, 60)

_details = None


def load_details(folder=DETAILS):
    """The detail images' SIFT keypoints: [(name, (w, h), points, descriptors)]."""
    global _details
    if _details is None:
        sift = cv2.SIFT_create()
        _details = []
        for name in sorted(os.listdir(folder)):
            if not name.lower().endswith(".png"):
                continue
            img = cv2.imread(os.path.join(folder, name))
            kp, des = sift.detectAndCompute(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), None)
            if des is not None and len(kp) >= MIN_INLIERS:
                _details.append((name, (img.shape[1], img.shape[0]), np.float32([k.pt for k in kp]), des.astype(np.float32)))
    return _details


def detect(features, details):
    """Where the details are in a photo (its features: points, descriptors, size)."""
    found = []
    des = features["descriptors"].astype(np.float32)
    if len(des) < 2:
        return found
    bf = cv2.BFMatcher()
    for name, (w, h), dpts, ddes in details:
        ms = [m for m, o in (p for p in bf.knnMatch(ddes, des, k=2) if len(p) == 2) if m.distance < RATIO * o.distance]
        if len(ms) < MIN_INLIERS:
            continue
        pa = np.float32([dpts[m.queryIdx] for m in ms])
        pb = np.float32([features["points"][m.trainIdx] for m in ms])
        left = np.ones(len(ms), bool)
        for _ in range(MAX_PER_PHOTO):
            idx = np.where(left)[0]
            if len(idx) < MIN_INLIERS:
                break
            H, mask = cv2.findHomography(pa[idx], pb[idx], cv2.USAC_MAGSAC, 3.0 * max(1.0, float(features["scale"])))
            if H is None:
                break
            inl = np.zeros(len(ms), bool)
            inl[idx[mask.ravel().astype(bool)]] = True
            left &= ~inl
            if inl.sum() < MIN_INLIERS or not match.plausible(H, (w, h)):
                continue
            corners = cv2.perspectiveTransform(np.float64([[[0, 0]], [[w, 0]], [[w, h]], [[0, h]]]), H).reshape(-1, 2)
            px_per_mm = np.sqrt(abs(cv2.contourArea(corners.astype(np.float32))) / (w * h)) * DETAIL_PX_PER_MM
            if PX_PER_MM[0] <= px_per_mm <= PX_PER_MM[1]:
                found.append({"detail": name, "corners": corners.round(1).tolist(), "centre": corners.mean(0).round(1).tolist(),
                              "px_per_mm": round(float(px_per_mm), 3), "inliers": int(inl.sum())})
    return found


def detect_photo(job):
    sha1, features_path, out = job
    f = np.load(features_path)
    steps.write_json(out, detect({k: f[k] for k in ("points", "descriptors", "scale")}, load_details()))
    return sha1


def detections(gen, chosen, workers=8, folder=DETAILS):
    """sha1 -> the photo's detections, made where the cache is stale."""
    out_dir = os.path.join(gen, "details")
    os.makedirs(out_dir, exist_ok=True)
    steps.remove_orphans(out_dir, chosen, ".json")
    newest = max([os.path.getmtime(__file__)] + [os.path.getmtime(os.path.join(folder, n)) for n in os.listdir(folder)])
    out = lambda s: os.path.join(out_dir, s + ".json")
    jobs = [(s, os.path.join(gen, "features", s + ".npz"), out(s)) for s in chosen
            if not os.path.exists(out(s)) or os.path.getmtime(out(s)) < newest]
    steps.run(detect_photo, jobs, workers, what="details searched in")
    return {s: json.load(open(out(s))) for s in chosen}
