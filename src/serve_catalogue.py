# serve_catalogue: the local catalogue page (screenscraper_site's) served from this computer, so reports are saved to a
# file instead of only in the browser. Run it from the repository folder:
#   python run.py py src/serve_catalogue.py [--port 8000]        then open http://localhost:8000/ (it opens by itself)
# Reports ("Report a problem" on a label) go to screenscraper-labels/reports.json, every change saved at once.
# "Leave these out" writes the reported images into screenscraper-labels/ignore.txt (one line each, what's wrong as a
# comment), clears them from the reports, removes them (screenscraper_download.py --dedupe) and builds the page again
# (screenscraper_site.py), which then reloads without them. Don't use it while a download is running.
# On the Missing list, "Add label" takes a label image you found (PNG, JPEG, WebP or AVIF) and its serial: it's saved in
# screenscraper-labels/added/ and listed in added.json, and the page is built again with it among the labels.
# While it runs it watches added.json, ignore.txt, matches.json and the restored labels: when one changes (a label
# added from elsewhere, say), it builds the page again and open pages reload themselves.
# Photos of labels to add go through a review: dropped in screenscraper-labels/inbox/ or uploaded at /review, each is
# straightened and its serial read (src/inbox.py), and waits there for Accept (after moving its corners if need be)
# or Reject.
# Only this computer can reach it (127.0.0.1). Stop it with Ctrl+C.
import http.server
import json
import os
import sys
import threading
import webbrowser

OUT = "screenscraper-labels"
REPORTS = os.path.join(OUT, "reports.json")
IGNORE = os.path.join(OUT, "ignore.txt")
PAGE = "/" + OUT + "/index.html"
LOCK = threading.Lock()
ADDED = os.path.join(OUT, "added.json")
TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/avif": "avif"}
MAX_BYTES = 40 * 1024 * 1024


def add(serial, release, title, system, data, content_type, out=OUT, source_width=None):
    """Save a label image someone found for a missing cartridge: added/<serial>[-n].<ext>, listed in added.json.
    Returns its entry."""
    import re
    ext = TYPES.get((content_type or "").split(";")[0].strip())
    if not ext:
        raise ValueError("not a PNG, JPEG, WebP or AVIF image")
    if not data or len(data) > MAX_BYTES:
        raise ValueError("empty, or over 40 MB")
    serial = re.sub(r"[^A-Z0-9-]", "", (serial or "").upper())[:20]
    if not re.fullmatch(r"(DMG|CGB|AGB)-[A-Z0-9]{2,5}(-[A-Z]{3})?(-\d)?", serial):
        raise ValueError("that doesn't look like a serial (like DMG-AAUE-USA)")
    added_path = os.path.join(out, "added.json")
    entries = json.load(open(added_path, encoding="utf-8")) if os.path.exists(added_path) else []
    os.makedirs(os.path.join(out, "added"), exist_ok=True)
    name, n = f"added/{serial}.{ext}", 1
    while os.path.exists(os.path.join(out, name)):
        n += 1
        name = f"added/{serial}-{n}.{ext}"
    with open(os.path.join(out, name), "wb") as f:
        f.write(data)
    entry = {"id": os.path.splitext(os.path.basename(name))[0], "serial": serial, "release": release or "-".join(serial.split("-")[:2]),
             "title": title or serial, "system": system or serial[:3].lower(), "file": name, "source": "added by you"}
    if source_width:
        entry["source_width"] = source_width
    entries.append(entry)
    with open(added_path + ".tmp", "w", encoding="utf-8", newline="\n") as f:
        json.dump(entries, f, indent=1, ensure_ascii=False)
    os.replace(added_path + ".tmp", added_path)
    return entry


def load():
    if not os.path.exists(REPORTS):
        return {}
    with open(REPORTS, encoding="utf-8") as f:
        return json.load(f)


def save(reports):
    with open(REPORTS + ".tmp", "w", encoding="utf-8", newline="\n") as f:
        json.dump(reports, f, indent=1, ensure_ascii=False)
    os.replace(REPORTS + ".tmp", REPORTS)


def line(file, r):
    what = "; ".join(r.get("reasons") or []) + (" - " + " ".join(r["note"].split()) if r.get("note") else "")
    return f"{file}  # {r.get('title', '')} ({r.get('serial', '')}): {what}"


def apply(reports, ignore=IGNORE):
    """Write the reported images into ignore.txt (those not there yet) and return how many were added."""
    have = set()
    if os.path.exists(ignore):
        with open(ignore, encoding="utf-8") as f:
            have = {l.split("#")[0].strip() for l in f}
    new = [line(file, r) for file, r in reports.items() if file not in have]
    if new:
        gap = False
        if os.path.exists(ignore) and os.path.getsize(ignore):
            with open(ignore, "rb") as f:
                gap = not f.read().endswith(b"\n")
        with open(ignore, "a", encoding="utf-8", newline="\n") as f:
            f.write(("\n" if gap else "") + "\n".join(new) + "\n")
    return len(new)


def rebuild(dedupe=True):
    """Remove what ignore.txt lists (--dedupe) and build the page again; True if both went well."""
    import subprocess
    here = os.path.dirname(os.path.abspath(__file__))
    steps = [("screenscraper_download.py", ["--dedupe"])] if dedupe else []
    for script, extra in steps + [("screenscraper_site.py", [])]:
        r = subprocess.run([sys.executable, os.path.join(here, script)] + extra, capture_output=True, text=True, encoding="utf-8", errors="replace")
        sys.stderr.write("  " + (r.stdout + r.stderr).strip().replace("\n", "\n  ") + "\n")
        if r.returncode:
            return False
    return True


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):  # never let the browser keep an old page: it's rebuilt as labels come in
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            self.send_response(302)
            self.send_header("Location", PAGE)
            self.end_headers()
        elif self.path == "/favicon.ico":  # the browser asks for one; there is none
            self.send_response(204)
            self.end_headers()
        elif self.path == "/api/version":
            self._json(200, {**VERSION, "review": REVIEW["n"]})
        elif self.path.split("?")[0] in ("/review", "/review/"):
            import review_page
            body = review_page.PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/candidates":
            import inbox
            self._json(200, [c for c in inbox.load() if c["status"] == "pending"])
        elif self.path == "/api/reports":
            with LOCK:
                self._json(200, load())
        else:
            super().do_GET()

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if self.path.startswith("/api/inbox?"):  # a photo for the review: saved in the inbox, processed at once
            import inbox, urllib.parse
            q = dict(urllib.parse.parse_qsl(self.path.split("?", 1)[1]))
            if length > MAX_BYTES:
                return self._json(400, {"error": "over 40 MB"})
            name = os.path.basename(q.get("name") or "photo.jpg")
            if not name.lower().endswith(inbox.IMAGES):
                return self._json(400, {"error": "not an image"})
            os.makedirs(inbox.INBOX, exist_ok=True)
            base, ext = os.path.splitext(name)
            path, n = os.path.join(inbox.INBOX, name), 1
            while os.path.exists(path):
                n += 1
                path = os.path.join(inbox.INBOX, f"{base}-{n}{ext}")
            with open(path, "wb") as f:
                f.write(self.rfile.read(length))
            with LOCK:
                inbox.process(lambda m: sys.stderr.write(m + "\n"))
                REVIEW["n"] += 1
            return self._json(200, {"saved": os.path.basename(path)})
        if self.path.startswith("/api/candidates/"):
            import inbox
            action = self.path.rsplit("/", 1)[1]
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
                with LOCK:
                    if action == "recrop":
                        return self._json(200, inbox.recrop(data["id"], data["quad"], data.get("typed", "")))
                    if action == "serial":
                        return self._json(200, inbox.lookup(data["id"], data.get("serial", "")))
                    if action == "reject":
                        return self._json(200, inbox.reject(data["id"]))
                    if action == "accept":
                        entry = inbox.accept(data["id"], data.get("serial"), data.get("title"), add)
                        done = rebuild(dedupe=False)
                        inbox.refresh_all()  # the others against the catalogue as it is now
                        VERSION["n"] += done
                        return self._json(200, {**entry, "rebuilt": done})
            except (KeyError, ValueError) as e:
                return self._json(400, {"error": str(e)})
            return self._json(404, {"error": "no such action"})
        if self.path.startswith("/api/add?"):
            import urllib.parse
            q = dict(urllib.parse.parse_qsl(self.path.split("?", 1)[1]))
            if length > MAX_BYTES:
                return self._json(400, {"error": "over 40 MB"})
            data = self.rfile.read(length)
            with LOCK:
                try:
                    entry = add(q.get("serial"), q.get("release"), q.get("title"), q.get("system"), data, self.headers.get("Content-Type"))
                except ValueError as e:
                    return self._json(400, {"error": str(e)})
                done = rebuild(dedupe=False)
                VERSION["n"] += done
            return self._json(200, {**entry, "rebuilt": done})
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json(400, {"error": "not JSON"})
        with LOCK:
            if self.path == "/api/reports":  # the whole set of reports, as the page has them now
                if not isinstance(data, dict):
                    return self._json(400, {"error": "expected an object"})
                save(data)
                return self._json(200, {"saved": len(data)})
            if self.path == "/api/refresh":  # the page's "Refresh" button: build it again now
                done = rebuild(dedupe=False)
                VERSION["n"] += done
                return self._json(200, {"rebuilt": done})
            if self.path == "/api/apply":
                reports = load()
                added = apply(reports)
                save({})
                done = rebuild()
                VERSION["n"] += done
                return self._json(200, {"added": added, "rebuilt": done})
        self._json(404, {"error": "no such thing"})

    def log_message(self, fmt, *args):  # only the saves and the errors, not every image
        first = str(args[0]) if args else ""
        if ("/api/" in first and "/api/version" not in first) or (fmt.startswith("code") and "favicon" not in self.path):
            sys.stderr.write("  " + fmt % args + "\n")


WATCHED = {os.path.join(OUT, "added.json"): False, os.path.join(OUT, "ignore.txt"): True,
           os.path.join(OUT, "matches.json"): False, os.path.join("published-labels", "labels.json"): False}
VERSION = {"n": 0}
REVIEW = {"n": 0}  # bumped when the inbox gets new candidates


def stamp(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def watch(every=2.0):
    """Build the page again whenever what it's made of changes (a label added to added.json, by the page or from
    elsewhere; ignore.txt edited; matches redone), and count it, so open pages reload themselves (/api/version)."""
    import time
    seen = {p: stamp(p) for p in WATCHED}
    while True:
        time.sleep(every)
        try:
            seen = check(seen)
        except Exception as e:  # never let the watcher die quietly
            sys.stderr.write(f"  watching failed ({e!r}); still watching\n")


def check(seen):
    """One look at the watched files: rebuild if one changed. Returns what was seen."""
    import time
    if True:
        try:
            import inbox
            with LOCK:
                if inbox.process(lambda m: sys.stderr.write(m + "\n")):
                    REVIEW["n"] += 1
        except Exception as e:
            sys.stderr.write(f"  inbox failed ({e!r})\n")
        now = {p: stamp(p) for p in WATCHED}
        changed = [p for p in WATCHED if now[p] != seen[p]]
        if not changed:
            return seen
        time.sleep(1.0)  # let a file being written finish
        with LOCK:
            sys.stderr.write("  changed: " + ", ".join(os.path.basename(p) for p in changed) + " - building the page again\n")
            if rebuild(dedupe=any(WATCHED[p] for p in changed)):
                VERSION["n"] += 1
                sys.stderr.write("  page built again; open pages will reload\n")
            return {p: stamp(p) for p in WATCHED}


def main(args):
    port = int(args[args.index("--port") + 1]) if "--port" in args else 8000
    if not os.path.exists(os.path.join(OUT, "index.html")):
        sys.exit("No screenscraper-labels/index.html: run src/screenscraper_site.py first.")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://localhost:{port}/"
    print("Serving the catalogue at", url, "- reports go to", REPORTS, "(Ctrl+C to stop)")
    print("Label photos to review: drop them in screenscraper-labels/inbox/ or upload them at", url + "review")
    os.makedirs(os.path.join(OUT, "inbox"), exist_ok=True)  # where photos to review are dropped
    threading.Thread(target=watch, daemon=True).start()
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    main(sys.argv[1:])
