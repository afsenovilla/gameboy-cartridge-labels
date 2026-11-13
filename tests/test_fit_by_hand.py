import numpy as np
import fit_by_hand


def test_view_photo_round_trip():
    photo_to_ink = np.array([[0.08, 0.002, -9.0], [-0.001, 0.079, -25.0], [-5e-5, -9e-6, 1.0]])
    view = np.array([[100.0, 100.0], [950.0, 110.0], [940.0, 830.0], [105.0, 840.0]])
    photo = fit_by_hand.view_to_photo(photo_to_ink, view)
    assert np.allclose(fit_by_hand.photo_to_view(photo_to_ink, photo), view, atol=1e-6)


def test_view_origin_is_the_margin():
    # the image's pixel centre (0, 0) lies MARGIN mm (less half a pixel) outside the nominal label
    import straighten
    ink = np.linalg.inv(np.eye(3))  # photo = ink mm
    p = fit_by_hand.view_to_photo(ink, [[0.0, 0.0]])[0]
    s = 1 / straighten.PX_PER_MM
    assert np.allclose(p, [-straighten.MARGIN + s / 2] * 2)
