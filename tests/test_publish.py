import json, os
import numpy as np
import publish, straighten


def test_cut_is_the_canonical_label_in_whole_pixels():
    (w, h), _ = straighten.canvas("dmg")
    img = np.zeros((h, w, 3), np.uint8)
    x, y, cw, ch = publish.crop_box("dmg")
    img[y:y + ch, x:x + cw] = 255                        # the label area white, the margin black
    c = publish.cut(img, "dmg")
    assert c.shape == (740, 850, 3) and c.min() == 255
    assert publish.cut(np.zeros((h, w, 3)), "agb").shape[:2] == (440, 860)


def test_sources_by_sha1(tmp_path):
    f = tmp_path / "photo-sources.json"
    f.write_text(json.dumps({"abc": {"source": "mercari", "file": "mercari/dmg/DMG-A1J.jpg", "page_url": "https://x/1"}}))
    assert publish.sources(str(f)) == {"abc": {"source": "mercari", "page_url": "https://x/1", "image_url": None}}


def test_poor_fits_from_solve():
    solved = {"a@1,1": {"fallback": "a poor fit: kept"}, "b@1,1": {"fallback": None}, "c@1,1": {}}
    assert publish.poor_fits(solved) == {"a@1,1"}
