# serve_catalogue: the local catalogue page (screenscraper_site's) served from this computer, so reports are saved to a
# file instead of only in the browser. Run it from the repository folder:
#   python run.py py src/serve_catalogue.py [--port 8000]        then open http://localhost:8000/ (it opens by itself)
# Reports ("Report a problem" on a label) go to screenscraper-labels/reports.json, every change saved at once.
# "Leave these out" writes the reported images into screenscraper-labels/ignore.txt (one line each, what's wrong as a
# comment), clears them from the reports, removes them (screenscraper_download.py --dedupe) and builds the page again
# (screenscraper_site.py), which then reloads without them. Don't use it while a download is running.
# On the Missing list, "Add label" takes a label image you found (PNG, JPEG, WebP or AVIF) and its serial: it's saved in
# screenscraper-labels/added/ and listed in added.json, and the page is built again with it among the labels.
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


def add(serial, release, title, system, data, content_type, out=OUT):
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
    entry = {"id": os.path.splitext(os.path.basename(name))[0], "serial": serial, "release": release or serial.rsplit("-", 1)[0],
             "title": title or serial, "system": system or serial[:3].lower(), "file": name, "source": "added by you"}
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
        r = subprocess.run([sys.executable, os.path.join(here, script)] + extra, capture_output=True, text=True)
        sys.stderr.write("  " + (r.stdout + r.stderr).strip().replace("\n", "\n  ") + "\n")
        if r.returncode:
            return False
    return True


class Handler(http.server.SimpleHTTPRequestHandler):
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
        elif self.path == "/api/reports":
            with LOCK:
                self._json(200, load())
        else:
            super().do_GET()

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
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
            if self.path == "/api/apply":
                reports = load()
                added = apply(reports)
                save({})
                done = rebuild()
                return self._json(200, {"added": added, "rebuilt": done})
        self._json(404, {"error": "no such thing"})

    def log_message(self, fmt, *args):  # only the saves and the errors, not every image
        first = str(args[0]) if args else ""
        if "/api/" in first or (fmt.startswith("code") and "favicon" not in self.path):
            sys.stderr.write("  " + fmt % args + "\n")


def main(args):
    port = int(args[args.index("--port") + 1]) if "--port" in args else 8000
    if not os.path.exists(os.path.join(OUT, "index.html")):
        sys.exit("No screenscraper-labels/index.html: run src/screenscraper_site.py first.")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://localhost:{port}/"
    print("Serving the catalogue at", url, "- reports go to", REPORTS, "(Ctrl+C to stop)")
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    main(sys.argv[1:])
