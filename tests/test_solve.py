import cv2, numpy as np
import solve, shapes


def drawn_label(H, size=(1200, 1000)):
    """A dark grey background with a light label: the canonical DMG label through H (label mm -> photo)."""
    img = np.full((size[1], size[0], 3), 60, np.uint8)
    quad = solve.project(H, solve.corners_mm("dmg"))
    cv2.fillPoly(img, [quad.astype(np.int32)], (220, 220, 220))
    return img


def test_snapping_finds_the_cut_from_a_start_a_few_mm_off():
    import edges
    H_true = solve.similarity_to_H((600, 500), 7.0, 15.0, "dmg")
    segs = edges.segments(drawn_label(H_true))["segments"].astype(np.float64)
    H0 = solve.similarity_to_H((620, 480), 5.0, 15.5, "dmg")       # about 2 mm and 2 degrees off
    H, support = solve.fit_outline(H0, "dmg", segs)
    assert H is not None and min(support) > 0.8
    err = np.abs(solve.project(H, solve.corners_mm("dmg")) - solve.project(H_true, solve.corners_mm("dmg"))).max()
    assert err < 3  # px, at 15 px/mm


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
