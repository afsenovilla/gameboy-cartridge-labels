# One-off, run 2026-11-10 (before these scripts came into this branch; kept as they ran): the training data for the edge
# models, from main's fits.json (a copy in this folder) and main's src/cartridge.py (its shells), the photos from
# this branch's photos/. Then train.py (queue.sh: the comparisons, table.py: their results.jsonl as a table; the six
# models: train.py --tag final --jitter 0.1 --steps 6000 --save models/<shape>-<part>.pt), fit.py (the fitting
# evaluation), export_onnx.py. Needs requirements.txt here (PyTorch), not the project's.
#
# Strips across the recess's and the label's edges of every good fit (accepted True or hand-placed; not "almost"),
# sampled in the cartridge's mm through the fit: per edge, one strip every STEP mm along it (1.5 mm clear of each end),
# each strip NORMAL_HALF mm to both sides of the edge at PER_MM samples per mm, from inside (-) to outside (+).
# Output: data/<shell>.npz with strips (n, 2*NORMAL_HALF*PER_MM+1, 3) uint8 RGB, and per strip its photo index, part
# (0 recess, 1 label), side (0 top, 1 right, 2 bottom, 3 left), position along the edge (mm).
import json, os, sys, numpy as np, cv2
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = "/Users/vicwid/code/geon/gameboy-labels"
DET = "/Users/vicwid/code/geon/gameboy-labels-detection"
sys.path.insert(0, os.path.join(MAIN, "src"))
import cartridge  # main's shells
cartridge.SPECIAL_SHELLS = os.path.join(MAIN, cartridge.SPECIAL_SHELLS)
import importlib.util
_spec = importlib.util.spec_from_file_location("det_photos", os.path.join(DET, "src", "photos.py"))
det_photos = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(det_photos)  # this branch's loader

PER_MM, NORMAL_HALF, STEP, END = 20, 20.0, 1.0, 1.5
T = np.linspace(-NORMAL_HALF, NORMAL_HALF, int(2 * NORMAL_HALF * PER_MM) + 1)


def good(part):
    return part and (part.get("source") == "hand-placed" or part.get("accepted") is True)


def edges(rect):
    x1, y1, x2, y2 = rect
    return [((x1, y1), (x2, y1), (0, -1)), ((x2, y1), (x2, y2), (1, 0)), ((x2, y2), (x1, y2), (0, 1)), ((x1, y2), (x1, y1), (-1, 0))]


def job(args):
    index, path, parts = args
    photo = det_photos.load(path)
    if photo is None:
        return None
    photo = cv2.cvtColor(photo, cv2.COLOR_BGR2RGB)
    out = []
    for part_id, rect, H in parts:
        H = np.asarray(H, np.float64)
        c = [(rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2]
        p = cartridge.project(H, [c, [c[0] + 1, c[1]], [c[0], c[1] + 1]])
        u_, v_ = p[1] - p[0], p[2] - p[0]; scale = np.sqrt(abs(u_[0] * v_[1] - u_[1] * v_[0]))  # px per mm
        img, Hs = photo, H
        if scale > PER_MM:  # no aliasing: the photo brought down to PER_MM px per mm first
            f = PER_MM / scale
            img = cv2.resize(photo, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
            Hs = np.diag([f, f, 1]) @ H
        for side, (a, b, n) in enumerate(edges(rect)):
            a, b, n = np.array(a, float), np.array(b, float), np.array(n, float)
            length = np.linalg.norm(b - a)
            u = (b - a) / length
            s = np.arange(END, length - END + 1e-9, STEP)
            pts = a + s[:, None] * u  # (k, 2)
            grid = pts[:, None, :] + T[None, :, None] * n  # (k, m, 2)
            px = cartridge.project(Hs, grid.reshape(-1, 2)).reshape(len(s), len(T), 2).astype(np.float32)
            strips = cv2.remap(img, px[..., 0], px[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
            out.append((part_id, side, s, strips, float(scale)))
    return index, out


def main():
    fits = json.load(open(os.path.join(HERE, "fits.json")))
    files = {os.path.splitext(f)[0]: os.path.join(DET, "photos", f) for f in os.listdir(os.path.join(DET, "photos"))}
    jobs = {"dmg": [], "cgb": [], "agb": []}
    names = {"dmg": [], "cgb": [], "agb": []}
    for name, e in sorted(fits.items()):
        un = cartridge.unprefixed(name)
        if un[:4].upper() not in ("DMG-", "CGB-", "AGB-") or cartridge.special_shell(name) or e["sha1"] not in files:
            continue
        shell = cartridge.shell_of(name)
        plastic, label = e["fit"].get("plastic"), e["fit"].get("label")
        parts = []
        if good(plastic):
            parts.append((0, shell.recess, plastic["mm_to_photo"]))
        if good(label):
            parts.append((1, shell.label, label["mm_to_photo"]))
        if parts:
            k = shell.name
            jobs[k].append((len(names[k]), files[e["sha1"]], parts))
            names[k].append((name, e["sha1"]))
    os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
    for k in jobs:
        print(k, len(jobs[k]), "photos", flush=True)
        strips, meta, scales = [], [], {}
        with Pool(4) as pool:
            for done, r in enumerate(pool.imap_unordered(job, jobs[k], chunksize=4)):
                if r is None:
                    continue
                i, out = r
                for part, side, s, st, scale in out:
                    strips.append(st)
                    meta.append(np.c_[np.full(len(s), i), np.full(len(s), part), np.full(len(s), side), s])
                    scales[(i, part)] = scale
                if done % 200 == 0:
                    print(" ", done, flush=True)
        np.savez(os.path.join(HERE, "data", k + ".npz"), strips=np.concatenate(strips), meta=np.concatenate(meta).astype(np.float32),
                 names=np.array(names[k]), scales=np.array([[i, p, s] for (i, p), s in scales.items()]))


if __name__ == "__main__":
    main()
