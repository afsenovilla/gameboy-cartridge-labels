import json

import screenscraper_match as m

PRINTS = [{"print": "AGB-A3AE-USA-nora", "kind": "labels", "release": "AGB-A3AE", "serials": ["AGB-A3AE-USA"],
           "title": "Super Mario Advance 3 - Yoshi's Island", "system": "agb", "file": "AGB-A3AE-USA-nora.avif"},
          {"print": "AGB-A2CE-USA-vera", "kind": "labels", "release": "AGB-A2CE", "serials": ["AGB-A2CE-USA"],
           "title": "Castlevania - Aria of Sorrow", "system": "agb", "file": "x.avif"},
          {"print": "AGB-A2CP-EUR-lee", "kind": "wanted", "release": "AGB-A2CP", "serials": ["AGB-A2CP-EUR"],
           "title": "Castlevania - Aria of Sorrow", "system": "agb", "file": None},
          {"print": "AGB-ACTY-EUU-nora", "kind": "labels", "release": "AGB-ACTY", "serials": ["AGB-ACTY-EUU"],
           "title": "Creatures", "system": "agb", "file": None}]


def run(texts, names, region="us"):
    state = {"games": {"1": {"system": "gba", "names": names, "labels": [f"gba/1-{region}.png"]}}}
    release_of = m.release_index(PRINTS, database=None)
    import os
    real = os.path.exists
    os.path.exists = lambda p: True
    try:
        return m.match(state, PRINTS, release_of, lambda path: texts)[f"gba/1-{region}.png"]
    finally:
        os.path.exists = real


def test_an_exact_serial_gives_the_print():
    e = run(["YOSHISISLAND", "Nintendo", "AGB-A3AE-USA"], ["Yoshi's Island"])
    assert (e["how"], e["serial"], e["labels"]) == ("serial", "AGB-A3AE-USA", ["AGB-A3AE-USA-nora"])


def test_a_cut_off_serial_gives_its_release():
    e = run(["Casllevania", "AGB-A2CE-US"], ["Castlevania"])
    assert (e["how"], e["release"], e["labels"]) == ("serial", "AGB-A2CE", ["AGB-A2CE-USA-vera"])


def test_a_garbled_serial_is_near():
    e = run(["A6B-A3AE-USA"], ["Yoshi"])
    assert (e["how"], e["serial"]) == ("near", "AGB-A3AE-USA")


def test_a_serial_nobody_has_is_unknown_not_another_print():
    e = run(["creatures", "AGB-ACTX-EUR"], ["Creatures"], region="eu")
    assert (e["how"], e["serial"], e["labels"]) == ("unknown", "AGB-ACTX-EUR", [])
    assert e["guesses"][0]["release"] == "AGB-ACTY"


def test_no_serial_falls_back_to_the_title_on_the_same_system():
    e = run(["Castlevania", "Aria of Sorrow"], ["Castlevania - Aria of Sorrow"], region="eu")
    assert e["how"] == "title" and e["guesses"][0]["title"] == "Castlevania - Aria of Sorrow"


def test_catalogue_reads_both_files(tmp_path):
    a, b = tmp_path / "l.json", tmp_path / "w.json"
    a.write_text(json.dumps([{"id": "X-1", "serial": "DMG-A-USA", "release": "DMG-A", "title": "A", "system": "dmg", "file": "X-1.avif"}]))
    b.write_text(json.dumps([{"print": "X-2", "serials": ["DMG-B-JPN"], "release": "DMG-B", "title": "B", "system": "dmg"}]))
    got = m.catalogue(str(a), str(b))
    assert [(p["print"], p["kind"], p["serials"]) for p in got] == [("X-1", "labels", ["DMG-A-USA"]), ("X-2", "wanted", ["DMG-B-JPN"])]


def test_unknown_serials_are_listed_once_with_their_images():
    result = {"gb/1-us.png": {"how": "unknown", "serial": "DMG-AAUE-USA", "names": ["Pokemon Gold"]},
              "gb/1-wor.png": {"how": "unknown", "serial": "DMG-AAUE-USA", "names": ["Pokemon Gold", "Pokémon Or"]},
              "gb/2-us.png": {"how": "serial", "serial": "DMG-X-USA", "names": []}}
    assert m.unknown_serials(result) == {"DMG-AAUE-USA": (["Pokemon Gold", "Pokémon Or"], ["gb/1-us.png", "gb/1-wor.png"])}
