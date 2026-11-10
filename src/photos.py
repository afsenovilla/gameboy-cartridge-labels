# photos/: every photo, named by its SHA-1 (<sha1>.<ext>), never re-encoded. Which photos a run works on (all of
# photos/, or the sample in sample.txt) and where its output goes (generated/ or generated-sample/), and loading a photo
# the way every step sees it: upright (its EXIF turn applied), as BGR pixels.
import os, subprocess, tempfile
import cv2

ROOT = "photos"
SAMPLE = "sample.txt"
EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".avif", ".heic", ".heif")


def all_photos(root=ROOT):
    """SHA-1 -> path, for every photo in root."""
    return {os.path.splitext(f)[0]: os.path.join(root, f) for f in sorted(os.listdir(root))
            if f.lower().endswith(EXTENSIONS)}


def chosen(sample=False, root=ROOT, sample_file=SAMPLE):
    """SHA-1 -> path of the photos a run works on: all of them, or with sample those listed in sample_file."""
    photos = all_photos(root)
    if not sample:
        return photos
    return {s: photos[s] for s in open(sample_file).read().split() if s in photos}


def generated(sample=False):
    """The folder a run's output goes in."""
    return "generated-sample" if sample else "generated"


def load(path):
    """The photo, upright (OpenCV applies the EXIF orientation); formats OpenCV can't read (HEIC) through a JPEG copy
    made by macOS's sips. None if it can't be read."""
    photo = cv2.imread(path)
    if photo is None:
        with tempfile.TemporaryDirectory() as tmp:
            copy = os.path.join(tmp, "photo.jpg")
            done = subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "95", path, "--out", copy],
                                  capture_output=True)
            if done.returncode == 0:
                photo = cv2.imread(copy)
    return photo


def delete(sha1, root=ROOT, sources_file="photo-sources.json"):
    """Deletes a photo from photos/: its file and its record in photo-sources.json."""
    os.remove(all_photos(root)[sha1])
    import json
    if os.path.exists(sources_file):
        sources = json.load(open(sources_file))
        if sources.pop(sha1, None) is not None:
            tmp = sources_file + ".tmp"
            with open(tmp, "w") as f:
                json.dump(sources, f, indent=1, ensure_ascii=False, sort_keys=True)
                f.write("\n")
            os.replace(tmp, sources_file)
