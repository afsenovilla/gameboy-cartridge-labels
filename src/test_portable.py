import json, multiprocessing, os, sys, tempfile, time, unittest, cv2, numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_catalog, build_database, fits, images, ocr_rapid, photos, rectify, serials


class Images(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.picture = np.zeros((40, 80, 3), np.uint8)
        self.picture[:, :40] = (0, 0, 255)

    def test_a_path_with_non_ascii_characters(self):
        path = os.path.join(self.folder.name, "ゲームボーイ ñ.png")
        images.write(path, self.picture)
        self.assertTrue(np.array_equal(images.read(path), self.picture))

    def test_exif_orientation_is_applied(self):
        path = os.path.join(self.folder.name, "turned.jpg")
        exif = Image.Exif()
        exif[0x0112] = 6
        Image.fromarray(self.picture[:, :, ::-1]).save(path, exif=exif, quality=95)
        self.assertEqual(images.read(path).shape[:2], (80, 40))

    def test_heic_is_read(self):  # real phone photos, turned in the file itself, were checked against their accepted fits
        path = os.path.join(self.folder.name, "photo.heic")
        Image.fromarray(self.picture[:, :, ::-1]).save(path, quality=95)
        self.assertEqual(images.read(path).shape[:2], (40, 80))

    def test_not_a_photo(self):
        path = os.path.join(self.folder.name, "note.jpg")
        with open(path, "w", encoding="utf-8") as f:
            f.write("not a photo")
        self.assertIsNone(images.read(path))
        self.assertIsNone(images.read(path + ".missing"))


class Files(unittest.TestCase):
    def test_saved_fits_have_lf_and_keep_japanese_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "fits.json")
            old, fits.FILE = fits.FILE, path
            self.addCleanup(setattr, fits, "FILE", old)
            fits.save({"DMG-A": {"sha1": "x", "fit": {"plastic": {"note": "ゲーム"}}, "rejected": []}})
            with open(path, "rb") as f:
                self.assertNotIn(b"\r", f.read())
            self.assertEqual(fits.load()["DMG-A"]["sha1"], "x")

    def test_lock_can_be_taken_and_given_back(self):
        with tempfile.TemporaryDirectory() as folder:
            for _ in range(2):
                with open(os.path.join(folder, "lock"), "w", encoding="utf-8") as lock:
                    fits.take_lock(lock)

    def test_names_stay_valid_on_windows(self):
        self.assertEqual(photos.tidy("dmg-a8-ukv (a)_2.JPG"), "DMG-A8-UKV(A)_2.jpg")
        self.assertNotRegex(photos.tidy('a<b>c:d"e|f?g*.jpg'), r'[<>:"|?*\\/]')


def hold_lock(path, seconds):
    with open(path, "w", encoding="utf-8") as lock:
        fits.take_lock(lock)
        time.sleep(seconds)


class Locks(unittest.TestCase):
    def test_a_second_process_waits(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "lock")
            other = multiprocessing.get_context("spawn").Process(target=hold_lock, args=(path, 2))
            other.start()
            time.sleep(1.5)  # it has started and holds the lock
            start = time.time()
            with open(path, "a", encoding="utf-8") as lock:
                fits.take_lock(lock)
            waited = time.time() - start
            other.join()
            self.assertGreater(waited, 0.05)


class Reading(unittest.TestCase):
    def picture(self):
        picture = np.full((200, 700, 3), 255, np.uint8)
        cv2.putText(picture, "DMG-ABCJ-JPN", (30, 120), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 4, cv2.LINE_AA)
        return picture

    def test_a_serial_is_read_with_its_corners_as_it_reads(self):
        lines = ocr_rapid.read_lines(self.picture())
        line = next(l for l in lines if "ABCJ" in l["text"])
        q = np.array(line["quad"])
        self.assertLess(q[0][0], q[1][0])  # its top left is left of its top right

    def test_text_turned_up_reads_up(self):
        lines = ocr_rapid.read_lines(cv2.rotate(self.picture(), cv2.ROTATE_90_COUNTERCLOCKWISE))
        line = next(l for l in lines if "ABCJ" in l["text"])
        q = np.array(line["quad"])
        self.assertLess(q[1][1], q[0][1])  # it runs up the picture


class Directions(unittest.TestCase):
    def test_a_box_is_read_along_its_long_side(self):
        wide = np.array([[0, 0], [100, 0], [100, 20], [0, 20]], np.float64)
        tall = np.array([[0, 0], [20, 0], [20, 100], [0, 100]], np.float64)
        self.assertEqual(len(ocr_rapid._readings(wide)), 2)
        readings = ocr_rapid._readings(tall)
        self.assertEqual(len(readings), 2)
        for quad in readings:  # its top edge, as it reads, is its long side
            self.assertEqual(np.linalg.norm(quad[1] - quad[0]), 100)

    def test_square_boxes_are_read_all_ways(self):
        self.assertEqual(len(ocr_rapid._readings(np.array([[0, 0], [20, 0], [20, 20], [0, 20]], np.float64))), 4)


class Rectify(unittest.TestCase):
    def test_a_known_pose_comes_out_straight(self):
        label = (0.0, 0.0, 10.0, 5.0)
        photo = np.zeros((300, 400, 3), np.uint8)
        photo[100:200, 100:300] = 255
        H = [[20, 0, 100], [0, 20, 100], [0, 0, 1]]
        straight = rectify.warp(photo, H, label)
        self.assertEqual(straight.shape[:2], (100, 200))
        self.assertGreater(straight[5:-5, 5:-5].min(), 245)
        self.assertEqual(rectify.native_scale(H, label), 20)


class Catalog(unittest.TestCase):
    def test_sources_and_titles(self):
        gbdb = [{"t": "Nobunaga's Ambition", "s": "DMG-NY-USA", "p": "Koei", "d": "03/01/1991", "v": ["DMG-NY-USA", "DMG-NY-USA-1"]}]
        named = [("DMG-NY-USA", "DMG-NY-USA"), ("DMG-ABJJ-JPN", "DMG-ABJJ-JPN"), ("DMG-ZZZ-JPN", None), ("UNKNOWN", None)]
        found = {r["id"]: r for r in build_catalog.build(gbdb, {"ABJJ": "A Game"}, named)}
        self.assertEqual(sorted(found), ["DMG-ABJJ", "DMG-NY", "DMG-ZZZ"])
        self.assertEqual(found["DMG-NY"]["sources"], ["gbdb", "label"])
        self.assertEqual(found["DMG-NY"]["cartridgeSerials"], ["DMG-NY-USA"])
        self.assertEqual((found["DMG-ABJJ"]["sources"], found["DMG-ABJJ"]["title_source"]), (["label"], "gb-rom-database"))
        self.assertEqual((found["DMG-ZZZ"]["sources"], found["DMG-ZZZ"]["title"]), (["name"], ""))


class Serials(unittest.TestCase):
    def test_a_code_is_not_a_region(self):
        self.assertEqual(serials.without_region("DMG-HKJ"), "DMG-HKJ")
        self.assertEqual(serials.without_region("DMG-HKJ-JPN"), "DMG-HKJ")
        self.assertEqual(serials.without_region("DMG-A8-UKV"), "DMG-A8")


class Grades(unittest.TestCase):
    GOOD = {"native_px_per_mm": 20, "sharpness": 1000, "clipped": 0, "contrast": 200}

    def test_grades(self):
        self.assertEqual(build_database.grade(self.GOOD, False)[0], "A")
        self.assertEqual(build_database.grade(dict(self.GOOD, native_px_per_mm=8), False), ("B", "few pixels"))
        self.assertEqual(build_database.grade(dict(self.GOOD, clipped=0.5), False), ("C", "blown out"))

    def test_a_watermark_is_at_most_c(self):
        self.assertEqual(build_database.grade(self.GOOD, False, True)[0], "C")

    def test_a_fake_is_never_more_than_a_placeholder(self):
        self.assertEqual(build_database.grade(self.GOOD, True)[0], "F")

    def test_the_choice_by_hand_wins(self):
        candidates = [("a", "1", "A", 20, 100), ("b", "2", "C", 5, 5)]
        self.assertEqual(build_database.choose_best(candidates, "2"), "b")
        self.assertEqual(build_database.choose_best(candidates, None), "a")
        self.assertEqual(build_database.choose_best(candidates, "gone"), "a")

    def test_game_of_a_serial(self):
        self.assertEqual(build_database.game_of("DMG-AAJJ-JPN"), build_database.game_of("DMG-AAJE-USA"))


if __name__ == "__main__":
    unittest.main()
