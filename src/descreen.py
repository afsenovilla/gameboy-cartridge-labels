# Print-screen removal (the user, 2026-11-14: tried on restored prints at generated/notch/, generated/print-filter/ and
# generated/source-filter/; on the restored image rather than on each label photo before, and this simple version
# rather than per-band or local ones): the labels are printed with a halftone screen (DMG-KYJ: dots on two lines at
# about +-45 degrees, 0.147 mm apart, about 170 lpi), which the restored print shows as a fine checkerboard, strongest
# in patches where the screen lines up with the pixels.
#   1. The screen's peaks: in the lightness spectrum (Oklab L, Hann-windowed), the points over MIN_RATIO times their
#      surroundings (the median magnitude over 15 x 15 frequency bins), at periods under MAX_PERIOD px (coarser is the
#      label's own design), local maxima over 7 x 7 bins.
#   2. A global notch: each peak (and its mirror) removed from all three Oklab channels by a Gaussian of NOTCH_SIGMA
#      cycles/px, over the whole image (mirrored PAD px at its edges first, so the borders don't make streaks).
#   3. A weighted median of RADIUS px on the whole image, each Oklab channel apart: each sample weighted by
#      1 - d / (RADIUS + 1), d its distance in px (a soft round neighbourhood, not a box), what the notch leaves where
#      the screen is stronger than its average.
# Measured on five test prints (the screen's two strongest peaks, in the 5 % of the label where it's strongest): 0.016 to
# 0.069 before, 0.0016 to 0.0075 after.
import cv2, numpy as np
from scipy import ndimage

MIN_RATIO = 6.0
MAX_PERIOD = 5.0       # px (0.25 mm at 20 px/mm)
NOTCH_SIGMA = 0.004    # cycles/px
PAD = 64
RADIUS = 1.5           # px


def peaks(L):
    """The screen's peaks in lightness L: [(fx, fy, ratio)] in cycles/px, one of each mirrored pair."""
    h, w = L.shape
    F = np.fft.fftshift(np.fft.fft2((L - L.mean()) * np.outer(np.hanning(h), np.hanning(w))))
    mag = np.abs(F)
    ratio = mag / (ndimage.median_filter(mag, size=15) + 1e-9)
    fy, fx = (np.arange(h) - h // 2) / h, (np.arange(w) - w // 2) / w
    FX, FY = np.meshgrid(fx, fy)
    found = (ratio > MIN_RATIO) & (np.hypot(FX, FY) > 1 / MAX_PERIOD) & (ratio == ndimage.maximum_filter(ratio, size=7))
    ys, xs = np.nonzero(found)
    out = [(float(fx[x]), float(fy[y]), float(ratio[y, x])) for y, x in zip(ys, xs)]
    return [f for f in out if f[0] > 0 or (f[0] == 0 and f[1] > 0)]


def notched(img, found):
    """img (H x W x channels) with the peaks found removed from every channel."""
    h, w = img.shape[:2]
    big = cv2.copyMakeBorder(img, PAD, PAD, PAD, PAD, cv2.BORDER_REFLECT_101)
    H, W = big.shape[:2]
    FX, FY = np.meshgrid(np.fft.fftfreq(W), np.fft.fftfreq(H))
    keep = np.ones((H, W))
    for fx, fy, _ in found:
        for sx, sy in ((fx, fy), (-fx, -fy)):
            dx = (FX - sx + 0.5) % 1 - 0.5
            dy = (FY - sy + 0.5) % 1 - 0.5
            keep *= 1 - np.exp(-(dx ** 2 + dy ** 2) / (2 * NOTCH_SIGMA ** 2))
    out = np.dstack([np.real(np.fft.ifft2(np.fft.fft2(big[..., c]) * keep)) for c in range(big.shape[2])]).astype(np.float32)
    return out[PAD:PAD + h, PAD:PAD + w]


def weighted_median(ch, radius=RADIUS):
    """Per pixel, the weighted median of its neighbourhood (each sample weighted by 1 - d / (radius + 1), those at 0 or
    less left out), the image's edges mirrored."""
    r = int(np.ceil(radius))
    off = [(dy, dx) for dy in range(-r, r + 1) for dx in range(-r, r + 1) if 1 - np.hypot(dy, dx) / (radius + 1) > 0]
    wts = np.array([1 - np.hypot(dy, dx) / (radius + 1) for dy, dx in off], np.float32)
    h, w = ch.shape
    pad = np.pad(ch, r, mode="reflect")
    vals = np.stack([pad[r + dy:r + dy + h, r + dx:r + dx + w] for dy, dx in off], -1)
    order = np.argsort(vals, -1)
    cum = np.cumsum(wts[order], -1)
    pick = (cum < cum[..., -1:] / 2).sum(-1)
    return np.take_along_axis(np.take_along_axis(vals, order, -1), pick[..., None], -1)[..., 0]


def descreen(lab):
    """An Oklab image (H x W x 3) with its print screen removed: (the image, the peaks found)."""
    found = peaks(lab[..., 0])
    out = notched(lab, found) if found else lab
    return np.dstack([weighted_median(out[..., c]) for c in range(3)]).astype(np.float32), found
