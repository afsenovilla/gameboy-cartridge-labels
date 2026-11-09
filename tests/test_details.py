import cv2, numpy as np
import details, features, find
from test_match import textured


def test_detail_found_twice_with_its_scale(tmp_path):
    rng = np.random.default_rng(3)
    detail = textured(rng, 240, 400)                      # 20 x 12 mm at 20 px/mm
    folder = tmp_path / "details"
    folder.mkdir()
    cv2.imwrite(str(folder / "logo.png"), detail)
    photo = textured(rng, 900, 1400)
    small = cv2.resize(detail, (300, 180))                # 15 px/mm
    photo[100:280, 200:500] = small
    photo[600:780, 1000:1300] = small                     # a second cartridge
    details._details = None
    found = details.detect(features.features(photo), details.load_details(str(folder)))
    details._details = None
    assert len(found) == 2
    for d in found:
        assert d["detail"] == "logo.png" and abs(d["px_per_mm"] - 15) < 1
    assert sorted(round(d["centre"][0] / 50) for d in found) == [7, 23]


def test_a_detail_alone_makes_a_label_photo_with_a_label_sized_circle():
    texts = {"a": {"size": [1000, 1000], "lines": []}}
    corners = [[400, 400], [550, 400], [550, 490], [400, 490]]
    detections = {"a": [{"detail": "logo.png", "corners": corners, "centre": [475, 445], "px_per_mm": 10.0, "inliers": 30}]}
    result = find.find({"a": "photos/a.jpg"}, texts, [], {}, detections)
    lp, = result["label_photos"]
    assert lp["found_by"] == "detail" and lp["radius"] == find.LABEL_DIAGONAL * 10
    assert lp["details"][0]["detail"] == "logo.png"
    assert find.find({"a": "photos/a.jpg"}, texts, [], {}, None)["label_photos"] == []
