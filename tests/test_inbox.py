import json

import cv2
import numpy as np

import inbox
import label_crop


def test_detect_finds_a_label_inside_its_cartridge():
    img = np.full((800, 700, 3), 140, np.uint8)
    cv2.rectangle(img, (100, 80), (600, 720), (120, 120, 120), -1)    # the cartridge
    cv2.rectangle(img, (180, 300), (520, 600), (90, 90, 90), 8)        # its recess
    cv2.rectangle(img, (200, 320), (500, 588), (40, 160, 230), -1)     # the label, 300 x 268
    q = np.array(label_crop.detect(img))
    assert np.abs(q - [[200, 320], [500, 320], [500, 588], [200, 588]]).max() < 8


def test_crop_is_820_wide_with_the_label_proportions():
    img = np.zeros((400, 400, 3), np.uint8)
    out = label_crop.crop(img, [[0, 0], [300, 0], [300, 268], [0, 268]])
    assert out.shape[1] == 820 and abs(out.shape[0] - 732) <= 1


def test_describe_says_if_missing_or_already_there():
    have = {"DMG-T3-FAH": [("DMG-T3-FAH", 600, None)]}
    c = inbox.describe({"serial": "DMG-T3-SCN"}, have, {"DMG-T3-SCN"}, {"DMG-T3": "Adventure Island"})
    assert c["missing"] and c["existing"] == [] and c["title"] == "Adventure Island"
    c = inbox.describe({"serial": "DMG-T3-FAH"}, have, set(), {})
    assert not c["missing"] and c["existing"] == [{"id": "DMG-T3-FAH", "width": 600}]
    c = inbox.describe({"serial": "DMG-F4-USA-1"}, {}, set(), {"DMG-F4": "4-in-1 Fun Pak"})
    assert c["title"] == "4-in-1 Fun Pak"


def test_a_serial_in_the_file_name_is_a_hint():
    assert inbox.SERIAL.search("cgb-bsfp-hol_photo.jpg").group(0).upper() == "CGB-BSFP-HOL"


def test_an_unknown_serial_gets_its_lookalike_suggested():
    c = inbox.describe({"serial": "AGB-8D2J-JPN"}, {}, set(), {"AGB-BD2J": "Duel Masters 2"})
    assert not c["known"] and c["suggest"] == "AGB-BD2J-JPN"


def test_a_new_photo_with_an_accepted_ones_name_is_new(tmp_path, monkeypatch):
    monkeypatch.setattr(inbox, "INBOX", str(tmp_path))
    monkeypatch.setattr(inbox, "LIST", str(tmp_path / "c.json"))
    monkeypatch.setattr(inbox, "PREVIEWS", str(tmp_path / "p"))
    monkeypatch.setattr(inbox, "OUT", str(tmp_path))
    monkeypatch.setattr(inbox, "read_serial", lambda img: (None, []))
    monkeypatch.setattr(inbox, "catalogue", lambda: ({}, set(), {}))
    img = np.full((300, 300, 3), 120, np.uint8)
    cv2.imwrite(str(tmp_path / "s-l1200.jpg"), img)
    inbox.save([{"id": "old", "file": "s-l1200.jpg", "status": "accepted"}])
    assert inbox.process() == 1
    assert inbox.process() == 0


def test_crops_get_the_labels_true_proportions():
    img = np.zeros((900, 900, 3), np.uint8)
    stretched = [[0, 0], [300, 0], [300, 400], [0, 400]]       # photographed at an angle: too tall
    assert label_crop.crop(img, stretched, aspect=label_crop.aspect_for("DMG-K2J")).shape[:2] == (720, 820)
    assert label_crop.crop(img, stretched, aspect=label_crop.aspect_for("AGB-BD2J-JPN")).shape[:2] == (413, 820)
    assert label_crop.aspect_for("", [[0, 0], [400, 0], [400, 220], [0, 220]]) == label_crop.ASPECT["agb"]


def test_avif_photos_are_read(tmp_path):
    from PIL import Image
    p = tmp_path / "x.avif"
    Image.fromarray(np.full((50, 60, 3), 200, np.uint8)).save(p)
    assert inbox.imread(str(p)).shape == (50, 60, 3)


def test_a_variant_the_database_lacks_takes_the_title_of_the_serial_it_was_fetched_for():
    c = {"serial": "DMG-ACDX-EUR", "file": "DMG-ACWP-EUR__launchbox_cebae0e8.jpg"}
    inbox.describe(c, {}, {"DMG-ACWP-EUR"}, {"DMG-ACWP": "Cool Hand"})
    assert (c["known"], c["title"], c["fetched_as"], c["missing"]) == (False, "Cool Hand", "DMG-ACWP-EUR", False)


def test_a_serial_the_catalogue_has_a_label_of_is_known_even_if_the_database_lacks_it():
    c = {"serial": "AGB-B2DU-AUS", "file": "AGB-B2DP-EUR__launchbox_47152eea.png"}
    inbox.describe(c, {"AGB-B2DU-AUS": [("AGB-B2DU-AUS", 600, None)]}, set(), {})
    assert c["known"] and c["existing"]
