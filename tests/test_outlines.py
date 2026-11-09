import cv2, numpy as np
import outlines, solve


def test_a_drawn_cartridge_gives_starts_near_its_pose():
    H_true = solve.similarity_to_H((700, 700), 4.0, 15.0, "dmg") @ np.linalg.inv(solve.label_to_plastic("dmg"))
    from test_solve import drawn_cartridge
    img = drawn_cartridge(H_true)
    quads = outlines.outline_quads(img)
    starts = outlines.outline_starts(quads, "dmg", (img.shape[1], img.shape[0]))
    assert {what for _, _, what in starts} >= {"label", "recess", "body"}
    box = solve.MODELS["dmg"]["box"]
    corners = [[box[0], box[1]], [box[2], box[1]], [box[2], box[3]], [box[0], box[3]]]
    best = min(np.abs(outlines.project(H, corners) - outlines.project(H_true, corners)).max() for H, _, _ in starts)
    assert best < 20  # px at 15 px/mm: a start the fit converges from


def test_tilt_and_upright_only():
    assert abs(outlines.tilt(np.eye(3))) < 1e-9
    upside_down = np.array([[-1.0, 0, 100], [0, -1, 100], [0, 0, 1]])
    assert abs(abs(outlines.tilt(upside_down)) - 180) < 1e-9
