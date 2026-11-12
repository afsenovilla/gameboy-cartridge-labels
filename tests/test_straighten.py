import cv2, numpy as np
import straighten, shapes


def test_a_label_photo_comes_out_in_ink_coordinates():
    # a photo with a white label rectangle 42.5 x 37 mm at 10 px/mm, its top left at (100, 50), on black
    photo = np.zeros((600, 700, 3), np.uint8)
    cv2.rectangle(photo, (100, 50), (100 + 425 - 1, 50 + 370 - 1), (255, 255, 255), -1)
    photo_to_ink = np.array([[0.1, 0, -10.0], [0, 0.1, -5.0], [0, 0, 1]])   # photo px -> mm on the label
    img = straighten.straightened(photo, photo_to_ink, "dmg")
    (w, h), _ = straighten.canvas("dmg")
    assert img.shape[:2] == (h, w)
    m = int(straighten.MARGIN * straighten.PX_PER_MM)
    lw, lh = (int(v * straighten.PX_PER_MM) for v in shapes.LABEL_MM["dmg"])
    assert img[m + 10: m + lh - 10, m + 10: m + lw - 10].min() > 200      # the label inside the nominal rectangle
    assert img[: m - 10].max() < 50 and img[:, : m - 10].max() < 50          # the margin outside it dark


def test_file_names_have_no_odd_characters():
    assert straighten.file_name("abc@50,25") == "abc_50_25.avif"


def test_a_fit_moved_a_tenth_of_a_mm_moves_the_image_two_pixels():
    import numpy as np
    H = np.array([[3.0, 0.1, 5], [-0.1, 3.0, 7], [0, 0, 1]])        # ink mm -> photo, roughly
    photo_to_ink = np.linalg.inv(H)
    shifted = np.array([[1, 0, 0.1], [0, 1, 0], [0, 0, 1.0]]) @ photo_to_ink
    assert straighten.moved_px(photo_to_ink, photo_to_ink, "dmg") < 1e-9
    assert abs(straighten.moved_px(photo_to_ink, shifted, "dmg") - 0.1 * straighten.PX_PER_MM) < 1e-6
