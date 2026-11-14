# Edge models trained on the strips from extract.py. A training example: one edge (photo, part, side), an offset d mm
# (uniform within +-MAX_OFFSET) of a hypothesized line from the true one, and K strips of that edge, each a window of
# +-W mm around the hypothesized line at R samples per mm (box-filtered from the stored 20 per mm). The answer: where
# the true edge is in the window, -d.
#   heatmap: a 1D fully convolutional net giving a logit per sample of the window ("the edge is here"); K strips
#            combined by adding their log-probabilities (the same line through all of them).
#   regress: a net giving d from one window; K strips combined by the median of their answers.
#   gradient: no learning: the strongest colour change, its magnitudes added over the K strips.
# Errors are measured on photos held out (by photo), per K.
import argparse, json, os, time, numpy as np, torch, torch.nn as nn, torch.nn.functional as F

HERE = os.path.dirname(os.path.abspath(__file__))
STORED_PER_MM, STORED_HALF = 20, 20.0
dev = torch.device("mps" if torch.backends.mps.is_available() else "cpu")


def load(shell):
    z = np.load(os.path.join(HERE, "data", shell + ".npz"))
    strips, meta = z["strips"], z["meta"]
    photo = meta[:, 0].astype(int)
    # held out by photo: a hash of the index, 80 % train, 20 % test
    rng = np.random.default_rng(0)
    perm = rng.permutation(photo.max() + 1)
    test_photo = perm[: len(perm) // 5]
    is_test = np.isin(photo, test_photo)
    if "hand" in z.files:  # labels placed by hand (extract.py): 1 always trained on, 2 always held out
        hand = z["hand"][photo]
        is_test = (is_test & (hand == 0)) | (hand == 2)
    else:
        hand = np.zeros(len(photo), int)
    key = photo * 8 + meta[:, 1].astype(int) * 4 + meta[:, 2].astype(int)  # edge instance
    return strips, meta, key, is_test, hand


class Edges:
    """The strips of one split on the device, grouped by edge instance."""

    def __init__(self, strips, meta, key, mask, parts, sides):
        sel = mask & np.isin(meta[:, 1].astype(int), parts) & np.isin(meta[:, 2].astype(int), sides)
        idx = np.nonzero(sel)[0]
        order = idx[np.argsort(key[idx], kind="stable")]
        k = key[order]
        starts = np.r_[0, np.nonzero(np.diff(k))[0] + 1]
        counts = np.diff(np.r_[starts, len(k)])
        self.x = torch.from_numpy(strips[order]).to(dev)  # (n, L, 3) uint8
        self.part = torch.from_numpy(meta[order, 1].astype(np.int64)).to(dev)
        self.side = torch.from_numpy(meta[order, 2].astype(np.int64)).to(dev)
        self.starts, self.counts = torch.from_numpy(starts).to(dev), torch.from_numpy(counts).to(dev)
        self.n_edges = len(starts)

    def sample(self, n_edges, k, gen):
        """k strip indices from each of n_edges random edges (with replacement when an edge has fewer)."""
        e = torch.randint(0, self.n_edges, (n_edges,), device=dev, generator=gen)
        r = torch.rand(n_edges, k, device=dev, generator=gen)
        # distinct where possible: a random permutation slice per edge is costly; random positions suffice at k << count
        j = (r * self.counts[e, None]).long()
        return self.starts[e, None] + j  # (n_edges, k)


def windows(x, d, W, R, scale=None):
    """Windows of strips x (n, L, 3 uint8) at +-W mm around position d (n,) mm, R samples per mm: (n, 3, 2WR+1) floats.
    scale (n,): the window's mm stretched by it (a pose's scale error)."""
    xf = x.permute(0, 2, 1).float() / 255.0  # (n, 3, L)
    f = STORED_PER_MM // R
    if f > 1:  # box filter of the sample spacing
        xf = F.avg_pool1d(F.pad(xf, (f // 2, f - 1 - f // 2), mode="replicate"), f, stride=1)
    t = torch.linspace(-W, W, int(2 * W * R) + 1, device=dev)
    pos = d[:, None] + t[None, :] * (1 if scale is None else scale[:, None])  # mm in the stored strip
    fi = (pos + STORED_HALF) * STORED_PER_MM
    i0 = fi.floor().clamp(0, xf.shape[2] - 2).long()
    w = (fi - i0).clamp(0, 1)[:, None, :]
    g0 = torch.gather(xf, 2, i0[:, None, :].expand(-1, 3, -1))
    g1 = torch.gather(xf, 2, (i0 + 1)[:, None, :].expand(-1, 3, -1))
    return g0 * (1 - w) + g1 * w


class Heatmap(nn.Module):
    def __init__(self, cond, ch=48, dilations=(1, 2, 4, 8, 16, 1), k=5):
        super().__init__()
        self.cond = cond
        layers, c_in = [], 3 + cond
        for dl in dilations:
            layers += [nn.Conv1d(c_in, ch, k, padding=dl * (k - 1) // 2, dilation=dl), nn.BatchNorm1d(ch), nn.GELU()]
            c_in = ch
        self.body = nn.Sequential(*layers)
        self.out = nn.Conv1d(ch, 1, 1)
        self.rf = 1 + sum(dl * (k - 1) for dl in dilations)

    def forward(self, w, c=None):
        if self.cond:
            w = torch.cat([w, c[:, :, None].expand(-1, -1, w.shape[2])], 1)
        return self.out(self.body(w))[:, 0]  # (n, samples) logits


class Regress(nn.Module):
    def __init__(self, cond, n, ch=32):
        super().__init__()
        self.cond = cond
        self.conv = nn.Sequential(nn.Conv1d(3 + cond, ch, 7, padding=3), nn.GELU(), nn.MaxPool1d(2),
                                  nn.Conv1d(ch, ch, 7, padding=3), nn.GELU(), nn.MaxPool1d(2),
                                  nn.Conv1d(ch, ch, 7, padding=3), nn.GELU(), nn.MaxPool1d(2))
        self.head = nn.Sequential(nn.Linear(ch * (n // 8) + cond, 256), nn.GELU(), nn.Linear(256, 1))

    def forward(self, w, c=None):
        h = self.conv(w if not self.cond else torch.cat([w, c[:, :, None].expand(-1, -1, w.shape[2])], 1)).flatten(1)
        return self.head(h if not self.cond else torch.cat([h, c], 1))[:, 0]


class Onnx:
    """An exported model (export_onnx.py), called as the PyTorch one."""

    def __init__(self, path):
        import onnxruntime
        self.session = onnxruntime.InferenceSession(path, providers=["CPUExecutionProvider"])

    def eval(self):
        return self

    def __call__(self, w, c):
        out = self.session.run(None, {"strips": w.cpu().numpy().astype(np.float32), "condition": c.cpu().numpy().astype(np.float32)})[0]
        return torch.from_numpy(out).to(w.device)


def cond_of(E, j, shell_id, n_cond):
    if not n_cond:
        return None
    # one-hot of part (2) and side (4)
    return torch.cat([F.one_hot(E.part[j], 2), F.one_hot(E.side[j], 4)], 1).float()


def batch(E, n, k, W, R, max_off, gen, jitter):
    j = E.sample(n, k, gen).reshape(-1)
    d = (torch.rand(n, device=dev, generator=gen) * 2 - 1) * max_off
    d = d[:, None].expand(n, k).reshape(-1)
    scale = 1 + (torch.rand(n, device=dev, generator=gen) * 2 - 1)[:, None].expand(n, k).reshape(-1) * jitter if jitter else None
    w = windows(E.x[j], d, W, R, scale)
    # where the true edge (0 in the strip) is in the window, in mm of the window: -d / scale
    y = -d / (1 if scale is None else scale)
    if jitter == 0 or True:  # brightness / contrast per strip
        a = 1 + (torch.rand(len(j), 1, 1, device=dev, generator=gen) - 0.5) * 0.4
        b = (torch.rand(len(j), 1, 1, device=dev, generator=gen) - 0.5) * 0.2
        w = (w * a + b)
    return w, y, j


def train(args, Etr, Ete):
    gen = torch.Generator(device=dev).manual_seed(1)
    W, R = args.W, args.R
    n = int(2 * W * R) + 1
    t = torch.linspace(-W, W, n, device=dev)
    n_cond = 6 if args.cond else 0
    model = (Heatmap(n_cond, ch=args.ch, dilations=tuple(args.dil)) if args.kind == "heatmap" else Regress(n_cond, n)).to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=2e-3, total_steps=args.steps)
    t0 = time.time()
    for step in range(args.steps):
        w, y, j = batch(Etr, args.batch, 1, W, R, args.max_off, gen, args.jitter)
        c = cond_of(Etr, j, 0, n_cond)
        if args.kind == "heatmap":
            logits = model(w, c)
            target = torch.exp(-0.5 * ((t[None, :] - y[:, None]) / args.sigma) ** 2)
            target = target / target.sum(1, keepdim=True)
            loss = -(target * F.log_softmax(logits, 1)).sum(1).mean()
        else:
            loss = F.smooth_l1_loss(model(w, c), y, beta=0.1)
        opt.zero_grad(); loss.backward(); opt.step(); sched.step()
        if step % 1000 == 0:
            print(f"  step {step} loss {loss.item():.4f} {time.time() - t0:.0f}s", flush=True)
    return model


@torch.no_grad()
def evaluate(model, args, E, ks=(1, 2, 4, 8, 16, 32), n_edges=4000, jitter=0.0):
    gen = torch.Generator(device=dev).manual_seed(2)
    W, R = args.W, args.R
    n = int(2 * W * R) + 1
    t = torch.linspace(-W, W, n, device=dev)
    n_cond = 6 if args.cond else 0
    if model is not None:
        model.eval()
    res = {}
    for k in ks:
        errs = []
        for _ in range(n_edges // 500):
            m = 500
            j = E.sample(m, k, gen).reshape(-1)
            d = ((torch.rand(m, device=dev, generator=gen) * 2 - 1) * args.max_off)[:, None].expand(m, k).reshape(-1)
            sc = (1 + (torch.rand(m, device=dev, generator=gen) * 2 - 1) * jitter)[:, None].expand(m, k).reshape(-1)
            w = windows(E.x[j], d, W, R, sc)
            y = (-d / sc).reshape(m, k)[:, 0]
            if model is None:  # strongest colour change
                g = (w[:, :, 1:] - w[:, :, :-1]).norm(dim=1)
                g = g.reshape(m, k, -1).sum(1)
                pred = (t[:-1] + t[1:])[g.argmax(1)] / 2
            elif args.kind == "heatmap":
                lp = F.log_softmax(model(w, cond_of(E, j, 0, n_cond)), 1).reshape(m, k, -1).sum(1)
                i = lp.argmax(1).clamp(1, n - 2)
                a, b, c = lp.gather(1, (i - 1)[:, None])[:, 0], lp.gather(1, i[:, None])[:, 0], lp.gather(1, (i + 1)[:, None])[:, 0]
                sub = 0.5 * (a - c) / (a - 2 * b + c).clamp(max=-1e-6)  # parabola through the peak
                pred = t[i] + sub.clamp(-0.5, 0.5) / R
            else:
                pred = model(w, cond_of(E, j, 0, n_cond)).reshape(m, k).median(1).values
            errs.append((pred - y).abs().cpu())
        e = torch.cat(errs).numpy()
        res[k] = {"median": float(np.median(e)), "p90": float(np.quantile(e, 0.9)), "le0.1": float((e <= 0.1).mean()),
                  "le0.25": float((e <= 0.25).mean()), "gt1": float((e > 1).mean())}
    return res


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--shell", default="dmg")
    p.add_argument("--kind", default="heatmap", choices=["heatmap", "regress", "gradient"])
    p.add_argument("--W", type=float, default=10.0)
    p.add_argument("--R", type=int, default=20)
    p.add_argument("--max-off", type=float, default=10.0)
    p.add_argument("--parts", type=int, nargs="+", default=[0, 1])
    p.add_argument("--sides", type=int, nargs="+", default=[0, 1, 2, 3])
    p.add_argument("--cond", type=int, default=1)
    p.add_argument("--steps", type=int, default=6000)
    p.add_argument("--batch", type=int, default=512)
    p.add_argument("--sigma", type=float, default=0.1)
    p.add_argument("--jitter", type=float, default=0.0)
    p.add_argument("--ch", type=int, default=48)
    p.add_argument("--dil", type=int, nargs="+", default=[1, 2, 4, 8, 16, 1])
    p.add_argument("--tag", default="")
    p.add_argument("--save", default="")
    p.add_argument("--onnx", default="", help="no training: evaluate this ONNX model instead")
    args = p.parse_args()
    strips, meta, key, is_test, hand = load(args.shell)
    Etr = Edges(strips, meta, key, ~is_test, args.parts, args.sides)
    Ete = Edges(strips, meta, key, is_test, args.parts, args.sides)
    print(vars(args), "train edges", Etr.n_edges, "test edges", Ete.n_edges, flush=True)
    if args.onnx:
        model = Onnx(args.onnx)
    else:
        model = None if args.kind == "gradient" else train(args, Etr, Ete)
    out = {"args": vars(args), "eval": {}}
    # per part, so recess and label are reported apart
    for part in args.parts:
        Ep = Edges(strips, meta, key, is_test, [part], args.sides)
        out["eval"][["recess", "label"][part]] = evaluate(model, args, Ep)
        out["eval"][["recess", "label"][part] + " scale+-10%"] = evaluate(model, args, Ep, ks=(1, 8), jitter=0.1)
        if part == 1 and (hand == 2).any():  # main's held-out fits and the hand-placed held out, apart
            out["eval"]["label main"] = evaluate(model, args, Edges(strips, meta, key, is_test & (hand == 0), [1], args.sides))
            out["eval"]["label hand"] = evaluate(model, args, Edges(strips, meta, key, hand == 2, [1], args.sides))
    if isinstance(model, Heatmap):
        out["receptive_field_mm"] = model.rf / args.R
    print(json.dumps(out["eval"]), flush=True)
    with open(os.path.join(HERE, "results.jsonl"), "a") as f:
        f.write(json.dumps(out) + "\n")
    if args.save:
        torch.save(model.state_dict(), os.path.join(HERE, args.save))


if __name__ == "__main__":
    main()
