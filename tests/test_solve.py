import cv2, numpy as np
import solve, shapes


def drawn_cartridge(H_plastic, shape="dmg", size=(1400, 1400)):
    """A dark background, a mid grey cartridge body, a darker recess and a light label at its nominal place, drawn
    through H_plastic (plastic mm -> photo)."""
    m = solve.MODELS[shape]
    img = np.full((size[1], size[0], 3), 20, np.uint8)
    rect = lambda r: solve.project(H_plastic, [[r[0], r[1]], [r[2], r[1]], [r[2], r[3]], [r[0], r[3]]]).astype(np.int32)
    cv2.fillPoly(img, [rect(m["box"])], (120, 120, 120))
    cv2.fillPoly(img, [rect(m["recess"])], (90, 90, 90))
    cv2.fillPoly(img, [rect(m["label"])], (230, 230, 230))
    return img


def test_nested_fit_finds_the_cartridge_from_a_start_a_few_mm_off():
    import edges
    H_true = solve.similarity_to_H((700, 700), 7.0, 15.0, "dmg") @ np.linalg.inv(solve.label_to_plastic("dmg"))
    segs = edges.segments(drawn_cartridge(H_true))["segments"].astype(np.float64)
    H0 = solve.similarity_to_H((725, 680), 5.0, 15.6, "dmg") @ np.linalg.inv(solve.label_to_plastic("dmg"))  # ~2 mm, 2 deg off
    H, placement, support = solve.fit_nested(H0, "dmg", segs)
    # the label and the recess (the drawn body is a plain box, the model's has bevels and steps at the bottom)
    for r in (solve.MODELS["dmg"]["label"], solve.MODELS["dmg"]["recess"]):
        corners = [[r[0], r[1]], [r[2], r[1]], [r[2], r[3]], [r[0], r[3]]]
        assert np.abs(solve.project(H, corners) - solve.project(H_true, corners)).max() < 6  # px, at 15 px/mm: 0.4 mm
    assert abs(placement[0]) < 0.5 and abs(placement[1]) < 0.5
    assert support["recess"] > 0.5 and support["label"] > 0.5


def test_rigid_fit():
    a = np.random.default_rng(0).uniform(0, 40, (30, 2))
    th = np.radians(2.0)
    R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    theta, t = solve.rigid_fit(a, a @ R.T + [1.0, -0.5])
    assert abs(theta - 2.0) < 1e-6 and np.allclose(t, [1.0, -0.5])


def test_stage2_aligns_two_stickers_and_anchors_by_the_median():
    # three label photos of one print; sticker b's cut is 1 mm right of a's, c's like a's: matched points tell
    pts = np.random.default_rng(1).uniform(5, 35, (40, 2))
    I = np.eye(3)
    fits = {k: {"cut_to_photo": I} for k in "abc"}
    pairs = {("a", "b"): (pts, pts - [1.0, 0]), ("a", "c"): (pts, pts.copy())}
    offsets, info, residual = solve.stage2([], fits, pairs, [["a", "b", "c"]])
    ink = {k: solve.apply_offset(offsets[k], pts - ([1.0, 0] if k == "b" else 0)) for k in "abc"}
    assert np.abs(ink["a"] - ink["b"]).max() < 0.05 and np.abs(ink["a"] - ink["c"]).max() < 0.05
    assert info[0]["links used"] == 2


def test_a_link_too_far_off_is_dropped():
    pts = np.random.default_rng(2).uniform(5, 35, (40, 2))
    fits = {k: {"cut_to_photo": np.eye(3)} for k in "ab"}
    offsets, info, _ = solve.stage2([], fits, {("a", "b"): (pts, pts + [10.0, 0])}, [["a", "b"]])
    assert info[0]["links used"] == 0 and info[0]["links dropped"] == 1
