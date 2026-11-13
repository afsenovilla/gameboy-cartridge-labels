import print_ids

T = "2026-11-13T12:00:00+01:00"


def pr(keys, serial="DMG-APSJ-JPN", release="DMG-APSJ"):
    return {"keys": keys, "serial": serial, "release": release}


def same(keys):
    return {k: k for k in keys}


def test_first_run_gives_new_ids_of_the_serial_and_a_name():
    prints = [pr(["a@1,1", "b@1,1"]), pr(["c@1,1"])]
    reg, changes = print_ids.assign(prints, {"prints": {}, "gone": {}}, {}, T)
    ids = [p["id"] for p in prints]
    assert all(i.startswith("DMG-APSJ-JPN-") and print_ids.split_id(i)[1] in print_ids.NAMES for i in ids)
    assert ids[0] != ids[1]
    assert {c["kind"] for c in changes} == {"new"}
    assert reg["prints"][ids[0]] == {"created": T, "keys": ["a@1,1", "b@1,1"]}


def test_ids_kept_when_nothing_changed_and_when_a_photo_joins():
    prints = [pr(["a@1,1", "b@1,1"]), pr(["c@1,1", "d@1,1"], serial="CGB-B33J-JPN")]
    reg, _ = print_ids.assign(prints, {"prints": {}, "gone": {}}, {}, T)
    first = [p["id"] for p in prints]
    again = [pr(["a@1,1", "b@1,1", "e@1,1"]), pr(["c@1,1", "d@1,1"], serial="CGB-B33J-JPN")]
    reg2, changes = print_ids.assign(again, reg, same(["a@1,1", "b@1,1", "c@1,1", "d@1,1"]), T)
    assert [p["id"] for p in again] == first
    assert {c["kind"] for c in changes} == {"kept"}
    assert reg2["prints"][first[0]]["keys"] == ["a@1,1", "b@1,1", "e@1,1"]


def test_merge_split_gone():
    old = {"prints": {"DMG-APSJ-JPN-lisa": {"keys": ["a@1,1", "b@1,1", "c@1,1"], "created": "1"},
                      "DMG-APSJ-JPN-bob": {"keys": ["d@1,1"], "created": "2"},
                      "DMG-APSJ-JPN-tom": {"keys": ["x@1,1"], "created": "3"}}, "gone": {}}
    # lisa's a, b and bob's d are now one print; lisa's c is a print of its own; tom's x is gone
    prints = [pr(["a@1,1", "b@1,1", "d@1,1"]), pr(["c@1,1"])]
    reg, changes = print_ids.assign(prints, old, {"a@1,1": "a@1,1", "b@1,1": "b@1,1", "c@1,1": "c@1,1", "d@1,1": "d@1,1", "x@1,1": None}, T)
    assert prints[0]["id"] == "DMG-APSJ-JPN-lisa"
    assert reg["gone"]["DMG-APSJ-JPN-bob"] == {"why": "merged", "into": "DMG-APSJ-JPN-lisa", "datetime": T}
    assert reg["gone"]["DMG-APSJ-JPN-tom"]["why"] == "no label photo left"
    assert reg["prints"][prints[1]["id"]]["split_from"] == "DMG-APSJ-JPN-lisa"
    # names are never reused: not lisa, bob or tom
    assert print_ids.split_id(prints[1]["id"])[1] not in {"lisa", "bob", "tom"}


def test_a_corrected_serial_renames_keeping_the_name_and_a_lost_serial_doesnt():
    old = {"prints": {"DMG-APSJ-JPN-lisa": {"keys": ["a@1,1"], "created": "1"}}, "gone": {}}
    prints = [pr(["a@1,1"], serial="DMG-APSJ-USA", release="DMG-APSJ")]
    reg, changes = print_ids.assign(prints, old, same(["a@1,1"]), T)
    assert prints[0]["id"] == "DMG-APSJ-USA-lisa"
    assert reg["gone"]["DMG-APSJ-JPN-lisa"] == {"why": "renamed", "into": "DMG-APSJ-USA-lisa", "datetime": T}
    assert reg["prints"]["DMG-APSJ-USA-lisa"]["renamed_from"] == "DMG-APSJ-JPN-lisa"
    prints = [pr(["a@1,1"], serial=None, release="DMG-APSJ")]
    print_ids.assign(prints, reg, same(["a@1,1"]), T)
    assert prints[0]["id"] == "DMG-APSJ-USA-lisa"


def test_no_serial_takes_the_release_then_unknown_and_is_renamed_once_read():
    prints = [pr(["a@1,1"], serial=None, release="DMG-APSJ"), pr(["b@1,1"], serial=None, release=None)]
    reg, _ = print_ids.assign(prints, {"prints": {}, "gone": {}}, {}, T)
    assert print_ids.split_id(prints[0]["id"])[0] == "DMG-APSJ"
    assert print_ids.split_id(prints[1]["id"])[0] == "UNKNOWN"
    name = print_ids.split_id(prints[1]["id"])[1]
    later = [pr(["a@1,1"], serial=None, release="DMG-APSJ"), pr(["b@1,1"], serial="AGB-BECJ-JPN", release="AGB-BECJ")]
    print_ids.assign(later, reg, same(["a@1,1", "b@1,1"]), T)
    assert later[1]["id"] == f"AGB-BECJ-JPN-{name}"


def test_two_names_once_every_name_is_used():
    used = {n: {"keys": [f"{n}@1,1"], "created": "1"} for n in print_ids.NAMES}
    old = {"prints": {f"DMG-APSJ-JPN-{n}": e for n, e in used.items()}, "gone": {}}
    prints = [pr([f"{n}@1,1"]) for n in print_ids.NAMES] + [pr(["new@1,1"])]
    print_ids.assign(prints, old, same([f"{n}@1,1" for n in print_ids.NAMES]), T)
    assert len(print_ids.split_id(prints[-1]["id"])[1].split("-")) == 2


def test_split_id():
    assert print_ids.split_id("DMG-APSJ-JPN-lisa") == ("DMG-APSJ-JPN", "lisa")
    assert print_ids.split_id("UNKNOWN-lisa-bob") == ("UNKNOWN", "lisa-bob")


def test_same_label_photo_by_key_or_by_the_old_centre_in_the_outline():
    outlines = {"s@51,50": [[400, 400], [600, 400], [600, 600], [400, 600]]}
    assert print_ids.same_label_photo("s@51,50", ["s@51,50"], outlines, {}) == "s@51,50"
    assert print_ids.same_label_photo("s@48,49", ["s@51,50"], outlines, {"s": [1000, 1000]}) == "s@51,50"
    assert print_ids.same_label_photo("s@10,10", ["s@51,50"], outlines, {"s": [1000, 1000]}) is None
