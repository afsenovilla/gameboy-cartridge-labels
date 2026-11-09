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


def test_paper_white_makes_the_paper_white_and_leaves_full_colour_art():
    img = np.full((100, 100, 3), 0.8, np.float32); img[..., 0] = 0.75     # bluish-grey paper, BGR
    img[30:60, 30:60] = [0.1, 0.2, 0.7]                                    # a red block
    paper, white = restore.paper_white(img)
    assert white is not None and np.abs(white[0, 0] - 1).max() < 1e-3      # the paper white (clipped)
    assert white[40, 40, 2] > white[40, 40, 0]                             # the red still red
    art = np.random.default_rng(4).random((100, 100, 3)).astype(np.float32)
    art[..., 2] = 0.9; art[..., 0] = 0.1                                   # all saturated: no paper
    assert restore.paper_white(art) == (None, None)
