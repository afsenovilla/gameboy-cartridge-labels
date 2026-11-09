# cuts: each sticker's cut edges found in its straightened label photo (ink coordinates, straighten's PX_PER_MM), and
# the crops made from them.
# solve fits the sticker's cut as main's canonical label size, placed on the plastic: right on average, but a side can sit
# a few tenths of a mm off the real edge, and the crop was that canonical rectangle at the family's median cut, not the
# stickers' edges. Here each side is found again in the straightened image, where it runs nearly along an axis: the
# colour gradient across the side (signed, pointing inward), averaged along the line over the side's middle 90 % for
# every turn within MAX_TURN degrees (a consistent edge adds up, the art's texture cancels), the strongest line kept. Its
# strength per offset is searched from OUTSIDE mm outside the fitted cut to INSIDE mm inside it; the strongest peak of at
# least MIN_STRENGTH is the edge, except peaks within RECESS_GAP mm of the recess's edge (from the plastic's fit), where
# a groove or a highlight is often stronger than a label's edge (measured on the sample: the strongest line within 1.6
# mm was the recess's on about one side in five, at 0.4-1.1 mm outside the fitted cut). A side with no such peak keeps
# the fitted cut ("found": false).
# Measured on the sample (273 label photos): the found edges lie 0.05-0.1 mm outside the fitted cut at the median.
# The highlight on a sticker's edge (light from above on its cut face) and the shadow under it spoil the outermost
# pixels of a label photo: INSET mm inside the edges found are left out (each label photo's own, in restore; the crop's;
# the user: 0.3 mm to be safe).
import cv2, numpy as np
import shapes

OUTSIDE, INSIDE = 0.6, 0.4
RECESS_GAP = 0.2
MIN_STRENGTH = 2.0       # the mean colour gradient across the line, summed over B, G, R (0..255) per pixel
MAX_TURN = 1.5           # degrees
TURN_STEP = 0.1
INSET = 0.3
SIDES = ("top", "right", "bottom", "left")


def corners_in_ink(H, shape, width=None):
    """The fitted label's corners (top left, top right, bottom right, bottom left) through H (label mm -> ink mm): the
    canonical label, made width mm wide about its centre if given (solve's width_mm)."""
    lw, lh = shapes.LABEL_MM[shape]
    a = (lw - (width or lw)) / 2
    return cv2.perspectiveTransform(np.float64([[[a, 0]], [[lw - a, 0]], [[lw - a, lh]], [[a, lh]]]), np.float64(H)).reshape(-1, 2)


def side_position(corners, side):
    """A side's position across it (mm: y for top and bottom, x for left and right), the mean of its two corners."""
    tl, tr, br, bl = corners
    return {"top": (tl[1] + tr[1]) / 2, "bottom": (bl[1] + br[1]) / 2,
            "left": (tl[0] + bl[0]) / 2, "right": (tr[0] + br[0]) / 2}[side]


def line_strength(img, side, pos, along_mm, px_per_mm, margin):
    """The line strength per offset (mm, negative outside pos) at the best turn: (offsets, strengths, turn degrees)."""
    if side in ("left", "right"):
        img = img.transpose(1, 0, 2)
    inward = 1 if side in ("top", "left") else -1
    g = cv2.GaussianBlur(img.astype(np.float32), (0, 0), 0.7)
    grad = np.zeros_like(g)
    grad[1:-1] = (g[2:] - g[:-2]) / 2 * inward
    P = px_per_mm
    xs = np.arange(int((0.05 * along_mm + margin) * P), int((0.95 * along_mm + margin) * P)) + 0.5
    xc = (along_mm / 2 + margin) * P
    offs = np.arange(-OUTSIDE, INSIDE + 1e-9, 1 / P)
    best = None
    for turn in np.arange(-MAX_TURN, MAX_TURN + 1e-9, TURN_STEP):
        ys = (pos + margin) * P - 0.5 + inward * offs[:, None] * P + np.tan(np.radians(turn)) * (xs[None, :] - xc)
        mx = np.broadcast_to(xs[None, :] - 0.5, ys.shape).astype(np.float32)
        s = cv2.remap(grad, mx, ys.astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        v = np.linalg.norm(s.mean(1), axis=1)
        if best is None or v.max() > best[1].max():
            best = (offs, v, turn)
    return best


def find_side(img, side, fitted, recess, along_mm, px_per_mm, margin):
    """One side: {"position" (mm across, at the side's middle), "turn" (degrees, positive: clockwise in the image's y-down
    frame for top and bottom), "strength", "found"}."""
    offs, v, turn = line_strength(img, side, fitted, along_mm, px_per_mm, margin)
    inward = 1 if side in ("top", "left") else -1
    recess_off = None if recess is None else (recess - fitted) * inward
    peaks = [i for i in range(1, len(v) - 1) if v[i] >= v[i - 1] and v[i] > v[i + 1] and v[i] >= MIN_STRENGTH
             and (recess_off is None or abs(offs[i] - recess_off) > RECESS_GAP)]
    if not peaks:
        return {"position": round(float(fitted), 3), "turn": 0.0, "strength": 0.0, "found": False}
    i = max(peaks, key=lambda i: v[i])
    a, b, c = v[i - 1], v[i], v[i + 1]                       # parabolic sub-pixel peak
    d = 0.5 * (a - c) / (a - 2 * b + c) if a - 2 * b + c != 0 else 0.0
    off = offs[i] + d / px_per_mm
    return {"position": round(float(fitted + inward * off), 3), "turn": round(float(turn), 2),
            "strength": round(float(b), 2), "found": True}


def find(img, shape, fitted_corners, recess_corners, px_per_mm, margin):
    """The sticker's four cut edges in a straightened label photo: {side: find_side's}."""
    lw, lh = shapes.LABEL_MM[shape]
    out = {}
    for side in SIDES:
        along = lh if side in ("left", "right") else lw
        recess = None if recess_corners is None else side_position(recess_corners, side)
        out[side] = find_side(img, side, side_position(fitted_corners, side), recess, along, px_per_mm, margin)
    return out


def side_line(cut, side, shape):
    """A side as a line a x + b y = c in ink mm."""
    lw, lh = shapes.LABEL_MM[shape]
    s = cut[side]
    t = np.tan(np.radians(s["turn"]))
    if side in ("top", "bottom"):        # y = pos + t (x - lw / 2)
        return np.array([-t, 1.0, s["position"] - t * lw / 2])
    return np.array([1.0, -t, s["position"] - t * lh / 2])   # x = pos + t (y - lh / 2) (turned like the image transposed)


def polygon(cut, shape, inset=0.0):
    """The cut's corners in ink mm (top left, top right, bottom right, bottom left), each side moved inset mm inward."""
    lines = {}
    for side in SIDES:
        a, b, c = side_line(cut, side, shape)
        n = np.hypot(a, b)
        inward = 1 if side in ("top", "left") else -1       # the line's normal (a, b) points +y / +x, i.e. inward for top / left
        lines[side] = (a, b, c + inward * inset * n)
    out = []
    for s1, s2 in (("left", "top"), ("top", "right"), ("right", "bottom"), ("bottom", "left")):
        A = np.array([lines[s1][:2], lines[s2][:2]])
        out.append(np.linalg.solve(A, [lines[s1][2], lines[s2][2]]))
    return np.array(out)


def mask(cut, shape, size, px_to_mm, inset=INSET):
    """H x W booleans: the pixels (size w, h; px_to_mm: px -> ink mm) whose centres lie inside the cut moved inset inward."""
    q = polygon(cut, shape, inset)
    q_px = cv2.perspectiveTransform(q.reshape(-1, 1, 2), np.linalg.inv(px_to_mm)).reshape(-1, 2)
    m = np.zeros((size[1], size[0]), np.uint8)
    cv2.fillPoly(m, [np.round(q_px * 16).astype(np.int32)], 1, lineType=cv2.LINE_8, shift=4)
    return m > 0


def crop(cuts, shape, px_per_mm, margin, inset=INSET):
    """The crop of a set of label photos (a family) in their straightened images: the median of each side's position
    over their cuts (found sides only, if any), moved inset mm inward and rounded inward to whole pixels.
    {"x", "y", "w", "h" (px), "mm" ([left, top, right, bottom] in ink mm)}."""
    med = {}
    for side in SIDES:
        found = [c[side]["position"] for c in cuts if c[side]["found"]]
        med[side] = float(np.median(found or [c[side]["position"] for c in cuts]))
    P = px_per_mm
    x0 = int(np.ceil((med["left"] + inset + margin) * P - 1e-6))
    y0 = int(np.ceil((med["top"] + inset + margin) * P - 1e-6))
    x1 = int(np.floor((med["right"] - inset + margin) * P + 1e-6))
    y1 = int(np.floor((med["bottom"] - inset + margin) * P + 1e-6))
    return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0,
            "mm": [round(x0 / P - margin, 3), round(y0 / P - margin, 3), round(x1 / P - margin, 3), round(y1 / P - margin, 3)]}
