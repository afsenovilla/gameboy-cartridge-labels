import serials


def test_reads_dashed_spaced_and_undashed():
    assert "DMG-APSJ-JPN" in serials.reads("DMG-APSJ-JPN")
    assert "DMG-APSJ-JPN" in serials.reads("DMG APSJ JPN")
    assert "DMG-APSJ-JPN" in serials.reads("DMG-APSJJPN")


def test_reads_look_alikes():
    assert "DMG-APSJ-JPN" in serials.reads("OMG-APSJ-JPN")
    assert "DMG-APSJ-JPN" in serials.reads("DMG一APSJ一JPN")
    assert "AGB-AXVE-USA" in serials.reads("ａｇｂ-axve-usa")  # full width, lower case


def test_reads_prefix_and_number():
    assert "DIS-CGB-AZ7E-USA" in serials.reads("DIS-CGB-AZ7E-USA")
    assert "DMG-MQ-UKV-1" in serials.reads("DMG-MQ-UKV-1")


def test_reads_also_without_region():
    assert serials.reads("DMG-MQ-UKV") == ["DMG-MQ-UKV", "DMG-MQ"]


def test_reads_nothing_in_plain_text():
    assert serials.reads("Nintendo GAME BOY") == []


def test_release_drops_unknown_region_and_prefix():
    release_of = {"DMG-A8": {"id": "dmg-1"}, "CGB-AZ7E-USA": {"id": "cgb-2"}}
    assert serials.release("DMG-A8-UKV", release_of)["id"] == "dmg-1"
    assert serials.release("DIS-CGB-AZ7E-USA", release_of)["id"] == "cgb-2"
    assert serials.release("DMG-ZZ-USA", release_of) is None


DATABASE = {"CGB-B96J-JPN": {"id": "cgb-1"}, "AGB-BPEJ-JPN": {"id": "agb-1"}, "DMG-APSJ-JPN": {"id": "dmg-1"},
            "DMG-APBJ-JPN": {"id": "dmg-2"}}


def test_near_serials_from_the_sample():
    regions = serials.by_region(DATABASE)
    for read, serial in [("B-B96J-JPN", "CGB-B96J-JPN"), ("COB-B96J-JPN", "CGB-B96J-JPN"),
                         ("GAB-896J-JPN", "CGB-B96J-JPN"), ("AGD-BPEJ-JPN", "AGB-BPEJ-JPN")]:
        assert [s for s, _, _ in serials.near(read, regions)] == [serial]


def test_near_leaves_exact_ambiguous_and_plain_text():
    regions = serials.by_region(DATABASE)
    assert serials.near("DMG-APSJ-JPN", regions) == []   # exact: reads()'s
    assert serials.near("DMG-AP?J-JPN", regions) == []   # APSJ or APBJ
    assert serials.near("MADE IN JAPAN", regions) == []
