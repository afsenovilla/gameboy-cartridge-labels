import concurrent.futures, glob, json, os, subprocess, sys, tempfile, cv2, numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import color, fits, photos
from cartridge import DISTANCE_TOLERANCE, MAX_TILT, SPECIAL_SHELLS, Fitter, camera_distance, color_lines, color_start, corners_of, emboss_lines, emboss_start, outline_quads, outline_starts, project, shell_of, special_shell, text_starts, tilt

# fit-cartridge: fits the model of the cartridge's shell (src/cartridge.py: the Game Boy's, or the Game Boy Color
# only cartridge's for CGB- serials) to every photo in photos/ but Game Boy Advance ones (no model) and those of
# cartridges with another shell (special-shells.tsv: rumble, tilt sensor...), started from its text in
# generated/read-text/ (make read-text), or, where that gives no fit, from the outlines in the photo (the label, the
# recess or the body). The fit, the plastic's pose as a homography from mm on the cartridge's front to
# the photo's pixels, goes into fits.json (src/fits.py) as the photo's current plastic, not yet reviewed; what this step
# found on the way goes into generated/fit-cartridge/<photo>.json: the shell, the fit, the camera's distance from the
# cartridge that explains it (a range, mm; fits no camera 20 to 100 cm away could have seen are left out), how far to
# trust it, and the candidates. The label, stuck on a little shifted and turned, is fitted in a later step, once the
# plastic's fit is known to be right. A photo whose plastic is accepted or placed by hand isn't fitted; one judged almost
# is, and a different fit takes its place (the almost one goes to the rejected fits, as it wasn't right); a fit equal to
# a rejected one isn't made current again. A photo is fitted again only when its file is missing, older than the photo,
# its text, or this step's code, or made from another photo under the same name (the file has the SHA-1 of the photo
# it was made from); one without its text is skipped and reported, and one renamed since read-text ran waits for it. A
# photo that can't be fitted gets {"error": why}, so it isn't tried again on every run. Files of photos no longer in
# photos/ are removed.
# Usage: fit_cartridge.py
TEXT = "generated/read-text"
OUT = "generated/fit-cartridge"
SYSTEMS = ("dmg", "cgb", "unknown")
SIDES = ("top", "right", "bottom", "left")


def load(path, even_colors=True):
    """The photo, upright (OpenCV applies the EXIF orientation, as the text recognition does); formats OpenCV can't
    read (HEIC) through a JPEG copy made by sips. Its colors evened out (src/color.py) unless even_colors is False."""
    photo = cv2.imread(path)
    if photo is None:
        with tempfile.TemporaryDirectory() as tmp:
            copy = os.path.join(tmp, "photo.jpg")
            subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "95", path, "--out", copy], check=True, capture_output=True)
            photo = cv2.imread(copy)
    return color.corrected(photo, path) if photo is not None and even_colors else photo


def crop(photo, lines, shell):
    """The box (x0, y0, x1, y1) of one cartridge in the photo, found by its embossed "Nintendo GAME BOY": the body the
    line implies (cartridge.emboss_start), with a margin (box_of). Of the lines like it, the one with the best score less
    its distance from the photo's center (in shares of the photo's size): photos of my collection show the neighbouring
    cartridges at the edges. Without any, a "GAME BOY COLOR" on the label (cartridge.color_start), likewise nearest the
    center. Without the crop, the fitter (which works at about 900 px across) saw a cartridge filling 60 % of a phone
    photo at about 10 px/mm, and nearly every fit had a broken recess line. The CGB's shell has no such embossing: by its
    "GAME BOY COLOR" alone. Returns the box and the line, or None."""
    h, w = photo.shape[:2]
    candidates, start = (emboss_lines(lines, count=10), emboss_start) if shell.name == "dmg" else ([], None)
    if not candidates:
        candidates, start = color_lines(lines), lambda line: color_start(line, text=shell.color_text)
    if not candidates:
        return None
    off_center = lambda l: float(np.linalg.norm(np.array(l["quad"]).mean(axis=0) / [w, h] - 0.5))
    line = min(candidates, key=lambda l: candidates.index(l) / len(candidates) + off_center(l))
    return box_of(start(line), shell, (w, h)), line


def box_of(H, shell, size):
    """The box (x0, y0, x1, y1) of the body H (mm -> the photo's pixels) puts in the photo, with a margin of 12 % of its
    size for the start's error in scale and place, within the photo."""
    body = project(H, corners_of((0, 0) + tuple(shell.body)))
    margin = 0.12 * (body.max(axis=0) - body.min(axis=0))
    x0, y0 = np.maximum(np.floor(body.min(axis=0) - margin).astype(int), 0)
    x1, y1 = np.minimum(np.ceil(body.max(axis=0) + margin).astype(int), list(size))
    return int(x0), int(y0), int(x1), int(y1)


def recess_plausible(H, recess):
    """The recess's proportions: photos are taken nearly head on, so its width over its height stays close to the
    model's (44:39 on the DMG). In 59 photos placed by hand it was 0.992 to 1.048 of that; every fit outside 0.98 to
    1.05 was off by over 1.4 mm."""
    q = project(H, corners_of(recess))
    width = (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3])) / 2
    height = (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1])) / 2
    return 0.97 <= width / height / ((recess[2] - recess[0]) / (recess[3] - recess[1])) <= 1.06


def fit(photo_path, text_path):
    """The fit of one photo, as written to its file."""
    cv2.setNumThreads(1)
    photo = load(photo_path)
    if photo is None:
        return {"error": "the photo can't be read"}
    lines = json.load(open(text_path))
    shell = shell_of(photos.serial_of(os.path.basename(photo_path)))
    size = (photo.shape[1], photo.shape[0])
    # Started from the text, in the box of the cartridge it shows; where that gives no fit, from the outlines in the
    # photo, each taken for the label, recess or body in the box it implies. Starts from both, chosen among together,
    # did worse: on 100 DMG photos with a good fit within 0.5 mm the text's fit 86, the outlines' alone 77, both 81, the
    # outlines' only where the text's failed 88; on 100 CGB ones 44, 32, 27, 44.
    found = crop(photo, lines, shell)
    result = None
    if found is not None:
        box, line = found
        shift = np.array([[1, 0, box[0]], [0, 1, box[1]], [0, 0, 1]], np.float64)
        in_crop = [dict(l, quad=(np.array(l["quad"]) - box[:2]).tolist()) for l in lines]
        result = fit_from(photo, shell, [(box, [shift @ H0 for H0 in text_starts(in_crop, shell)])], line["text"])
        if "error" not in result:
            return result
    starts = outline_starts(outline_quads(photo), shell, size)
    if not starts:
        return result or {"error": "no text or outline to start from"}
    by_outline = {}
    for H0, i, what in starts:
        by_outline.setdefault((i, what), []).append(H0)
    from_outline = fit_from(photo, shell, [(box_of(group[0], shell, size), group) for group in by_outline.values()], "outline")
    return from_outline if "error" not in from_outline or result is None else result


def fit_from(photo, shell, groups, found_by):
    """The fit from starts (in the photo's pixels) in groups, each fitted in its crop: [(box, starts)]. Fits from
    outlines are kept upright (cartridge.tilt), as their starts don't tell up from down."""
    size = (photo.shape[1], photo.shape[0])
    recess = shell.recess
    # Possible: a camera 20 to 100 cm away could have seen it so (cartridge.camera_distance).
    possible = lambda H: camera_distance(H, size)[0] <= DISTANCE_TOLERANCE
    # Of the plausible fits, the one where the recess's line is strongest; more starts only add wrong fits that score well.
    candidates = []  # every plausible fit, for judging ambiguity; poses in the photo's pixels
    fitters = []
    for (x0, y0, x1, y1), starts in groups:
        fitter = Fitter(photo[y0:y1, x0:x1], shell)
        shift = np.array([[1, 0, x0], [0, 1, y0], [0, 0, 1]], np.float64)
        fitters.append((fitter, shift, (x0, y0, x1, y1), [np.linalg.inv(shift) @ H0 for H0 in starts]))
        for H0 in fitters[-1][3]:
            H, _ = fitter.fit(H0)
            if recess_plausible(H, recess) and (found_by != "outline" or abs(tilt(H)) <= MAX_TILT):
                Hp = shift @ H
                Hp /= Hp[2, 2]
                candidates.append({"H": Hp, "group": len(fitters) - 1, "recess_strength": fitter.recess_strength(H), "band_line": fitter.band_line(H), "possible": possible(Hp)})
    if not candidates:
        return {"error": "no plausible fit", "found_by": found_by} | ({"crop": list(fitters[0][2])} if len(fitters) == 1 else {})
    # The band below the recess is plain apart from the arrow: candidates with a line there at least 0.8 as strong as the
    # recess's bottom line are left out, if any others remain (on the photos placed by hand: within 0.3 mm 37 -> 40,
    # within 1 mm 44 -> 46).
    clear = [c for c in candidates if c["band_line"] < 0.8] or candidates
    # Possible ones first; an impossible one may still come right in the refit below (it did on UNKNOWN_245), and only
    # possible ones are rivals.
    best = max([c for c in clear if c["possible"]] or clear, key=lambda c: c["recess_strength"])
    fitter, shift, (x0, y0, x1, y1), starts = fitters[best["group"]]
    Hp, strength = best["H"], best["recess_strength"]
    H = np.linalg.inv(shift) @ Hp
    quality = fitter.quality(H)
    # Ambiguity: the strongest rival that lands clearly elsewhere (mean recess corner distance over 0.5 mm, in the chosen
    # fit's mm frame). One at 85% of the winner's strength or more flags the fit for review: on the photos placed by
    # hand that caught 8 of the 13 fits off by 1 mm or more, and flagged 7 others.
    to_mm = np.linalg.inv(Hp)
    rivals = [(c["recess_strength"] / max(strength, 1e-9), float(np.linalg.norm(project(to_mm, project(c["H"], corners_of(recess))) - corners_of(recess), axis=1).mean()))
              for c in candidates if c["possible"]]
    rival = max((r for r in rivals if r[1] > 0.5), default=(0.0, 0.0))
    # A broken recess line: a side with under 40 % of its samples on one straight line. On the photos placed by hand
    # every fit off by more than 1 mm had one (21 to 36 %), and 3 good fits. Label art along that side (a logo's
    # letters) may have been taken for the recess: fitted again without that side's recess and label samples, from
    # every start, and kept if the recess's line is then less broken.
    continuity = fitter.line_continuity(H)
    refit_without = None
    if min(continuity) < 0.4:
        side = int(np.argmin(continuity))
        reduced = fitter.without_side(side)
        retry = (-1.0, None)
        for H0 in starts + [H]:
            Hr, _ = reduced.fit(H0)
            if recess_plausible(Hr, recess) and possible(shift @ Hr):
                s = reduced.recess_strength(Hr)
                if s > retry[0]:
                    retry = (s, Hr)
        if retry[1] is not None:
            retry_continuity = fitter.line_continuity(retry[1])
            if min(retry_continuity) > min(continuity):
                H, continuity, refit_without = retry[1], retry_continuity, SIDES[side]
                quality = fitter.quality(H)
    Hp = shift @ H
    Hp = Hp / Hp[2, 2]
    if not possible(Hp):
        return {"error": "no fit a camera 20 to 100 cm away could have seen", "crop": [x0, y0, x1, y1], "found_by": found_by}
    return {"shell": shell.name, "mm_to_photo": Hp.tolist(), "photo_size": list(size), "distance_mm": camera_distance(Hp, size)[1],
            "crop": [x0, y0, x1, y1], "found_by": found_by, "quality": quality, "recess_strength": strength,
            "rival_strength": rival[0], "rival_distance_mm": rival[1], "ambiguous": rival[0] >= 0.85,
            "line_continuity": continuity, "broken_line": min(continuity) < 0.4, "refit_without": refit_without,
            "candidates": [{"mm_to_photo": c["H"].tolist(), "recess_strength": c["recess_strength"], "band_line": c["band_line"], "possible": c["possible"]} for c in candidates]}


def fit_into(stem, photo_path, text_path, sha1):
    out = os.path.join(OUT, stem + ".json")
    try:
        result = fit(photo_path, text_path)
    except Exception as e:
        result = {"error": f"{type(e).__name__}: {e}"}
    result["sha1"] = sha1
    json.dump(result, open(out, "w"))
    return stem, result


def take(e, found):
    """Puts a photo's fit as this step found it (its file; None: not fitted) into its entry in fits.json, unless its
    plastic is known to be right. Returns whether it's current."""
    current = e["fit"].get("plastic")
    if fits.good(current):
        return False
    if found is None or "error" in found or fits.was_rejected(e, found["mm_to_photo"]):
        if current is not None and "accepted" not in current:
            e["fit"] = {}
        return False
    if current is not None and fits.same(current, found["mm_to_photo"]):
        return True
    if current is not None and current.get("accepted") == "almost":
        fits.reject_plastic(e)
    e["fit"] = {"plastic": fits.part(found["mm_to_photo"])}
    return True


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    # Photos renamed since read-text last ran are left for it, which takes their new names (photos.reconcile).
    paths = {photos.stem(n): os.path.join(photos.ROOT, s, system, n) for s, system, n, _ in photos.all_sources() if system in SYSTEMS}
    paths = {stem: path for stem, path in paths.items() if os.path.exists(path)}
    special = {stem for stem in paths if special_shell(photos.serial_of(stem))}
    paths = {stem: path for stem, path in paths.items() if stem not in special}
    for path in glob.glob(os.path.join(OUT, "*.json")):
        if photos.stem(os.path.basename(path)) not in paths:
            os.remove(path)
    code = max(os.path.getmtime(p) for p in ("src/cartridge.py", __file__))
    sha1s = photos.sha1s()
    known = fits.load()
    todo, no_text, kept = [], [], set()
    for stem, path in sorted(paths.items()):
        if fits.good(fits.of(known, stem, sha1s[stem])["fit"].get("plastic")):
            kept.add(stem)
            continue
        text = os.path.join(TEXT, stem + ".json")
        out = os.path.join(OUT, stem + ".json")
        if not os.path.exists(text):
            no_text.append(stem)
        elif not os.path.exists(out) or json.load(open(out)).get("sha1") != sha1s[stem] or os.path.getmtime(out) < max(os.path.getmtime(path), os.path.getmtime(text), code):
            todo.append((stem, path, text, sha1s[stem]))
    print(f"{len(paths)} photos ({len(special)} of cartridges with another shell left out, {SPECIAL_SHELLS}), {len(kept)} with their plastic accepted or placed by hand, kept; {len(todo)} to fit" + (f"; {len(no_text)} without their text (make read-text): {' '.join(no_text)}" if no_text else ""))
    with concurrent.futures.ProcessPoolExecutor() as pool:
        for done, (stem, result) in enumerate(pool.map(fit_into, *zip(*todo)) if todo else (), 1):
            print(f"{done} of {len(todo)}: {stem}: {result.get('error') or 'quality %.2f' % result['quality']}", flush=True)
    # Every photo's fit into fits.json, from the files (so that an interrupted run loses nothing).
    with fits.editing() as known:
        current = 0
        for stem in paths:
            out = os.path.join(OUT, stem + ".json")
            found = json.load(open(out)) if os.path.exists(out) else None
            if found is not None and found.get("sha1") != sha1s[stem]:
                found = None
            current += take(fits.entry(known, stem, sha1s[stem]), found)
    # Only the photos this step fits: the files of kept ones may be of an older version of it.
    results = [json.load(open(p)) for p in glob.glob(os.path.join(OUT, "*.json")) if photos.stem(os.path.basename(p)) not in kept]
    print(f"{len(kept)} kept, {current} fitted and not known to be wrong; {sum('error' in r for r in results)} couldn't be fitted, "
          f"{sum('error' not in r and not r['ambiguous'] and not r['broken_line'] for r in results)} files not flagged (ambiguous or broken recess line)")
