import json, os
import cv2, numpy as np
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


def test_jobs_compare_a_big_print_within_itself_and_a_small_one_with_its_familys_biggest():
    p = lambda pid, keys, fam: {"id": pid, "keys": keys, "family": fam, "shape": "dmg"}
    prints = [p("a", ["a", "b", "c"], "f"), p("d", ["d"], "f"), p("e", ["e", "g"], "h"), p("i", ["i"], "h"),
              p("j", ["j"], "k")]
    jobs = {j[1][0]: j for j in remove_photos.jobs_of(prints)}
    assert jobs["a"][0] == "others"                          # 3 or more: each against the median of the others
    assert jobs["d"][0] == "print" and jobs["d"][4] == "a"   # the family's biggest print
    assert jobs["i"][4] == "e"
    assert jobs["e"][4] is None and jobs["j"][4] is None     # the biggest itself, or alone: nothing to compare with


def test_glare_on_one_label_photo_is_damage_and_not_on_the_others():
    rng = np.random.default_rng(0)
    label = cv2.GaussianBlur(rng.random((120, 160, 3)).astype(np.float32), (0, 0), 3)
    label = (label - label.min()) / (label.max() - label.min()) * 0.6 + 0.2   # art with contrast, 0.2..0.8
    valid = np.ones(label.shape[:2], bool)
    entries = [(np.clip(label + rng.normal(0, 0.01, label.shape), 0, 1).astype(np.float32), valid) for _ in range(4)]
    glare = entries[0][0].copy()
    glare[30:70, 40:100] = 1.0                               # an eighth of the label blown out
    entries[0] = (glare, valid)
    d = remove_photos.against_others(entries)
    assert d[0] > 0.05 and max(d[1:]) < 0.01                 # white over light art differs by under DAMAGE_DE
