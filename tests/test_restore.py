import numpy as np
import restore


def test_oklab_round_trip():
    img = np.random.default_rng(0).random((20, 30, 3)).astype(np.float32)
    assert np.abs(restore.from_oklab(restore.to_oklab(img)) - img).max() < 1e-4


def test_pyramid_collapses_back():
    img = np.random.default_rng(1).random((120, 200, 3)).astype(np.float32)
    levels = restore.pyramid(img)
    assert len(levels) >= 4 and levels[0].shape == img.shape
    assert np.abs(restore.collapse(levels) - img).max() < 1e-4


def test_finest_band_by_resolution():
    assert restore.finest_band(20) == 0 and restore.finest_band(40) == 0
    assert restore.finest_band(10) == 1 and restore.finest_band(5) == 2


def test_evening_a_photo_to_itself_keeps_it():
    img = np.random.default_rng(3).random((40, 50, 3)).astype(np.float32)
    out = restore.even_to(img, img.copy(), np.ones((40, 50), bool))
    assert np.abs(out - img).max() < 1e-5


def test_dark_grey_ink_becomes_black_and_the_paper_stays_white():
    img = np.full((100, 100, 3), 0.8, np.float32)
    img[:30] = 0.15                                                       # a solid black printed as dark grey
    img[:30, :, 0] += np.linspace(-0.02, 0.02, 100)[None, :]              # its texture
    _, out = restore.paper_white(img)
    assert out[:30].mean() < 0.03 and np.abs(out[60:] - 1).max() < 1e-2


def test_paper_white_makes_the_paper_white_and_leaves_full_colour_art():
    img = np.full((100, 100, 3), 0.8, np.float32); img[..., 0] = 0.75     # bluish-grey paper, BGR
    img[30:60, 30:60] = [0.1, 0.2, 0.7]                                    # a red block
    paper, white = restore.paper_white(img)
    assert white is not None and np.abs(white[0, 0] - 1).max() < 1e-2      # the paper white
    assert white[40, 40, 2] > white[40, 40, 0]                             # the red still red
    art = np.random.default_rng(4).random((100, 100, 3)).astype(np.float32)
    art[..., 2] = 0.9; art[..., 0] = 0.1                                   # all saturated: no paper
    assert restore.paper_white(art) == (None, None)


def test_registering_lines_up_a_shifted_and_slightly_bent_copy():
    import cv2
    from test_match import textured
    base = cv2.resize(textured(np.random.default_rng(8), 150, 170), (850, 740)).astype(np.float32) / 255
    M = np.array([[1, 0.002, 1.5], [0.001, 1, -1.2], [0, 0, 1]], np.float32)    # about 1.5 px off, slightly sheared
    moved = cv2.warpPerspective(base, M, (850, 740), borderMode=cv2.BORDER_REFLECT)
    entries = [(base, np.ones((740, 850), bool), None, 20.0), (base.copy(), np.ones((740, 850), bool), None, 20.0),
               (moved, np.ones((740, 850), bool), None, 20.0)]
    out = restore.register(entries)
    before = np.abs(moved - base)[50:-50, 50:-50].mean()
    after = np.abs(out[2][0] - out[0][0])[50:-50, 50:-50].mean()
    assert after < before / 2
