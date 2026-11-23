# label_crop: find a cartridge label in a photo and straighten it, the way the labels added by hand were done.
#   detect(image) -> [[x, y] x4] (top-left, top-right, bottom-right, bottom-left), a best guess to check by eye
#   crop(image, quad) -> the label, 820 px wide, its rounded corners filled with the colour next to them
# Detection looks for the largest four-sided outline of a label's proportions (Game Boy about 1.1:1, Game Boy Advance
# about 2:1) among the photo's edges; it misses on reflections, clear cartridges and labels the colour of their
# cartridge, so the review page lets the corners be moved before a label is accepted.
import cv2
import numpy as np

WIDTH = 820


def order(pts):
    pts = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
    s, d = pts.sum(1), pts[:, 0] - pts[:, 1]
    return np.array([pts[s.argmin()], pts[d.argmax()], pts[s.argmax()], pts[d.argmin()]])


def _quads(edges, area_min):
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    for c in contours:
        if cv2.contourArea(c) < area_min:
            continue
        hull = cv2.convexHull(c)
        peri = cv2.arcLength(hull, True)
        for eps in (0.01, 0.02, 0.03, 0.05):
            a = cv2.approxPolyDP(hull, eps * peri, True)
            if len(a) == 4:
                yield order(a), cv2.contourArea(a)
                break


def shape_fits(q):
    """Whether four corners have a label's proportions: Game Boy about 1.12:1, Game Boy Advance about 2:1."""
    w = (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3])) / 2
    h = (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1])) / 2
    if not h or not w:
        return False
    r = w / h
    return abs(r - 1.12) < 0.15 or abs(r - 2.0) < 0.3


def detect(image):
    """Corners of the label: of the outlines with a label's proportions, the smallest one that is still large (the
    label sits inside the cartridge's recess, of about the same shape, and the cartridge itself); the central two
    thirds of the photo if none."""
    h, w = image.shape[:2]
    small = 1000 / max(h, w)
    img = cv2.resize(image, None, fx=small, fy=small, interpolation=cv2.INTER_AREA) if small < 1 else image
    k = small if small < 1 else 1
    gray = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    area = img.shape[0] * img.shape[1]
    found = []
    for lo, hi in ((20, 60), (30, 90), (50, 150), (80, 200)):
        edges = cv2.dilate(cv2.Canny(gray, lo, hi), np.ones((3, 3), np.uint8))
        found += [(a, q) for q, a in _quads(edges, area * 0.03) if shape_fits(q) and a < 0.9 * area]
    if not found:
        q = np.array([[w / 6, h / 6], [5 * w / 6, h / 6], [5 * w / 6, 5 * h / 6], [w / 6, 5 * h / 6]])
        return q.round(1).tolist()
    biggest = max(a for a, _ in found)
    a, q = min((x for x in found if x[0] >= 0.55 * biggest), key=lambda x: x[0])
    return (q / k).round(1).tolist()


def crop(image, quad, width=WIDTH, corner=None):
    """The label inside quad, straightened to width px, its rounded corners filled with the colour beside each."""
    q = np.float32(quad)
    w = (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3])) / 2
    h = (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1])) / 2
    W, H = width, max(1, round(width * h / max(w, 1)))
    out = cv2.warpPerspective(image, cv2.getPerspectiveTransform(q, np.float32([(0, 0), (W, 0), (W, H), (0, H)])), (W, H),
                              flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    r = corner or max(12, round(W * 0.03))
    for cx, cy in ((r, r), (W - 1 - r, r), (r, H - 1 - r), (W - 1 - r, H - 1 - r)):
        x0, x1 = (0, r) if cx == r else (W - r, W)
        y0, y1 = (0, r) if cy == r else (H - r, H)
        yy, xx = np.mgrid[y0:y1, x0:x1]
        sx0, sx1 = (r // 2, r) if cx == r else (W - r, W - r // 2)
        sy0, sy1 = (r, 2 * r) if cy == r else (H - 2 * r, H - r)
        out[y0:y1, x0:x1][(xx - cx) ** 2 + (yy - cy) ** 2 > r * r] = np.median(out[sy0:sy1, sx0:sx1].reshape(-1, 3), axis=0)
    return out


def source_width(quad):
    q = np.float32(quad)
    return round((np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3])) / 2)
