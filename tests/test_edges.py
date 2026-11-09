import cv2, numpy as np
import edges


def test_a_dark_rectangle_gives_its_four_sides_in_the_photos_pixels():
    img = np.full((1000, 3000, 3), 200, np.uint8)
    cv2.rectangle(img, (600, 200), (2400, 800), (40, 40, 40), -1)
    e = edges.segments(img, max_side=1000)           # seen at a third
    assert e["scale"] == 3.0
    seg = e["segments"]
    long = seg[np.hypot(seg[:, 2] - seg[:, 0], seg[:, 3] - seg[:, 1]) > 500]
    assert len(long) == 4
    ys = sorted(round(float((s[1] + s[3]) / 2)) for s in long if abs(s[1] - s[3]) < 5)
    xs = sorted(round(float((s[0] + s[2]) / 2)) for s in long if abs(s[0] - s[2]) < 5)
    assert abs(ys[0] - 200) <= 3 and abs(ys[1] - 800) <= 3
    assert abs(xs[0] - 600) <= 3 and abs(xs[1] - 2400) <= 3


def test_the_darker_side_is_on_the_right():
    img = np.full((400, 600, 3), 200, np.uint8)
    img[200:] = 40                                    # dark below a level edge at y = 200
    e = edges.segments(img)
    s = e["segments"][np.argmax(np.abs(e["segments"][:, 2] - e["segments"][:, 0]))]
    direction = np.array([s[2] - s[0], s[3] - s[1]])
    right = np.array([-direction[1], direction[0]])   # with y down, (-dy, dx) is to the right
    assert right[1] > 0                               # pointing down, into the dark


def test_short_segments_left_out_and_types():
    img = np.full((400, 600, 3), 200, np.uint8)
    cv2.line(img, (100, 100), (105, 100), (0, 0, 0), 1)
    e = edges.segments(img)
    assert len(e["segments"]) == 0 and e["segments"].shape == (0, 4)
