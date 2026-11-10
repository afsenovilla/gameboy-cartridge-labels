# Fitting with the edge models, on the photos held out from training (train.load's split).
# The recess: the plastic's pose (mm -> photo px) refined by a homography correction; the label: the label's pose as the
# plastic's times a similarity (shift, turn, scale), started centered on the fitted plastic. Each round: strips through
# the current pose (1 mm apart along the edges, 1.5 mm clear of the corners), each strip's most likely edge position
# (parabola at the peak) and its confidence (probability within +-0.3 mm of it), the correction minimizing the edges'
# distances to those positions (robust, soft L1 at 0.3 mm), repeated until it moves under 0.01 mm.
# Error: the largest of the 4 corners' distances (mm) from where the good fit puts them, in the good fit's mm.
import argparse, json, os, sys, time, numpy as np, cv2, torch, torch.nn.functional as F
from scipy.optimize import least_squares

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import extract, train, cartridge

W, R = 10.0, 10
dev = train.dev


def load_model(shell, part):
    m = train.Heatmap(6).to(dev)
    m.load_state_dict(torch.load(os.path.join(HERE, "models", f"{shell}-{part}.pt"), map_location=dev))
    return m.eval()


def edge_points(rect):
    pts, normals, sides = [], [], []
    for side, (a, b, n) in enumerate(extract.edges(rect)):
        a, b, n = np.array(a, float), np.array(b, float), np.array(n, float)
        length = np.linalg.norm(b - a)
        s = np.arange(extract.END, length - extract.END + 1e-9, extract.STEP)
        pts.append(a + s[:, None] * (b - a) / length); normals.append(np.repeat(n[None], len(s), 0)); sides += [side] * len(s)
    return np.concatenate(pts), np.concatenate(normals), np.array(sides)


def strips(photo, H, pts, normals):
    """Strips as extract.py stores them (+-20 mm, 20 per mm), through H."""
    c = pts.mean(0)
    p = cartridge.project(H, [c, c + [1, 0], c + [0, 1]])
    u, v = p[1] - p[0], p[2] - p[0]
    scale = np.sqrt(abs(u[0] * v[1] - u[1] * v[0]))
    img, Hs = photo, H
    if scale > extract.PER_MM:
        f = extract.PER_MM / scale
        img = cv2.resize(photo, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
        Hs = np.diag([f, f, 1]) @ H
    grid = pts[:, None, :] + extract.T[None, :, None] * normals[:, None, :]
    px = cartridge.project(Hs, grid.reshape(-1, 2)).reshape(len(pts), len(extract.T), 2).astype(np.float32)
    return cv2.remap(img, px[..., 0], px[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)


@torch.no_grad()
def peaks(model, st, part, sides, nearest=False):
    x = torch.from_numpy(st).to(dev)
    w = train.windows(x, torch.zeros(len(st), device=dev), W, R)
    c = torch.cat([F.one_hot(torch.full((len(st),), part, device=dev), 2), F.one_hot(torch.from_numpy(sides).to(dev), 4)], 1).float()
    lp = F.log_softmax(model(w, c), 1)
    n = lp.shape[1]
    t = torch.linspace(-W, W, n, device=dev)
    i = lp.argmax(1).clamp(1, n - 2)
    if nearest:  # the strong local maximum nearest the strip's middle (where the current pose puts the edge)
        p = lp.exp()
        mass = F.avg_pool1d(p[:, None], 7, 1, 3)[:, 0] * 7  # within +-0.3 mm
        is_max = (mass >= F.max_pool1d(mass[:, None], 7, 1, 3)[:, 0]) & (mass >= 0.15)
        dist = torch.where(is_max, t[None, :].abs(), torch.full_like(mass, 1e9))
        j = dist.argmin(1)
        i = torch.where(is_max.any(1), j, i).clamp(1, n - 2)
    a, b, cc = (lp.gather(1, (i + o)[:, None])[:, 0] for o in (-1, 0, 1))
    sub = (0.5 * (a - cc) / (a - 2 * b + cc).clamp(max=-1e-6)).clamp(-0.5, 0.5)
    pos = t[i] + sub / R
    near = (t[None, :] - pos[:, None]).abs() <= 0.3
    conf = (lp.exp() * near).sum(1)
    return pos.cpu().numpy(), conf.cpu().numpy()


def correction(kind, x, center):
    if kind == "homography":
        a, b, c, d, e, f, g, h = x
        return np.array([[1 + a, b, c], [d, 1 + e, f], [g / 100, h / 100, 1]])
    tx, ty, th, ls = x  # similarity about the center
    s = np.exp(ls)
    M = np.array([[s * np.cos(th), -s * np.sin(th), 0], [s * np.sin(th), s * np.cos(th), 0], [0, 0, 1]])
    T1, T2 = np.eye(3), np.eye(3)
    T1[:2, 2] = -np.asarray(center); T2[:2, 2] = np.asarray(center) + [tx, ty]
    return T2 @ M @ T1


NEAREST = False


def refine(photo, H, rect, model, part, kind, rounds=8, history=None):
    pts, normals, sides = edge_points(rect)
    center = np.array([(rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2])
    staged = kind == "homography"
    for rnd in range(rounds):
        k = "similarity" if staged and rnd < 3 else kind
        pos, conf = peaks(model, strips(photo, H, pts, normals), part, sides, nearest=NEAREST and rnd >= 2)
        q = pts + pos[:, None] * normals
        wts = np.sqrt(np.clip(conf, 0.02, 1)) * (conf >= 0.2)

        def res(x):
            C = correction(k, x, center)
            return wts * ((cartridge.project(C, pts) - q) * normals).sum(1)

        x0 = np.zeros(8 if k == "homography" else 4)
        r = least_squares(res, x0, loss="soft_l1", f_scale=0.3, x_scale="jac")
        C = correction(k, r.x, center)
        moved = np.abs(cartridge.project(C, cartridge.corners_of(rect)) - cartridge.corners_of(rect)).max()
        H = H @ C
        if history is not None:
            history.append(float(moved))
        if moved < 0.01 and not (staged and rnd < 3):
            break
    return H, float(np.median(conf))


def corner_error(H, H_true, rect):
    corners = cartridge.corners_of(rect)
    back = cartridge.project(np.linalg.inv(np.asarray(H_true)), cartridge.project(H, corners))
    return float(np.linalg.norm(back - corners, axis=1).max())


def perturb(H, rect, level, rng):
    """H times a random correction moving the rect's corners about level mm (shift, turn, scale, a little perspective)."""
    center = np.array([(rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2])
    ang = rng.uniform(0, 2 * np.pi)
    shift = rng.uniform(0.3, 0.7) * level * np.array([np.cos(ang), np.sin(ang)])
    th = np.radians(rng.uniform(-1, 1) * level * 0.4)
    ls = rng.uniform(-1, 1) * min(0.05, level * 0.01)
    C = correction("similarity", [*shift, th, ls], center)
    P = np.eye(3); P[2, :2] = rng.uniform(-1, 1, 2) * level * 2e-4
    return np.asarray(H) @ C @ P


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shell", default="dmg")
    ap.add_argument("--limit", type=int, default=150)
    ap.add_argument("--nearest", type=int, default=0)
    ap.add_argument("--levels", type=float, nargs="+", default=[2, 5, 10])
    args = ap.parse_args()
    global NEAREST
    NEAREST = bool(args.nearest)
    fits = json.load(open(os.path.join(HERE, "fits.json")))
    z = np.load(os.path.join(HERE, "data", args.shell + ".npz"))
    names, photo_idx = z["names"], z["meta"][:, 0].astype(int)
    perm = np.random.default_rng(0).permutation(photo_idx.max() + 1)
    test = sorted(perm[: len(perm) // 5])
    shell = cartridge.SHELLS[args.shell]
    models = [load_model(args.shell, 0), load_model(args.shell, 1)]
    files = {os.path.splitext(f)[0]: os.path.join(extract.DET, "photos", f) for f in os.listdir(os.path.join(extract.DET, "photos"))}
    rng = np.random.default_rng(5)
    rows = []
    t0 = time.time()
    for n_done, i in enumerate(test[: args.limit]):
        name, sha1 = names[i]
        e = fits[name]
        photo = extract.det_photos.load(files[sha1])
        if photo is None:
            continue
        photo = cv2.cvtColor(photo, cv2.COLOR_BGR2RGB)
        plastic, label = e["fit"].get("plastic"), e["fit"].get("label")
        row = {"name": name}
        if extract.good(plastic):
            Ht = np.asarray(plastic["mm_to_photo"])
            row["plastic_source"] = plastic["source"]
            # from the good fit itself: how far the models pull it away
            Hf, _ = refine(photo, Ht, shell.recess, models[0], 0, "homography")
            row["recess_from_truth"] = corner_error(Hf, Ht, shell.recess)
            for level in args.levels:
                H0 = perturb(Ht, shell.recess, level, rng)
                hist = []
                Hf, conf = refine(photo, H0, shell.recess, models[0], 0, "homography", history=hist)
                row[f"recess_start_{level:g}"] = corner_error(H0, Ht, shell.recess)
                row[f"recess_fit_{level:g}"] = corner_error(Hf, Ht, shell.recess)
                row[f"recess_conf_{level:g}"] = conf
                row[f"recess_rounds_{level:g}"] = len(hist)
            # real rough starts: the auto fits rejected for this photo
            rej = [r["plastic"]["mm_to_photo"] for r in e["rejected"] if "label" not in r]
            if rej:
                H0 = np.asarray(rej[-1])
                Hf, conf = refine(photo, H0, shell.recess, models[0], 0, "homography")
                row["recess_rejected_start"] = corner_error(H0, Ht, shell.recess)
                row["recess_rejected_fit"] = corner_error(Hf, Ht, shell.recess)
                row["recess_rejected_conf"] = conf
            if extract.good(label):
                Hl = np.asarray(label["mm_to_photo"])
                # label from the good plastic, then from the plastic fitted from a 5 mm start
                Hf, conf = refine(photo, Ht, shell.label, models[1], 1, "similarity")
                row["label_start"] = corner_error(Ht, Hl, shell.label)
                row["label_fit"] = corner_error(Hf, Hl, shell.label)
                row["label_conf"] = conf
        rows.append(row)
        if n_done % 25 == 0:
            print(n_done, f"{time.time() - t0:.0f}s", flush=True)
    json.dump(rows, open(os.path.join(HERE, f"fit-{args.shell}{'-nearest' if NEAREST else ''}.json"), "w"), indent=0)
    summarize(rows)


def summarize(rows):
    keys = sorted({k for r in rows for k in r if k.endswith(("_fit", "_from_truth", "_start")) or "_fit_" in k or "_start_" in k})
    for k in keys:
        v = np.array([r[k] for r in rows if k in r])
        print(f"{k:28s} n={len(v):4d} median {np.median(v):6.3f}  p90 {np.quantile(v, .9):7.3f}  <=0.25 {np.mean(v <= .25):5.1%}  <=0.5 {np.mean(v <= .5):5.1%}  >1 {np.mean(v > 1):5.1%}  >5 {np.mean(v > 5):5.1%}")


if __name__ == "__main__":
    main()
