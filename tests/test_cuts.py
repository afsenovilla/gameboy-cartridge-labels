import cv2, numpy as np
import cuts, straighten

P, M = straighten.PX_PER_MM, straighten.MARGIN


def label_on_plastic(left=0.2, top=-0.15, right=42.5 + 0.3, bottom=37.0 - 0.1, recess_gap=0.8, seed=0):
    """A straightened dmg label photo: grey plastic, a darker groove at the recess's edge (recess_gap mm outside the
    label), a textured label with the given edges (ink mm), a bright highlight along its top edge."""
    (w, h), _ = straighten.canvas("dmg")
    img = np.full((h, w, 3), 120, np.float32)
    px = lambda mm: (mm + M) * P
    for t in (2, 1):   # the groove: a dark line 2 px wide around the label
        cv2.rectangle(img, (int(px(left - recess_gap)), int(px(top - recess_gap))),
                      (int(px(right + recess_gap)), int(px(bottom + recess_gap))), (40, 40, 40), t)
    rng = np.random.default_rng(seed)
    art = cv2.GaussianBlur(rng.uniform(80, 240, (h, w, 3)).astype(np.float32), (0, 0), 3)
    ys, xs = np.mgrid[0:h, 0:w]
    inside = (xs + 0.5 >= px(left)) & (xs + 0.5 < px(right)) & (ys + 0.5 >= px(top)) & (ys + 0.5 < px(bottom))
    img[inside] = art[inside]
    img[int(px(top)):int(px(top)) + 2, int(px(left)):int(px(right))] = 250
    return np.clip(img, 0, 255).astype(np.uint8)


def fitted(dx=0.0, dy=0.0):
    return np.array([[0, 0], [42.5, 0], [42.5, 37], [0, 37]], float) + [dx, dy]


def test_the_cut_is_found_not_the_recess_groove():
    img = label_on_plastic()
    rec = fitted() + np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]]) * 0.8
    c = cuts.find(img, "dmg", fitted(0.1, -0.1), rec, P, M)
    want = {"left": 0.2, "top": -0.15, "right": 42.8, "bottom": 36.9}
    for side, pos in want.items():
        assert c[side]["found"], side
        assert abs(c[side]["position"] - pos) < 0.1, (side, c[side])


def test_a_side_without_an_edge_keeps_the_fitted_cut():
    (w, h), _ = straighten.canvas("dmg")
    c = cuts.find(np.full((h, w, 3), 120, np.uint8), "dmg", fitted(), None, P, M)
    assert not any(s["found"] for s in c.values())
    assert c["right"]["position"] == 42.5


def test_polygon_and_mask_are_inset():
    c = {"top": {"position": 0.0, "turn": 0.0}, "bottom": {"position": 37.0, "turn": 0.0},
         "left": {"position": 0.0, "turn": 0.0}, "right": {"position": 42.5, "turn": 0.0}}
    q = cuts.polygon(c, "dmg", 0.1)
    assert np.allclose(q, [[0.1, 0.1], [42.4, 0.1], [42.4, 36.9], [0.1, 36.9]])
    size, px_to_mm = straighten.canvas("dmg")
    m = cuts.mask(c, "dmg", size, px_to_mm)
    # INSET (0.3 mm = 6 px) inside the label's first pixel at M * P
    row = m[int(M * P) + 100]
    assert not row[int(M * P) + 5] and row[int(M * P) + 7]


def test_a_turned_side_is_a_turned_line():
    c = {"top": {"position": 0.0, "turn": 1.0}, "bottom": {"position": 37.0, "turn": 0.0},
         "left": {"position": 0.0, "turn": 0.0}, "right": {"position": 42.5, "turn": 0.0}}
    q = cuts.polygon(c, "dmg")
    t = np.tan(np.radians(1.0))
    assert np.isclose(q[0, 1], -t * 42.5 / 2) and np.isclose(q[1, 1], t * 42.5 / 2)


def test_the_crop_is_the_median_inset_in_whole_pixels():
    mk = lambda l, t, r, b: {s: {"position": v, "turn": 0.0, "found": True}
                             for s, v in zip(("left", "top", "right", "bottom"), (l, t, r, b))}
    cs = [mk(-0.2, 0.0, 42.6, 37.1), mk(0.0, 0.1, 42.4, 37.0), mk(0.1, -0.1, 42.5, 36.9)]
    c = cuts.crop(cs, "dmg", P, M)
    assert c["mm"] == [0.3, 0.3, 42.2, 36.7]
    assert (c["x"], c["y"], c["w"], c["h"]) == (106, 106, 838, 728)
