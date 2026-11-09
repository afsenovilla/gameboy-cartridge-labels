import cv2, numpy as np
import features

BLOBS = [(500, 300), (1800, 700), (3300, 400)]


def blob_image(w=4000, h=1000):
    """Grey with dark discs of radius 60 at BLOBS: SIFT finds a keypoint at each disc's centre."""
    img = np.full((h, w, 3), 200, np.uint8)
    for x, y in BLOBS:
        cv2.circle(img, (x, y), 60, (30, 30, 30), -1)
    return img


def test_points_are_in_the_full_photos_pixels():
    f = features.features(blob_image(), max_side=1000)
    assert f["scale"] == 4.0 and f["size"].tolist() == [4000, 1000]
    for x, y in BLOBS:
        assert np.hypot(*(f["points"] - [x, y]).T).min() < 8  # 2 px of what SIFT saw
    assert f["sizes"].max() > 60  # sizes in the photo's pixels too


def test_small_photos_are_not_scaled_up():
    f = features.features(blob_image(800, 400)[:, :, :], max_side=2000)
    assert f["scale"] == 1.0


def test_cap_and_types():
    rng = np.random.default_rng(1)
    noise = (rng.random((800, 800, 3)) * 255).astype(np.uint8)
    f = features.features(noise, max_keypoints=300)
    assert 0 < len(f["points"]) <= 300 + 10  # SIFT keeps ties at the cut
    assert f["descriptors"].dtype == np.uint8 and f["descriptors"].shape == (len(f["points"]), 128)
    assert len(f["sizes"]) == len(f["angles"]) == len(f["responses"]) == len(f["points"])


def test_unreadable_photo_gets_empty_arrays(tmp_path):
    p, out = tmp_path / "broken.jpg", tmp_path / "broken.npz"
    p.write_bytes(b"not an image")
    features.do_photo(("broken", str(p), str(out)))
    f = np.load(out)
    assert f["points"].shape == (0, 2) and f["descriptors"].shape == (0, 128)
