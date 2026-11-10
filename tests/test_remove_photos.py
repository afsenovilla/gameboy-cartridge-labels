import json, os
import photos, remove_photos


def test_delete_removes_the_file_and_its_record(tmp_path):
    root = tmp_path / "photos"
    root.mkdir()
    (root / "aa.jpg").write_bytes(b"x")
    (root / "bb.png").write_bytes(b"y")
    sources = tmp_path / "photo-sources.json"
    sources.write_text(json.dumps({"aa": {"source": "s"}, "bb": {"source": "t"}}))
    photos.delete("aa", root=str(root), sources_file=str(sources))
    assert sorted(os.listdir(root)) == ["bb.png"]
    assert json.loads(sources.read_text()) == {"bb": {"source": "t"}}


def test_references():
    p = lambda pid, keys, fam: {"id": pid, "keys": keys, "family": fam}
    prints = [p("a", ["a", "b", "c"], "f"), p("d", ["d"], "f"), p("e", ["e", "g"], "h"), p("i", ["i"], "h"),
              p("j", ["j"], "k"), p("l", ["l", "m"], "n"), p("o", ["o", "q"], "n")]
    refs = remove_photos.references(prints)
    assert refs["a"] == refs["d"] == "a"          # the family's biggest print, its own print if 3 or more
    assert refs["e"] == refs["i"] == "e"
    assert refs["j"] is None                      # alone in its family: nothing to compare with
    assert refs["l"] == "l" and refs["o"] == "o"  # a tie: its own print
