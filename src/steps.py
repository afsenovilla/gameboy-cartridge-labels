# What the steps share: which outputs are stale (missing, or older than the step's code), writing a file through a
# temporary one (a file is never left half written), removing outputs of photos no longer there, and running a step's
# work per photo in parallel.
import json, os
from multiprocessing import Pool
import numpy as np


def stale(out, code):
    """Whether out must be made (again): missing, or older than the step's code."""
    return not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(code)


def write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def write_npz(path, **arrays):
    tmp = path + ".tmp.npz"
    np.savez(tmp, **arrays)
    os.replace(tmp, path)


def remove_orphans(out_dir, chosen, ext):
    """Deletes out_dir's <sha1><ext> files of photos not in chosen."""
    for f in os.listdir(out_dir):
        if f.endswith(ext) and f[:-len(ext)] not in chosen:
            os.remove(os.path.join(out_dir, f))


def run(work, jobs, workers, initializer=None, initargs=(), what="done"):
    """work(job) for every job, in workers processes, with progress."""
    if not jobs:
        return
    with Pool(workers, initializer=initializer, initargs=initargs) as pool:
        for done, _ in enumerate(pool.imap_unordered(work, jobs), 1):
            if done % 50 == 0 or done == len(jobs):
                print(f"{what} {done} of {len(jobs)}", flush=True)


def legend(items, title=None):
    """A page's legend: one entry per line, each with its colour in a dot in front ([(colour, text)])."""
    import html
    rows = "".join(f'<li style="list-style:none;margin:2px 0"><span style="display:inline-block;width:0.8em;height:0.8em;'
                   f'border-radius:50%;background:{c};margin-right:0.5em;vertical-align:-0.05em"></span>{html.escape(t)}</li>'
                   for c, t in items)
    head = f"<div>{html.escape(title)}</div>" if title else ""
    return f'<div class="legend" style="margin:8px 0">{head}<ul style="margin:0;padding:0">{rows}</ul></div>'
