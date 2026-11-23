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


def test_a_region_sharing_an_image_gets_its_answer():
    state = {"games": {"1": {"system": "gba", "names": ["Yoshi"], "labels": ["gba/1-us.png"], "same": {"gba/1-wor.png": "gba/1-us.png"}}}}
    import os
    real = os.path.exists
    os.path.exists = lambda p: True
    try:
        r = m.match(state, PRINTS, m.release_index(PRINTS, database=None), lambda p: ["AGB-A3AE-USA"])
    finally:
        os.path.exists = real
    assert r["gba/1-wor.png"]["serial"] == "AGB-A3AE-USA" and r["gba/1-wor.png"]["same_as"] == "gba/1-us.png"
    assert r["gba/1-wor.png"]["region"] == "wor"


def test_review_shows_a_shared_image_once_with_its_regions():
    import screenscraper_review as r
    matches = {"gb/1-fr.png": {"how": "serial", "system": "gb", "game": "1", "names": ["A"], "serial": "DMG-A-FRA",
                               "labels": ["DMG-A-FRA-x"], "wanted": [], "text": ["DMG-A-FRA"]},
               "gb/1-eu.png": {"how": "serial", "system": "gb", "game": "1", "names": ["A"], "same_as": "gb/1-fr.png"},
               "gb/2-us.png": {"how": "none", "system": "gb", "game": "2", "names": ["B"], "text": []}}
    got = r.items(matches, [{"id": "DMG-A-FRA-x", "file": "DMG-A-FRA-x.avif"}])
    assert [x["img"] for x in got] == ["gb/2-us.png", "gb/1-fr.png"]
    assert got[1]["also"] == ["gb/1-eu.png"] and got[1]["ours"] == "../published-labels/DMG-A-FRA-x.avif"


def test_site_labels_one_per_distinct_image_with_serial_or_screenscraper_name():
    import screenscraper_site as s
    matches = {"gba/1-us.png": {"how": "serial", "system": "gba", "game": "1", "region": "us", "names": ["Yoshi"],
                                "serial": "AGB-A3AE-USA", "release": "AGB-A3AE", "title": "Yoshi's Island"},
               "gba/1-wor.png": {"how": "serial", "system": "gba", "game": "1", "region": "wor", "same_as": "gba/1-us.png"},
               "gb/2-jp.png": {"how": "title", "system": "gb", "game": "2", "region": "jp", "names": ["Qix"], "serial": None},
               "gbc/3-us.png": {"how": "serial", "system": "gbc", "game": "3", "region": "us", "names": ["X"], "serial": "AGB-A3AE-USA"},
               "gb/4-us.png": {"how": "none", "system": "gb", "game": "4", "region": "us", "names": ["Fan"]}}
    s.size_of = lambda p: [600, 528]
    got = s.labels(matches, ignore={"4"}, exists=lambda p: True)
    assert [(l["id"], l["serial"], l["system"], l["title"]) for l in got] == [
        ("SS-2-jp", "", "dmg", "Qix"), ("AGB-A3AE-USA", "AGB-A3AE-USA", "agb", "Yoshi's Island"),
        ("AGB-A3AE-USA-2", "AGB-A3AE-USA", "agb", "X")]


def test_missing_lists_the_releases_no_label_is_of():
    import screenscraper_site as s
    entries = [{"serial": "AGB-A3AE-USA", "release": "AGB-A3AE"}, {"serial": "DMG-AAUE-USA", "release": ""}]
    releases = {"AGB-A3AE": {"id": "AGB-A3AE", "title": "Yoshi", "system": "agb", "cartridgeSerials": ["AGB-A3AE-USA"]},
                "DMG-AAUE": {"id": "DMG-AAUE", "title": "Pokemon Gold", "system": "dmg", "cartridgeSerials": []},
                "AGB-ACHJ": {"id": "AGB-ACHJ", "title": "Castlevania", "system": "agb", "cartridgeSerials": []}}
    got = s.missing(entries, releases)
    assert [(w["print"], w["region"], w["serials"]) for w in got] == [("AGB-ACHJ", "JPN", ["AGB-ACHJ"])]


def test_missing_is_one_per_serial():
    import screenscraper_site as s
    releases = {"DMG-XA": {"id": "DMG-XA", "title": "Asterix", "system": "dmg", "cartridgeSerials": ["DMG-XA-NOE", "DMG-XA-SCN"]},
                "AGB-A2CE": {"id": "AGB-A2CE", "title": "Castlevania", "system": "agb", "cartridgeSerials": ["AGB-A2CE-USA"]},
                "AGB-A2CP": {"id": "AGB-A2CP", "title": "Castlevania", "system": "agb", "cartridgeSerials": ["AGB-A2CP-EUR", "AGB-A2CP-NOE"]}}
    entries = [{"serial": "DMG-XA-FAH", "release": "DMG-XA"}, {"serial": "AGB-A2CE", "release": "AGB-A2CE"}, {"serial": "AGB-A2CP", "release": "AGB-A2CP"}]
    got = [w["print"] for w in s.missing(entries, releases)]
    assert got == ["DMG-XA-NOE", "DMG-XA-SCN", "AGB-A2CP-EUR", "AGB-A2CP-NOE"]  # by title


def test_serve_catalogue_writes_reports_into_ignore_once(tmp_path):
    import serve_catalogue as s
    ign = tmp_path / "ignore.txt"
    ign.write_text("gb/1-us.png  # old", encoding="utf-8")
    reports = {"gb/1-us.png": {"title": "A", "serial": "S", "reasons": ["Not a label"]},
               "gbc/2-jp.png": {"title": "Checkmate", "serial": "SS-2-jp", "reasons": ["Not a label"], "note": "a\nbox"}}
    assert s.apply(reports, str(ign)) == 1
    assert ign.read_text(encoding="utf-8") == "gb/1-us.png  # old\ngbc/2-jp.png  # Checkmate (SS-2-jp): Not a label - a box\n"


def test_an_added_label_is_saved_under_its_serial(tmp_path):
    import serve_catalogue as s, pytest, json as j
    e = s.add("dmg-aaue-usa", "", "Pokemon Gold", "dmg", b"\x89PNG...", "image/png", out=str(tmp_path))
    assert e["file"] == "added/DMG-AAUE-USA.png" and e["release"] == "DMG-AAUE" and (tmp_path / "added" / "DMG-AAUE-USA.png").exists()
    assert s.add("DMG-AAUE-USA", "", "", "", b"x", "image/png", out=str(tmp_path))["file"] == "added/DMG-AAUE-USA_2.png"
    assert len(j.loads((tmp_path / "added.json").read_text(encoding="utf-8"))) == 2
    with pytest.raises(ValueError):
        s.add("hello", "", "", "", b"x", "image/png", out=str(tmp_path))
    with pytest.raises(ValueError):
        s.add("DMG-AAUE-USA", "", "", "", b"x", "text/html", out=str(tmp_path))


def test_database_fixes_correct_misread_serials(tmp_path):
    import screenscraper_site as s
    f = tmp_path / "fixes.json"
    f.write_text(json.dumps({"_note": "x", "DMG-A4RJ-JPI": "DMG-A4RJ-JPN"}), encoding="utf-8")
    assert s.database_fixes(str(f)) == {"DMG-A4RJ-JPI": "DMG-A4RJ-JPN"}


def test_missing_tells_whole_games_from_other_versions():
    import screenscraper_site as s
    assert s.game_of("DMG-AAUE") == s.game_of("DMG-AAUP-EUR") == s.game_of("DMG-AAUJ-JPN") == "DMG-AAU"
    assert s.game_of("DMG-T3J") == s.game_of("DMG-T3-NOE") == "DMG-T3"
    releases = {"DMG-XA": {"id": "DMG-XA", "title": "Asterix", "system": "dmg", "cartridgeSerials": ["DMG-XA-NOE"]},
                "DMG-QQQE": {"id": "DMG-QQQE", "title": "Nothing", "system": "dmg", "cartridgeSerials": ["DMG-QQQE-USA"]}}
    got = {w["print"]: w["kind"] for w in s.missing([{"serial": "DMG-XA-FAH", "release": "DMG-XA"}], releases)}
    assert got == {"DMG-XA-NOE": "variant", "DMG-QQQE-USA": "game"}


def test_added_labels_come_from_the_folder_even_if_added_json_lost_them(tmp_path):
    import screenscraper_site as s
    (tmp_path / "added").mkdir()
    for n in ("DMG-AAUP-EUR-1.png", "AGB-AAKJ-JPN.png", "DMG-XA-FAH_2.png", "notes.txt"):
        (tmp_path / "added" / n).write_bytes(b"x")
    (tmp_path / "added.json").write_text(json.dumps([{"id": "AGB-AAKJ-JPN", "serial": "AGB-AAKJ-JPN", "release": "AGB-AAKJ",
        "title": "Airforce Delta II", "system": "agb", "file": "added/AGB-AAKJ-JPN.png", "source_width": 440}]), encoding="utf-8")
    got = {e["id"]: (e["serial"], e["title"]) for e in s.added(out=str(tmp_path), titles={"DMG-AAUP": "Pokemon - Gold Version"})}
    assert got == {"AGB-AAKJ-JPN": ("AGB-AAKJ-JPN", "Airforce Delta II"), "DMG-AAUP-EUR-1": ("DMG-AAUP-EUR-1", "Pokemon - Gold Version"),
                   "DMG-XA-FAH_2": ("DMG-XA-FAH", "DMG-XA-FAH")}
