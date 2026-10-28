import glob, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import serials

# match-serials: matches the serial on each photo's label, from its text in generated/read-text/ (make read-text),
# against gb-game-list's releases (src/serials.py), into generated/match-serials/serials.tsv: photo, status (exact,
# near, unknown, none), serial, release id, title, whether the title was read too ("title"), and the serial-like strings
# found. Done again only when serials.tsv is older than the photos' text (or the folder, for removed photos),
# gb-game-list's releases.json, or this step's code.
# Usage: match_serials.py
TEXT = "generated/read-text"
OUT = "generated/match-serials/serials.tsv"

inputs = [TEXT, serials.RELEASES, "src/serials.py", __file__] + glob.glob(os.path.join(TEXT, "*.json"))
if os.path.exists(OUT) and os.path.getmtime(OUT) >= max(os.path.getmtime(p) for p in inputs):
    print(f"{OUT} is up to date")
    sys.exit()
rows = serials.serials(TEXT)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w") as f:
    f.writelines("\t".join(row) + "\n" for row in rows)
counts = {k: sum(r[1] == k for r in rows) for k in ("exact", "near", "unknown", "none")}
print(f"{len(rows)} photos: " + ", ".join(f"{v} {k}" for k, v in counts.items()) + f"; title read on {sum(r[5] == 'title' for r in rows)}")
