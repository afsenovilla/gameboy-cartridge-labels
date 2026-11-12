import numpy as np
import remove_low_resolution as rlr


def record(photo, px_per_mm):
    # a label photo fitted at px_per_mm photo pixels per mm, no perspective
    return {"photo": photo, "shape": "dmg", "cut_to_photo": (np.diag([px_per_mm, px_per_mm, 1.0])).tolist()}


def test_a_photo_goes_only_when_every_label_photo_is_under_the_limit():
    solved = {"a@1": record("a", 6), "b@1": record("b", 6), "b@2": record("b", 14), "c@1": record("c", 12),
              "d@1": record("d", 4)}
    low = rlr.low_resolution(solved, {"a", "b", "c"})        # d no longer in photos/
    assert set(low) == {"a"} and low["a"] == [6.0]
