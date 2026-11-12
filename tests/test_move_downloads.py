import json
import move_downloads


def test_moves_listed_photos_with_their_entries_and_leaves_a_photo_still_downloading(tmp_path):
    src, dst = tmp_path / "downloaded" / "ebay-search", tmp_path / "target" / "ebay-search"
    src.mkdir(parents=True)
    dst.mkdir(parents=True)
    (src / "a.jpg").write_bytes(b"a")
    (src / "b.jpg").write_bytes(b"b")                       # no listing entry yet: still downloading
    (src / "listing.json").write_text(json.dumps({"a.jpg": {"page_url": "u"}}))
    (dst / "listing.json").write_text(json.dumps({"old.jpg": {"page_url": "o"}}))
    moved = move_downloads.move(str(tmp_path / "downloaded"), str(tmp_path / "target"))
    assert moved == {"ebay-search": 1}
    assert (dst / "a.jpg").exists() and (src / "b.jpg").exists() and not (src / "a.jpg").exists()
    assert json.loads((dst / "listing.json").read_text()) == {"old.jpg": {"page_url": "o"}, "a.jpg": {"page_url": "u"}}
    assert json.loads((src / "listing.json").read_text()) == {}
