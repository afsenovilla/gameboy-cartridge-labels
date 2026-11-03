import hashlib, html, json, os, re, sqlite3, subprocess, sys, cv2, numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fits, images, photos, rectify, serials

# database: generated/database/labels.sqlite, made afresh from what's committed (photos/, fits.json, preferred.json) and
# the labels (make rectify). Nothing is copied by hand into it, so a wrong row is fixed at its source. Tables:
# - releases: each release known (from gb-game-list, or, without it, the photos' names: meta says which);
# - photos: every photo in photos/, its source and the state of its fit;
# - labels: every straightened label, its measures and grade;
# - issues: what should be checked, one row per thing, most serious first;
# - the view best_labels: each release's label to use.
# Grades (src/build_database.grade):
#   A  a real photo, sharp, well exposed and with plenty of pixels: good enough to publish as it is;
#   B  a real photo, usable, with one measure below A's;
#   C  a real photo of poor quality, or watermarked: only until a better one turns up;
#   F  a fake (photos.FAKES: box art pasted on a rendered cartridge): a placeholder, whatever its measures.
OUT = "generated/database"
SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE releases (id TEXT PRIMARY KEY, title TEXT NOT NULL, system TEXT NOT NULL, serials TEXT NOT NULL, in_catalog INTEGER NOT NULL CHECK (in_catalog IN (0, 1)));
CREATE TABLE photos (
 stem TEXT PRIMARY KEY, path TEXT NOT NULL UNIQUE, sha1 TEXT NOT NULL, source TEXT NOT NULL, system TEXT NOT NULL, serial TEXT NOT NULL,
 release_id TEXT REFERENCES releases(id), is_fake INTEGER NOT NULL CHECK (is_fake IN (0, 1)), image_url TEXT, page_url TEXT, serial_on_label TEXT,
 plastic_state TEXT, label_state TEXT, preferred INTEGER NOT NULL CHECK (preferred IN (0, 1)));
CREATE TABLE labels (
 stem TEXT PRIMARY KEY REFERENCES photos(stem), path TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
 native_px_per_mm REAL NOT NULL, sharpness REAL NOT NULL, clipped REAL NOT NULL, contrast REAL NOT NULL,
 grade TEXT NOT NULL CHECK (grade IN ('A', 'B', 'C', 'F')), grade_why TEXT NOT NULL, is_best INTEGER NOT NULL CHECK (is_best IN (0, 1)));
CREATE TABLE issues (id INTEGER PRIMARY KEY, severity TEXT NOT NULL CHECK (severity IN ('error', 'warning', 'info')), kind TEXT NOT NULL, stem TEXT, release_id TEXT, detail TEXT NOT NULL);
CREATE INDEX photos_release ON photos(release_id);
CREATE INDEX issues_kind ON issues(kind);
CREATE VIEW best_labels AS SELECT p.release_id, l.* FROM labels l JOIN photos p USING (stem) WHERE l.is_best = 1;
"""
# Sources whose photos carry a watermark across the label: never more than C, however sharp.
WATERMARKED = ("otakaraou",)
# What A asks, then C's floor. Set from this data's distribution and by looking at labels at each level (see README).
A_PX_PER_MM, C_PX_PER_MM = 12.0, 6.0
A_SHARPNESS, C_SHARPNESS = 400.0, 100.0  # about the 4th percentile of real photos, and below any seen; it depends on the art too
A_CLIPPED, C_CLIPPED = 0.03, 0.20
A_CONTRAST, C_CONTRAST = 120.0, 60.0
GRADE_ORDER = {"A": 0, "B": 1, "C": 2, "F": 3}
# Comparing labels by their look: thumbnails' correlation.
THUMB = (40, 35)
LOOKALIKE, UNLIKE = 0.95, 0.35


def grade(measures, is_fake, watermarked=False):
    """A label's grade, and why it isn't better."""
    if is_fake:
        return "F", "not a photo: box art on a rendered cartridge"
    if watermarked:
        return "C", "watermark across the label"
    checks = [("few pixels", measures["native_px_per_mm"], A_PX_PER_MM, C_PX_PER_MM, False), ("soft", measures["sharpness"], A_SHARPNESS, C_SHARPNESS, False),
              ("blown out", measures["clipped"], A_CLIPPED, C_CLIPPED, True), ("low contrast", measures["contrast"], A_CONTRAST, C_CONTRAST, False)]
    below_a = [n for n, v, a, _, more_is_worse in checks if (v > a if more_is_worse else v < a)]
    below_c = [n for n, v, _, c, more_is_worse in checks if (v > c if more_is_worse else v < c)]
    if below_c:
        return "C", ", ".join(below_c)
    return ("B", ", ".join(below_a)) if below_a else ("A", "")


def state(part):
    if part is None:
        return None
    if part["source"] == "hand-placed":
        return "hand-placed"
    return {True: "accepted", "almost": "almost"}.get(part.get("accepted"), "unreviewed")


def posix(path):
    return path.replace(os.sep, "/")


def commit():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def release_key(serial, release_of):
    """The release a serial is filed under, as find-doubles keys it; (key, in the catalog)."""
    match = next((s for s in (serial, re.sub(r"-[A-Z]{3}$", "", serial)) if s in release_of), None)
    return (release_of[match]["id"], True) if match else (serial, False)


def choose_best(candidates, preferred_sha1):
    """The stem of a release's label to use, of its [(stem, sha1, grade, native, sharpness)]: the photo chosen by hand if it
    has a label; else the best grade, the most pixels, the sharpest (the name last, so that it's always the same one)."""
    chosen = [c for c in candidates if c[1] == preferred_sha1]
    if chosen:
        return chosen[0][0]
    return min(candidates, key=lambda c: (GRADE_ORDER[c[2]], -c[3], -c[4], c[0]))[0] if candidates else None


def thumb(path):
    image = images.read(path)
    small = cv2.resize(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), THUMB, interpolation=cv2.INTER_AREA).astype(np.float32).ravel()
    small -= small.mean()
    return small / (np.linalg.norm(small) + 1e-6)


def game_of(serial):
    """A serial's game: its system and code without the region letter (DMG-AAJJ-JPN -> DMG-AAJ)."""
    m = re.match(r"(DMG|CGB|AGB)-([A-Z0-9]{3,4})", serial)
    return f"{m.group(1)}-{m.group(2)[:3]}" if m else serial


def look_issues(thumbs, serial_of):
    """Labels that look alike under different games (one of them likely misnamed: about 2 % of names are read wrong), and
    a label unlike all others of its serial (a misnamed photo, or a real variant)."""
    stems = sorted(thumbs)
    if not stems:
        return []
    M = np.stack([thumbs[s] for s in stems])
    found = []
    for i, a in enumerate(stems):
        near = M[i + 1:] @ M[i]
        for j in np.nonzero(near >= LOOKALIKE)[0]:
            b = stems[i + 1 + int(j)]
            if game_of(serial_of[a]) != game_of(serial_of[b]):
                found.append(("warning", "looks_like_other_serial", a, f"looks like {b} ({near[j]:.2f}), a different serial"))
    groups = {}
    for k, s in enumerate(stems):
        groups.setdefault(serial_of[s], []).append(k)
    for serial, members in groups.items():
        if len(members) >= 3:
            c = M[members] @ M[members].T
            for k, m in enumerate(members):
                others = np.median(np.delete(c[k], k))
                if others < UNLIKE:
                    found.append(("warning", "unlike_its_serial", stems[m], f"unlike the {len(members) - 1} others of {serial} ({others:.2f})"))
    return found


def build():
    release_of = serials.releases_by_serial()
    catalog = os.path.exists(serials.RELEASES)
    known, preferred = fits.load(), {}
    if os.path.exists("preferred.json"):
        preferred = json.load(open("preferred.json", encoding="utf-8"))
    os.makedirs(OUT, exist_ok=True)
    temporary = os.path.join(OUT, "labels.sqlite.tmp")
    if os.path.exists(temporary):
        os.remove(temporary)
    db = sqlite3.connect(temporary)
    db.executescript(SCHEMA)
    db.execute("PRAGMA foreign_keys = ON")
    db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    issues = []
    issue = lambda severity, kind, stem, release, detail: issues.append((severity, kind, stem, release, detail))

    releases = {}
    if catalog:
        for r in {r["id"]: r for r in release_of.values()}.values():
            releases[r["id"]] = (r["id"], r.get("title", ""), r["id"].split("-")[0], json.dumps(r.get("cartridgeSerials", [])), 1)

    rows, label_rows, by_release, thumbs, serial_of, by_sha = [], [], {}, {}, {}, {}
    for source, system, name, entry in photos.all_sources():
        stem, serial = photos.stem(name), photos.serial_of(name)
        path = os.path.join(photos.ROOT, source, system, name)
        key, in_catalog = release_key(serial, release_of)
        if key not in releases:
            is_serial = re.match(r"(DMG|CGB|AGB)-", serial, re.I)
            if is_serial or in_catalog:
                releases[key] = (key, "", serial.split("-")[0].upper(), json.dumps([serial]), 0)
            else:
                key = None
        is_fake = source in photos.FAKES
        fit = fits.of(known, stem, entry.get("sha1"))["fit"]
        sha1 = entry.get("sha1") or ""
        by_sha.setdefault(sha1, []).append(stem)
        is_preferred = key is not None and preferred.get(key) == sha1
        rows.append((stem, posix(path), sha1, source, system, serial, key, int(is_fake), entry.get("image_url"), entry.get("page_url"), entry.get("serial_on_label"),
                     state(fit.get("plastic")), state(fit.get("label")), int(is_preferred)))
        if not os.path.isfile(path):
            issue("error", "file_missing", stem, key, f"{path} is in sources.json but isn't there")
        else:
            with open(path, "rb") as f:
                if hashlib.sha1(f.read()).hexdigest() != sha1:
                    issue("error", "sha1_differs", stem, key, "the file isn't the one its sources.json records")
        said = entry.get("serial_on_label")
        if said and said != serial and re.sub(r"-[A-Z]{3}$", "", said) != re.sub(r"-[A-Z]{3}$", "", serial):
            issue("warning", "name_differs_from_read", stem, key, f"named {serial}, but {said} was read on its label")
        if key is None and system != "unknown":
            issue("warning", "not_a_serial", stem, None, f"{serial} isn't a serial")
        elif key is None:
            issue("info", "unnamed", stem, None, "no serial known (make name-photos)")
        elif catalog and not in_catalog:
            issue("warning", "not_in_catalog", stem, key, f"{serial} isn't in gb-game-list")
        if serial == re.sub(r"-[A-Z]{3}$", "", serial) and not said and not is_fake:
            issue("info", "named_by_release", stem, key, "named by the release searched for, not read on its label")
        if state(fit.get("label")) == "almost":
            issue("info", "label_almost", stem, key, "its label was judged almost: place it by hand (make fit-by-hand)")
        elif state(fit.get("label")) == "unreviewed":
            issue("info", "label_unreviewed", stem, key, "its label waits for a verdict (make review-labels)")
        details = os.path.join(rectify.OUT, stem + ".json")
        png = os.path.join(rectify.OUT, stem + ".png")
        if fits.good(fit.get("plastic")) and fits.good(fit.get("label")):
            m = json.load(open(details, encoding="utf-8")) if os.path.exists(details) else None
            if not m or m.get("sha1") != sha1 or m.get("mm_to_photo") != fit["label"]["mm_to_photo"] or "error" in m or not os.path.exists(png):
                issue("error", "label_stale", stem, key, "its straightened label is missing or out of date (make rectify)")
                continue
            g, why = grade(m, is_fake, source in WATERMARKED)
            with open(png, "rb") as f:
                digest = hashlib.sha256(f.read()).hexdigest()
            label_rows.append([stem, posix(png), digest, m["width"], m["height"], m["native_px_per_mm"], m["sharpness"], m["clipped"], m["contrast"], g, why, 0])
            if key:
                by_release.setdefault(key, []).append((stem, sha1, g, m["native_px_per_mm"], m["sharpness"]))
            if not is_fake:
                thumbs[stem] = thumb(png)
                serial_of[stem] = serial

    for sha1, stems in by_sha.items():
        if len({photos.serial_of(s) for s in stems}) > 1:
            issue("info", "same_file_two_serials", stems[0], None, "the same file under " + ", ".join(stems))
    best = set()
    for key, candidates in by_release.items():
        chosen = choose_best(candidates, preferred.get(key))
        best.add(chosen)
        g = next(c[2] for c in candidates if c[0] == chosen)
        better = [c for c in candidates if GRADE_ORDER[c[2]] < GRADE_ORDER[g]]
        if better and preferred.get(key) and next(c[1] for c in candidates if c[0] == chosen) == preferred[key]:
            issue("warning", "preferred_is_worse", chosen, key, f"chosen by hand, graded {g}; {better[0][0]} is graded {better[0][2]}")
        if g in ("C", "F"):
            issue("warning", "best_is_poor", chosen, key, f"the release's best label is graded {g}")
    for key, sha1 in preferred.items():
        if key in releases and not any(c[1] == sha1 for c in by_release.get(key, [])):
            issue("info", "preferred_has_no_label", None, key, f"the photo chosen by hand ({sha1[:10]}) has no good label yet")
    for severity, kind, stem, detail in look_issues(thumbs, serial_of):
        issue(severity, kind, stem, None, detail)
    if catalog:
        for key in sorted(releases):
            if releases[key][4] and key not in by_release and releases[key][2] in ("DMG", "CGB"):
                issue("warning", "release_without_label", None, key, "no good label")
    for row in label_rows:
        row[11] = int(row[0] in best)

    db.executemany("INSERT INTO releases VALUES (?, ?, ?, ?, ?)", [releases[k] for k in sorted(releases)])
    db.executemany("INSERT INTO photos VALUES (" + ", ".join("?" * 14) + ")", sorted(rows))
    db.executemany("INSERT INTO labels VALUES (" + ", ".join("?" * 12) + ")", sorted(label_rows))
    order = {"error": 0, "warning": 1, "info": 2}
    db.executemany("INSERT INTO issues (severity, kind, stem, release_id, detail) VALUES (?, ?, ?, ?, ?)",
                   sorted(issues, key=lambda i: (order[i[0]], i[1], i[2] or "", i[3] or "", i[4])))
    db.executemany("INSERT INTO meta VALUES (?, ?)", [("schema_version", str(SCHEMA_VERSION)), ("commit", commit()), ("catalog", "gb-game-list" if catalog else "photo names only: gb-game-list missing")])
    db.commit()
    db.close()
    final = os.path.join(OUT, "labels.sqlite")
    fits.replace(temporary, final)
    return final


def report(path):
    """generated/database/report.html: the numbers, each release's best labels, the issues."""
    db = sqlite3.connect(path)
    one = lambda q: db.execute(q).fetchone()[0]
    grades = dict(db.execute("SELECT grade, count(*) FROM labels WHERE is_best = 1 GROUP BY grade"))
    rows = "".join(f"<tr><td>{html.escape(s)}</td><td>{html.escape(k)}</td><td>{n}</td></tr>" for s, k, n in db.execute("SELECT severity, kind, count(*) FROM issues GROUP BY severity, kind ORDER BY CASE severity WHEN 'error' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, 3 DESC"))
    worst = "".join(f"<tr><td>{html.escape(s)}</td><td>{html.escape(k)}</td><td>{html.escape(t or r or '')}</td><td>{html.escape(d)}</td></tr>" for s, k, t, r, d in db.execute("SELECT severity, kind, stem, release_id, detail FROM issues WHERE severity != 'info' LIMIT 1000"))
    cards = "".join(f'<figure><img loading="lazy" src="../../{html.escape(p)}"><figcaption><b>{g}</b> {html.escape(r)}<br>{html.escape(w)}</figcaption></figure>'
                    for r, p, g, w in db.execute("SELECT release_id, path, grade, grade_why FROM best_labels ORDER BY release_id"))
    page = f"""<!doctype html><meta charset="utf-8"><title>Label database</title><style>body{{font:14px system-ui;margin:24px}}table{{border-collapse:collapse}}td{{border-bottom:1px solid #ddd;padding:3px 10px}}
.g{{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:10px}}figure{{margin:0}}img{{width:100%}}figcaption{{font-size:12px}}</style>
<h1>Label database</h1><p>{one("SELECT count(*) FROM releases")} releases, {one("SELECT count(*) FROM photos")} photos, {one("SELECT count(*) FROM labels")} labels. Best label per release by grade: {grades}. Catalog: {html.escape(one("SELECT value FROM meta WHERE key = 'catalog'"))}.</p>
<h2>Issues</h2><table>{rows}</table><h2>To check</h2><table>{worst}</table><h2>Best labels</h2><div class="g">{cards}</div>"""
    with open(os.path.join(OUT, "report.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    db.close()
    print(f"{path}: {grades}; report in {OUT}/report.html")


if __name__ == "__main__":
    report(build())
