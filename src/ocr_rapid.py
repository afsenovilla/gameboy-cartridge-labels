import cv2, numpy as np
from rapidocr_onnxruntime import RapidOCR

import images

# Text recognition without macOS's Vision framework (RapidOCR: PP-OCR's models on ONNX Runtime, on the CPU, on every
# system, its models in the package). PP-OCR finds a line's box without knowing which way it reads, and the fitter
# needs that (the label's "GAME BOY COLOR" runs up its side, and photos come turned). So each box is read in the
# directions it could read, and kept in the one read with the most confidence, its corners as the text reads: top
# left, top right, bottom right, bottom left, as src/ocr.swift gives them.
# Photos are read at most LONGEST px on their longest side, the corners given in the photo's own pixels.
LONGEST = 2000
ELONGATED = 1.5
MIN_CONFIDENCE = 0.3
_engine = None


def _crop(photo, quad):
    width = max(2, int(max(np.linalg.norm(quad[0] - quad[1]), np.linalg.norm(quad[2] - quad[3]))))
    height = max(2, int(max(np.linalg.norm(quad[0] - quad[3]), np.linalg.norm(quad[1] - quad[2]))))
    target = np.float32([[0, 0], [width, 0], [width, height], [0, height]])
    return cv2.warpPerspective(photo, cv2.getPerspectiveTransform(np.float32(quad), target), (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def _readings(quad):
    """The box's corners for each direction its text could read: along its long side; all four if it's about square."""
    across = np.linalg.norm(quad[1] - quad[0]) + np.linalg.norm(quad[2] - quad[3])
    down = np.linalg.norm(quad[3] - quad[0]) + np.linalg.norm(quad[2] - quad[1])
    if across >= ELONGATED * down:
        turns = (0, 2)
    elif down >= ELONGATED * across:
        turns = (1, 3)
    else:
        turns = (0, 1, 2, 3)
    return [np.roll(quad, -t, axis=0) for t in turns]


def read_lines(photo):
    """Every line of text in a photo (a BGR array), as [{"text", "confidence", "quad"}]."""
    global _engine
    if _engine is None:
        _engine = RapidOCR()
    scale = min(1.0, LONGEST / max(photo.shape[:2]))
    small = cv2.resize(photo, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else photo
    boxes, _ = _engine.text_detector(small)
    if boxes is None or not len(boxes):
        return []
    readings = [(b, q) for b, box in enumerate(boxes) for q in _readings(np.asarray(box, np.float64))]
    results, _ = _engine.text_recognizer([_crop(small, q) for _, q in readings])
    best = {}
    for (b, quad), (text, confidence) in zip(readings, results):
        if text.strip() and (b not in best or float(confidence) > best[b][0]):
            best[b] = (float(confidence), text, quad)
    return [{"text": t, "confidence": c, "quad": (q / scale).tolist()} for c, t, q in (best[b] for b in sorted(best)) if c >= MIN_CONFIDENCE]


def read_file(path):
    """The lines of the photo at path; None if it can't be read."""
    photo = images.read(path)
    return None if photo is None else read_lines(photo)
