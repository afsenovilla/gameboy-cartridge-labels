import concurrent.futures, glob, json, os, subprocess, sys, tempfile, cv2, numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import color, fits, photos
from cartridge import BODY, DISTANCE_TOLERANCE, SPECIAL_SHELLS, Fitter, camera_distance, color_lines, color_start, corners_of, emboss_lines, emboss_start, project, shell_of, special_shell, text_starts

# fit-cartridge: fits the model of the cartridge's shell (src/cartridge.py: the Game Boy's, or the Game Boy Color
# only cartridge's for CGB- serials) to every photo in photos/ but Game Boy Advance ones (no model) and those of
# cartridges with another shell (special-shells.tsv: rumble, tilt sensor...), started from its text in
# generated/read-text/ (make read-text). The fit, the plastic's pose as a homography from mm on the cartridge's front to
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
    line implies (cartridge.emboss_start), with a margin of 12 % of its size for the line's error in scale and place. Of
    the lines like it, the one with the best score less its distance from the photo's center (in shares of the photo's
    size): photos of my collection show the neighbouring cartridges at the edges. Without any, a "GAME BOY COLOR" on the
    label (cartridge.color_start), likewise nearest the center. Without the crop, the fitter (which works at about 900 px
    across) saw a cartridge filling 60 % of a phone photo at about 10 px/mm, and nearly every fit had a broken recess
    line. The CGB's shell has no such embossing: by its "GAME BOY COLOR" alone. Returns the box and the line, or None."""
    h, w = photo.shape[:2]
    candidates, start = (emboss_lines(lines, count=10), emboss_start) if shell.name == "dmg" else ([], None)
    if not candidates:
        candidates, start = color_lines(lines), lambda line: color_start(line, text=shell.color_text)
    if not candidates:
        return None
    off_center = lambda l: float(np.linalg.norm(np.array(l["quad"]).mean(axis=0) / [w, h] - 0.5))
    line = min(candidates, key=lambda l: candidates.index(l) / len(candidates) + off_center(l))
    body = project(start(line), corners_of((0, 0) + BODY))
    margin = 0.12 * (body.max(axis=0) - body.min(axis=0))
    x0, y0 = np.maximum(np.floor(body.min(axis=0) - margin).astype(int), 0)
    x1, y1 = np.minimum(np.ceil(body.max(axis=0) + margin).astype(int), [w, h])
    return (int(x0), int(y0), int(x1), int(y1)), line


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
    found = crop(photo, lines, shell)
    if found is None:
        return {"error": "no embossed text or GAME BOY COLOR found"}
    (x0, y0, x1, y1), line = found
    # Fitted in the crop; the results go back to the photo's pixels through the crop's offset.
    lines = [dict(l, quad=(np.array(l["quad"]) - [x0, y0]).tolist()) for l in lines]
    fitter = Fitter(photo[y0:y1, x0:x1], shell)
    to_photo = lambda H: (lambda P: (P / P[2, 2]).tolist())(np.array([[1, 0, x0], [0, 1, y0], [0, 0, 1]]) @ H)
    starts = text_starts(lines, shell)
    recess = shell.recess
    size = (photo.shape[1], photo.shape[0])
    # Possible: a camera 20 to 100 cm away could have seen it so (cartridge.camera_distance).
    possible = lambda H: camera_distance(to_photo(H), size)[0] <= DISTANCE_TOLERANCE
    # Of the plausible fits, the one where the recess's line is strongest; more starts only add wrong fits that score well.
    candidates = []  # every plausible fit, for judging ambiguity
    for H0 in starts:
        H, _ = fitter.fit(H0)
        if recess_plausible(H, recess):
            candidates.append({"H": H / H[2, 2], "recess_strength": fitter.recess_strength(H), "band_line": fitter.band_line(H), "possible": possible(H)})
    if not candidates:
        return {"error": "no plausible fit", "crop": [x0, y0, x1, y1]}
    # The band below the recess is plain apart from the arrow: candidates with a line there at least 0.8 as strong as the
    # recess's bottom line are left out, if any others remain (on the photos placed by hand: within 0.3 mm 37 -> 40,
    # within 1 mm 44 -> 46).
    clear = [c for c in candidates if c["band_line"] < 0.8] or candidates
    # Possible ones first; an impossible one may still come right in the refit below (it did on UNKNOWN_245), and only
    # possible ones are rivals.
    best = max([c for c in clear if c["possible"]] or clear, key=lambda c: c["recess_strength"])
    H, strength = best["H"], best["recess_strength"]
    quality = fitter.quality(H)
    # Ambiguity: the strongest rival that lands clearly elsewhere (mean recess corner distance over 0.5 mm, in the chosen
    # fit's mm frame). One at 85% of the winner's strength or more flags the fit for review: on the photos placed by
    # hand that caught 8 of the 13 fits off by 1 mm or more, and flagged 7 others.
    to_mm = np.linalg.inv(H)
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
            if recess_plausible(Hr, recess) and possible(Hr):
                s = reduced.recess_strength(Hr)
                if s > retry[0]:
                    retry = (s, Hr)
        if retry[1] is not None:
            retry_continuity = fitter.line_continuity(retry[1])
            if min(retry_continuity) > min(continuity):
                H, continuity, refit_without = retry[1], retry_continuity, SIDES[side]
                quality = fitter.quality(H)
    if not possible(H):
        return {"error": "no fit a camera 20 to 100 cm away could have seen", "crop": [x0, y0, x1, y1]}
    return {"shell": shell.name, "mm_to_photo": to_photo(H), "photo_size": list(size), "distance_mm": camera_distance(to_photo(H), size)[1],
            "crop": [x0, y0, x1, y1], "found_by": line["text"], "quality": quality, "recess_strength": strength,
            "rival_strength": rival[0], "rival_distance_mm": rival[1], "ambiguous": rival[0] >= 0.85,
            "line_continuity": continuity, "broken_line": min(continuity) < 0.4, "refit_without": refit_without,
            "candidates": [{"mm_to_photo": to_photo(c["H"]), "recess_strength": c["recess_strength"], "band_line": c["band_line"], "possible": c["possible"]} for c in candidates]}


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
    todo, no_text, kept = [], [], 0
    for stem, path in sorted(paths.items()):
        if fits.good(fits.of(known, stem, sha1s[stem])["fit"].get("plastic")):
            kept += 1
            continue
        text = os.path.join(TEXT, stem + ".json")
        out = os.path.join(OUT, stem + ".json")
        if not os.path.exists(text):
            no_text.append(stem)
        elif not os.path.exists(out) or json.load(open(out)).get("sha1") != sha1s[stem] or os.path.getmtime(out) < max(os.path.getmtime(path), os.path.getmtime(text), code):
            todo.append((stem, path, text, sha1s[stem]))
    print(f"{len(paths)} photos ({len(special)} of cartridges with another shell left out, {SPECIAL_SHELLS}), {kept} with their plastic accepted or placed by hand, kept; {len(todo)} to fit" + (f"; {len(no_text)} without their text (make read-text): {' '.join(no_text)}" if no_text else ""))
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
    results = [json.load(open(p)) for p in glob.glob(os.path.join(OUT, "*.json"))]
    print(f"{kept} kept, {current} fitted and not known to be wrong; {sum('error' in r for r in results)} couldn't be fitted, "
          f"{sum('error' not in r and not r['ambiguous'] and not r['broken_line'] for r in results)} files not flagged (ambiguous or broken recess line)")
