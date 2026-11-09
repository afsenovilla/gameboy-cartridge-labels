import cv2, numpy as np
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
    entries = [(base, np.ones((740, 850), bool), 20.0), (base.copy(), np.ones((740, 850), bool), 20.0),
               (moved, np.ones((740, 850), bool), 20.0)]
    out = restore.register(entries)
    before = np.abs(moved - base)[50:-50, 50:-50].mean()
    after = np.abs(out[2][0] - out[0][0])[50:-50, 50:-50].mean()
    assert after < before / 2


def test_a_blurred_label_photo_is_left_out_of_the_fine_band_where_its_blurred():
    rng = np.random.default_rng(0)
    sharp = rng.normal(0, 1, (60, 80)).astype(np.float32)
    blurred = cv2.GaussianBlur(sharp, (0, 0), 3)                       # its fine band nearly empty
    half = sharp.copy(); half[:, 40:] = blurred[:, 40:]                 # out of focus on the right only
    L = np.stack([sharp, sharp * 1.1, blurred, half])
    ok = restore.sharp_enough(L, np.ones(L.shape, bool), 0)
    assert ok[0].all() and ok[1].all() and not ok[2, 10:50, 10:70].any()
    assert ok[3, 10:50, 5:30].all() and not ok[3, 10:50, 55:75].any()


def test_dirt_on_one_label_photo_doesnt_push_the_others_out():
    rng = np.random.default_rng(1)
    L = np.stack([rng.normal(0, 1, (60, 80)).astype(np.float32) for _ in range(3)])
    L[0, 20:40, 20:40] *= 10                                           # a dirty patch: lots of "detail"
    assert restore.sharp_enough(L, np.ones(L.shape, bool), 0)[1:].all()


def label_with_text(extra_text=False, seed=0):
    """A synthetic label photo, 0..1 BGR at 20 px/mm: paper, a block of art, a line of text; optionally small text
    on the paper elsewhere (another print's, like a region variant's "this side out"); a little noise."""
    from test_match import textured
    img = np.full((740, 850, 3), 230, np.uint8)
    art = cv2.resize(textured(np.random.default_rng(8), 60, 90), (450, 300))
    img[100:400, 100:550] = art[..., None] if art.ndim == 2 else art
    cv2.putText(img, "GAME BOY", (100, 520), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (25, 25, 25), 5)
    if extra_text:
        cv2.putText(img, "this side out", (580, 650), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (25, 25, 25), 1)
    noise = np.random.default_rng(seed).normal(0, 0.01, img.shape).astype(np.float32)
    return np.clip(img.astype(np.float32) / 255 + noise, 0, 1)


def test_another_print_photo_counts_on_shared_art_not_where_it_has_small_text_the_print_lacks():
    ones = np.ones((740, 850), bool)
    own = [(label_with_text(seed=1), ones), (label_with_text(seed=2), ones)]
    other = (label_with_text(extra_text=True, seed=3), ones)
    counts = restore.where_other_print_photo_matches_own_photos(other, own)
    assert counts[150:350, 150:500].mean() > 0.95          # the art both prints share
    assert counts[460:540, 120:400].mean() > 0.9           # the text both prints share
    assert not counts[638:650, 580:672].any()              # the small text only the other print has


def test_another_print_photo_doesnt_count_off_its_photo():
    ones = np.ones((740, 850), bool)
    valid = ones.copy()
    valid[:, 600:] = False
    own = [(label_with_text(seed=1), ones)]
    counts = restore.where_other_print_photo_matches_own_photos((label_with_text(seed=3), valid), own)
    assert not counts[:, 600:].any()


def test_another_print_photo_is_registered_to_the_print_own_photos():
    base = label_with_text(seed=1)
    M = np.array([[1, 0.002, 1.5], [0.001, 1, -1.2], [0, 0, 1]], np.float32)
    moved = cv2.warpPerspective(base, M, (850, 740), borderMode=cv2.BORDER_REFLECT)
    own_ref = restore.evened_gray(base, np.ones((740, 850), bool))
    out = restore.register_to_own_photos(own_ref, (moved, np.ones((740, 850), bool), 20.0))
    before = np.abs(moved - base)[50:-50, 50:-50].mean()
    after = np.abs(out[0] - base)[50:-50, 50:-50].mean()
    assert after < before / 2
