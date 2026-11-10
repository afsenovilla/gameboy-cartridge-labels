import numpy as np
import edge_fit


def test_edge_points_clear_of_corners():
    rect = edge_fit.SHAPES["dmg"]["recess"]
    pts, normals, sides = edge_fit.edge_points(rect)
    x1, y1, x2, y2 = rect
    on_x = np.isclose(pts[:, 0], x1) | np.isclose(pts[:, 0], x2)
    on_y = np.isclose(pts[:, 1], y1) | np.isclose(pts[:, 1], y2)
    assert np.all(on_x ^ on_y)  # on one side each, never at a corner
    corners = edge_fit.corners_of(rect)
    assert np.min(np.linalg.norm(pts[:, None] - corners[None], axis=2)) >= edge_fit.END - 1e-9
    assert set(sides) == {0, 1, 2, 3}
    assert np.allclose(np.linalg.norm(normals, axis=1), 1)


def test_corrections():
    center = (28.5, 37.5)
    for kind, n in (("homography", 8), ("similarity", 4)):
        assert np.allclose(edge_fit.correction(kind, np.zeros(n), center), np.eye(3))
    C = edge_fit.correction("similarity", [1.0, 0.0, np.radians(90), 0.0], center)
    assert np.allclose(edge_fit.project(C, [center])[0], [29.5, 37.5])  # turned about the center, then shifted


def test_models_give_a_logit_per_sample():
    for shape in ("dmg", "cgb", "agb"):
        for part, part_id in (("recess", 0), ("label", 1)):
            st = np.random.default_rng(0).random((5, 3, len(edge_fit.T)), dtype=np.float32)
            pos, conf = edge_fit.peaks(edge_fit.model(shape, part), st, part_id, np.array([0, 1, 2, 3, 0]), nearest=True)
            assert pos.shape == (5,) and np.all(np.abs(pos) <= edge_fit.HALF) and np.all((conf >= 0) & (conf <= 1))


def test_nothing_to_see_no_confidence():
    for value in (0, 128, 255):  # a blank photo: the models put the edge at a window's end, which counts as none
        photo = np.full((400, 400, 3), value, np.uint8)
        for part in ("recess", "label"):
            H, conf = edge_fit.refine(photo, np.diag([5.0, 5.0, 1.0]), "dmg", part, rounds=2)
            assert conf == 0
