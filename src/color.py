import os, cv2, numpy as np

import photos

# The photos' colors, evened out as they're read (fit_cartridge.load), for the sources that photograph every cartridge
# alike: my own photos and jnlgame's, on a plain white background, have it made white (that sets their exposure and
# white balance alike, as my hand correction of IMG_7324 did); Hit-Japan's (eBay), washed out, get the contrast of my
# hand corrections of nine of them. Other sources' photos are left as they are: elrocinante's background isn't white,
# and one setting for all its photos made them no nearer mine of the same releases. Judged by eye on the labels of all
# these sources' photos (2026-10-30).

# Where the background's white is measured: the frame's outer share on my photos (the cartridge photographed fills the
# middle, neighbouring ones the edges), the whole frame on jnlgame's. Against the band 2-6 mm around the fitted
# cartridge, the white measured so was within 3 % in brightness and 1.3 % in color on half my 187 photos, 10 % and
# 2.6 % on nine in ten; jnlgame's within 4.5 % and 2.1 % on half.
BORDERS = {"my-collection": 0.12, "jnlgame": None}
# What goes above white is rolled off rather than clipped: a pixel's brightest channel, in linear light, compressed
# above KNEE so that TOP times the white comes out white, its channels scaled alike (its hue kept).
KNEE, TOP = 0.8, 1.6
# My hand corrections of nine Hit-Japan photos (2026-10-30), averaged: one tone curve, the same on the three channels,
# sRGB in (the middle of 32 equal steps) to out, 0-255. It darkens the shadows (a black point near 30) and lifts the
# highlights a little; it brought them within ΔE 3.7 of my corrections (median, each left out of the average in turn).
HITJAPAN_CURVE = [7, 7, 8, 8, 10, 15, 22, 30, 39, 49, 60, 70, 81, 92, 102, 113, 124, 134, 145, 155, 165, 176, 187, 197, 208, 219, 229, 239, 246,
                  250, 252, 252]
HITJAPAN = np.interp(np.arange(256), (np.arange(32) + 0.5) * 8, HITJAPAN_CURVE).round().astype(np.uint8)

_v = np.arange(256) / 255
LINEAR = np.where(_v <= 0.04045, _v / 12.92, ((_v + 0.055) / 1.055) ** 2.4).astype(np.float32)
_v = np.arange(4096) / 4095
SRGB = (255 * np.where(_v <= 0.0031308, 12.92 * _v, 1.055 * _v ** (1 / 2.4) - 0.055)).round().astype(np.uint8)
LUMINANCE = np.array([0.0722, 0.7152, 0.2126], np.float32)  # B, G, R


def source_of(path):
    """The source of a photo in photos/, from its path; None for one elsewhere."""
    rel = os.path.relpath(path, photos.ROOT)
    return None if rel.startswith("..") else rel.split(os.sep)[0]


def white(photo, border=None):
    """The background's white, linear (B, G, R): the median of the brighter half of the photo's pixels (shrunk to
    400 px), of those in the frame's outer border share only if given."""
    scale = 400 / max(photo.shape[:2])
    small = cv2.resize(photo, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    if border is not None:
        h, w = small.shape[:2]
        yy, xx = np.mgrid[0:h, 0:w]
        small = small[(xx < w * border) | (xx >= w * (1 - border)) | (yy < h * border) | (yy >= h * (1 - border))]
    pixels = LINEAR[small.reshape(-1, 3)]
    y = pixels @ LUMINANCE
    return np.median(pixels[y >= np.median(y)], 0)


def made_white(photo, white, rows=512):
    """The photo with its white made white, what goes above it rolled off; a few rows at a time (a photo is large)."""
    out = np.empty_like(photo)
    T = (TOP - KNEE) / (1 - KNEE)
    for r in range(0, photo.shape[0], rows):
        x = LINEAR[photo[r:r + rows]] / white
        m = np.maximum(x.max(2, keepdims=True), 1e-6)
        t = np.maximum(m - KNEE, 0) / (1 - KNEE)
        rolled = np.where(m > KNEE, KNEE + (1 - KNEE) * t * (1 + t / T ** 2) / (1 + t), m)
        out[r:r + rows] = SRGB[np.clip(x * (np.minimum(rolled, 1) / m) * 4095 + 0.5, 0, 4095).astype(np.int32)]
    return out


def corrected(photo, path):
    """The photo (as read from path) with its colors evened out, if its source is one of those above."""
    source = source_of(path)
    if source in BORDERS:
        return made_white(photo, white(photo, BORDERS[source]))
    if source == "ebay-hitjapan":
        return cv2.LUT(photo, HITJAPAN)
    return photo
