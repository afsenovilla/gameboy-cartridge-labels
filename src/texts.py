# Texts at one place on labels of a layout (details/text-places.json: the strip texts of US and European DMG labels, the
# GAME BOY COLOR logo's text), read by OCR: seeds for find, and the label placed from a line's reading start, direction
# and length or height.
import difflib, json, os, re
import numpy as np

PLACES = os.path.join("details", "text-places.json")
SIMILAR = 0.75  # the least difflib ratio between a line's letters and a place's text


def load(path=PLACES):
    return json.load(open(path))["texts"] if os.path.exists(path) else []


def letters(text):
    return re.sub(r"[^A-Z]", "", text.upper())


def matching(line_text, places):
    """The text places (kind "text") a line reads."""
    t = letters(line_text)
    return [p for p in places if p["kind"] == "text" and len(t) >= 4 and
            difflib.SequenceMatcher(None, t, p["text"]).ratio() >= SIMILAR]


def scale(corners, place):
    """The photo's px per mm at a line: by its length where the text is always read whole, else its height."""
    c = np.float64(corners)
    if place.get("length_mm"):
        return np.hypot(*(c[1] - c[0])) / place["length_mm"]
    return (np.hypot(*(c[3] - c[0])) + np.hypot(*(c[2] - c[1]))) / 2 / place["height_mm"]


def placed_label(corners, place, label_mm):
    """The label's corners in the photo (top left, top right, bottom right, bottom left), from a line (corners in
    reading order) reading a text place: a similarity from the line's start, direction and scale."""
    c = np.float64(corners)
    k = scale(corners, place)
    theta = np.arctan2(*(c[1] - c[0])[::-1]) - np.radians(place["turn"])
    R = k * np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    t = c[0] - R @ np.float64(place["start_mm"])
    lw, lh = label_mm[place["shape"]]
    return (np.float64([[0, 0], [lw, 0], [lw, lh], [0, lh]]) @ R.T) + t
