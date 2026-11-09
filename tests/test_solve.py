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
    H, placement, support, error = solve.fit_nested(H0, "dmg", segs)
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


def test_pixel_agreement_finds_the_same_print_shifted_and_not_another():
    from test_match import textured
    print_ = textured(np.random.default_rng(0), 400, 500)
    # two photos of one print: a's cut at the print's origin, b's cut 1 mm right and 0.5 down (b's frame -> a's: +1, +0.5)
    px = 10  # photo px per mm
    cut_a = np.array([[px, 0, 20.0], [0, px, 20.0], [0, 0, 1]])
    cut_b = np.array([[px, 0, 20.0 + px], [0, px, 20.0 + 0.5 * px], [0, 0, 1]])
    va = solve.compare_view(print_, cut_a, "dmg")
    vb = solve.compare_view(print_, cut_b, "dmg")
    share, textured_tiles = solve.pixel_agreement(va, vb, 0.0, np.array([1.0, 0.5]), "dmg")
    assert textured_tiles > 50 and share > 0.9
    share, _ = solve.pixel_agreement(va, vb, 0.0, np.array([-1.0, -0.5]), "dmg")   # the wrong way round
    assert share < 0.3
    other = solve.compare_view(textured(np.random.default_rng(1), 400, 500), cut_b, "dmg")
    assert solve.pixel_agreement(va, other, 0.0, np.array([1.0, 0.5]), "dmg")[0] < 0.3


def test_the_choice_learns_which_feature_tells_right_from_wrong():
    rng = np.random.default_rng(3)
    n = len(solve.FEATURES)
    right = rng.normal(0, 1, (200, n)); right[:, 7] += 2.0   # the agreeing share higher when right
    wrong = rng.normal(0, 1, (200, n))
    model = solve.train_choice(list(right) + list(wrong), [1] * 200 + [0] * 200)
    assert int(np.argmax(model[2])) == 7
    assert solve.predict(model, right).mean() > solve.predict(model, wrong).mean() + 0.3


def test_confident_needs_two_kinds_of_start_agreeing():
    c = lambda start: {"start": start}
    apart = np.array([[0, 0.2, 0.3], [0.2, 0, 0.1], [0.3, 0.1, 0]])
    assert solve.confident([c("outline (label)"), c("outline (recess)"), c("outline (label)")], apart, 0)
    assert not solve.confident([c("outline (label)"), c("outline (label)"), c("outline (label)")], apart, 0)
    far = np.array([[0, 5.0], [5.0, 0]])
    assert not solve.confident([c("placed by X"), c("outline (body)")], far, 0)


def test_a_degenerate_label_homography_isnt_usable():
    assert solve.usable(solve.similarity_to_H((500, 500), 0, 10, "dmg"), "dmg")
    singular = np.array([[1.0, 2, 3], [2, 4, 6], [0, 0, 1]])
    assert not solve.usable(singular, "dmg")
    assert not solve.usable(np.full((3, 3), np.nan), "dmg")
    tiny = solve.similarity_to_H((500, 500), 0, 0.1, "dmg")          # under 20 px across
    assert not solve.usable(tiny, "dmg")


def test_apart_survives_a_singular_candidate():
    good = {"cut_to_photo": solve.similarity_to_H((500, 500), 0, 10, "dmg")}
    bad = {"cut_to_photo": np.array([[1.0, 2, 3], [2, 4, 6], [0, 0, 1]])}
    assert solve.apart_mm(bad, good, "dmg") == float("inf")
