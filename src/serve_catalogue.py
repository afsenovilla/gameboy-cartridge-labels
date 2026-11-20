# serve_catalogue: the local catalogue page (screenscraper_site's) served from this computer, so reports are saved to a
# file instead of only in the browser. Run it from the repository folder:
#   python run.py py src/serve_catalogue.py [--port 8000]        then open http://localhost:8000/ (it opens by itself)
# Reports ("Report a problem" on a label) go to screenscraper-labels/reports.json, every change saved at once.
# "Leave these out" writes the reported images into screenscraper-labels/ignore.txt (one line each, what's wrong as a
# comment), clears them from the reports, removes them (screenscraper_download.py --dedupe) and builds the page again
# (screenscraper_site.py), which then reloads without them. Don't use it while a download is running.
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


def rebuild():
    """Remove what ignore.txt lists (--dedupe) and build the page again; True if both went well."""
    import subprocess
    here = os.path.dirname(os.path.abspath(__file__))
    for script, extra in (("screenscraper_download.py", ["--dedupe"]), ("screenscraper_site.py", [])):
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
        elif self.path == "/api/reports":
            with LOCK:
                self._json(200, load())
        else:
            super().do_GET()

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
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

    def log_message(self, fmt, *args):  # only the saves, not every image
        if "/api/" in (args[0] if args else ""):
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
