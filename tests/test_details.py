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
    detections = {"a": [{"detail": "logo.png", "size": [150, 90], "corners": corners, "centre": [475, 445], "px_per_mm": 10.0, "inliers": 30}]}
    result = find.find({"a": "photos/a.jpg"}, texts, [], {}, detections)
    lp, = result["label_photos"]
    assert lp["found_by"] == "detail" and lp["radius"] == find.LABEL_DIAGONAL * 10
    assert lp["details"][0]["detail"] == "logo.png"
    assert find.find({"a": "photos/a.jpg"}, texts, [], {}, None)["label_photos"] == []


def test_a_fixed_place_detail_places_the_label():
    # a 100 x 40 px detail (5 x 2 mm) centred at (10, 5) mm on a DMG label, seen at 10 px/mm with the label's top left
    # at (300, 200): the detail's corners are at (300 + 10 * (10 -+ 2.5), 200 + 10 * (5 -+ 1))
    corners = [[375, 240], [425, 240], [425, 260], [375, 260]]
    places = {"logo.png": {"shape": "dmg", "centre_mm": [10, 5]}}
    label = details.placed_label({"detail": "logo.png", "corners": corners}, places, (100, 40), {"dmg": (42.5, 37)})
    assert np.abs(label - [[300, 200], [725, 200], [725, 570], [300, 570]]).max() < 0.01
    assert details.placed_label({"detail": "other.png", "corners": corners}, places, (100, 40), {"dmg": (42.5, 37)}) is None


def test_a_serial_of_another_shape_keeps_a_detail_from_placing():
    corners = [[375, 240], [425, 240], [425, 260], [375, 260]]
    places = {"logo.png": {"shape": "dmg", "centre_mm": [10, 5]}}
    d = {"detail": "logo.png", "size": [100, 40], "corners": corners, "centre": [400, 250], "px_per_mm": 10.0, "inliers": 30}
    texts = {"a": {"size": [1000, 1000], "lines": [{"text": "CGB-B96J-JPN", "confidence": 1, "corners": [[380, 300], [580, 300], [580, 320], [380, 320]]}]},
             "b": {"size": [1000, 1000], "lines": []}}
    result = find.find({"a": "a", "b": "b"}, texts, [], {"CGB-B96J-JPN": {"id": "cgb-1"}}, {"a": [d], "b": [d]}, places=places)
    by = {lp["photo"]: lp for lp in result["label_photos"]}
    assert by["a"]["placed_by"] is None and by["a"]["shape"] == "cgb"
    assert by["b"]["placed_by"] == "logo.png" and by["b"]["shape"] == "dmg"
