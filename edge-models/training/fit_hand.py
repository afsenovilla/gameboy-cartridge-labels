# Label fitting on the labels placed by hand and held out from training (extract.py's HAND_TEST, data/cgb.npz "hand" 2):
# src/edge_fit.refine started at the hand fit and 1, 2, 4 mm off it (shift, turn up to the same in degrees, scale), with the old
# and the new ONNX model; the largest corner error from the hand fit. Run 2026-11-14 (results in label-detection.md).
# Usage, from the project root: python edge-models/training/fit_hand.py <old>.onnx <new>.onnx (training's requirements).
import json, os, sys, numpy as np, cv2, onnxruntime
DET = "/Users/vicwid/code/geon/gameboy-labels-detection"
sys.path.insert(0, os.path.join(DET, "src"))
import edge_fit, photos

z = np.load(os.path.join(DET, "edge-models/training/data/cgb.npz"))
keys = [n[0][5:] for n, h in zip(z["names"], z["hand"]) if h == 2]
hand = json.load(open(os.path.join(DET, "hand-fit-labels.json")))
rect = edge_fit.SHAPES["cgb"]["label"]
x1, y1, x2, y2 = rect
src = np.float32([[x1, y1], [x2, y1], [x2, y2], [x1, y2]])
c = np.array([(x1 + x2) / 2, (y1 + y2) / 2])
files = {os.path.splitext(f)[0]: os.path.join(DET, "photos", f) for f in os.listdir(os.path.join(DET, "photos"))}


def offset(level, rng):
    a = rng.uniform(0, 2 * np.pi)
    t = level * np.array([np.cos(a), np.sin(a)])
    th = np.radians(rng.uniform(-1, 1) * level)
    s = 1 + rng.uniform(-1, 1) * min(0.05, level * 0.015)
    R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]]) * s
    M = np.eye(3); M[:2, :2] = R; M[:2, 2] = c + t - R @ c
    return M


sessions = {name: onnxruntime.InferenceSession(p, providers=["CPUExecutionProvider"]) for name, p in (("old", sys.argv[1]), ("new", sys.argv[2]))}
rng = np.random.default_rng(3)
rows = []
for key in keys:
    photo = photos.load(files[key.split("@")[0]])
    Ht = cv2.getPerspectiveTransform(src, np.float32(hand[key]["corners"])).astype(np.float64)
    for level in (0, 1, 2, 4):
        for _ in range(1 if level == 0 else 4):
            H0 = Ht @ offset(level, rng) if level else Ht
            row = {"key": key, "level": level}
            for name, sess in sessions.items():
                edge_fit._sessions[("cgb", "label")] = sess
                H, conf = edge_fit.refine(photo, H0, "cgb", "label")
                row[name] = edge_fit.corner_error(H, Ht, rect)
                row[name + "_conf"] = conf
            rows.append(row)
    print(key, " ".join(f"{r['old']:.2f}/{r['new']:.2f}" for r in rows if r["key"] == key), flush=True)
json.dump(rows, open(os.path.join(DET, "edge-models/training/fit-hand.json"), "w"))
print("\nlargest corner error (mm) from the hand fit, old / new model")
for level in (0, 1, 2, 4):
    rs = [r for r in rows if r["level"] == level]
    for name in ("old", "new"):
        e = np.array([r[name] for r in rs]); cf = np.array([r[name + "_conf"] for r in rs])
        print(f"start {level} mm off, {name}: median {np.median(e):.2f}, under 0.5 mm {np.mean(e < 0.5):.0%}, over 1 mm {np.mean(e > 1):.0%}, "
              f"confident (>=0.8) {np.mean(cf >= 0.8):.0%}, confident and over 1 mm {np.mean((cf >= 0.8) & (e > 1)):.0%}  (n={len(rs)})")
