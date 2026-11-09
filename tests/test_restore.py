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


def test_soft_median_ignores_an_outlier():
    rng = np.random.default_rng(2)
    good = 0.5 + 0.01 * rng.standard_normal((5, 10, 10, 3))
    vals = np.concatenate([good, np.full((1, 10, 10, 3), 5.0)])   # one label photo with glare
    est = restore.tukey(vals.astype(np.float32), np.ones((6, 10, 10), np.float32))
    assert np.abs(est - 0.5).max() < 0.02


def test_finest_band_by_resolution():
    assert restore.finest_band(20) == 0 and restore.finest_band(40) == 0
    assert restore.finest_band(10) == 1 and restore.finest_band(5) == 2


def test_evening_a_photo_to_itself_keeps_it():
    img = np.random.default_rng(3).random((40, 50, 3)).astype(np.float32)
    out = restore.even_to(img, img.copy(), np.ones((40, 50), bool))
    assert np.abs(out - img).max() < 1e-5
