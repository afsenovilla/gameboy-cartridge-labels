import json, os, re, sys, urllib.parse, cv2
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fits, photos, serials
from fit_cartridge import load

# find-doubles: a local page listing every photo in photos/, one release per row (the release its serial is filed
# under in gb-game-list, the region dropped if gb-game-list lacks it; else the serial itself), its photos sorted by
# their source's quality (SOURCES, best first), each marked with an orange check if its plastic is fitted (accepted or
# placed by hand), a green one if its label is too. Each photo can be deleted (photos.delete), its fits with it.
# Usage: find_doubles.py [port]
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8770
# The sources, best first: Hit-Japan highest, otakaraou the lowest real photos, the fakes made from box art below it.
# A source not listed goes just above otakaraou.
SOURCES = ("ebay-hitjapan", "my-collection", "ebay-elrocinante", "yugiyahirano", "jnlgame", "jauce", "mercari", "rakuma",
           "retros-ae", "gbhwdb", "ebay", "tradera", "kleinanzeigen", "marktplaats", "gamestop", "google", "unrecorded",
           "otakaraou", "emumovies", "launchbox-abeezy1388")


def rank(source):
    return SOURCES.index(source) if source in SOURCES else SOURCES.index("otakaraou") - 0.5


def image(path, longest):
    """The photo, its longest side at most longest px, as JPEG bytes."""
    photo = load(path, even_colors=False)
    scale = min(1, longest / max(photo.shape[:2]))
    small = cv2.resize(photo, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()


def rows():
    """[{"release", "title", "photos": [{"path", "source", "fitted": None, "plastic" or "label"}]}], by release."""
    release_of = serials.releases_by_serial()
    known = fits.load()
    found = {}
    for source, system, name, entry in photos.all_sources():
        serial = photos.serial_of(name)
        match = next((s for s in (serial, re.sub(r"-[A-Z]{3}$", "", serial)) if s in release_of), None)
        release = release_of[match] if match else None
        key = release["id"] if release else serial
        row = found.setdefault(key, {"release": key, "title": release["title"] if release else "(not in gb-game-list)", "photos": []})
        fit = fits.of(known, photos.stem(name), entry.get("sha1"))["fit"]
        fitted = "label" if fits.good(fit.get("label")) else "plastic" if fits.good(fit.get("plastic")) else None
        row["photos"].append({"path": os.path.join(photos.ROOT, source, system, name), "source": source, "fitted": fitted})
    for row in found.values():
        row["photos"].sort(key=lambda p: (rank(p["source"]), p["path"]))
    return [found[k] for k in sorted(found)]


PAGE = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Find doubles</title>
<style>
body{font:14px system-ui;margin:0;background:#f4f4f4;color:#222}
header{position:sticky;top:0;z-index:1;background:#fff;padding:8px 16px;border-bottom:1px solid #ddd;display:flex;gap:16px;align-items:center}
#count{margin-left:auto;font-variant-numeric:tabular-nums}
.row{display:flex;gap:12px;padding:8px 16px;border-bottom:1px solid #e4e4e4;align-items:flex-start}
.release{width:180px;flex:none}.release b{display:block}.release span{color:#555}
.photos{display:flex;gap:8px;overflow-x:auto}
figure{margin:0;width:180px;flex:none;background:#fff;border-radius:0.3em;padding:6px;position:relative}
figure img{width:180px;height:180px;object-fit:contain;display:block}
figcaption{font-size:12px;color:#555;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin:4px 0}
.check{position:absolute;top:8px;right:8px;width:22px;height:22px;border-radius:50%;color:#fff;font-weight:700;text-align:center;line-height:22px}
.check.plastic{background:#e8830c}.check.label{background:#2a9d3a}
button{font:inherit;padding:2px 8px;border:none;border-radius:0.3em;color:#b00}
</style>
<header><b>Find doubles</b><label><input type="checkbox" id="doubles"> only releases with several photos</label>
<span><span class="check plastic" style="position:static;display:inline-block">✓</span> plastic fitted
<span class="check label" style="position:static;display:inline-block">✓</span> label fitted</span><span id="count"></span></header>
<main id="rows"></main>
<script>
const $ = id => document.getElementById(id);
const esc = s => s.replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"})[c]);
let rows = [];
function render() {
  const shown = $("doubles").checked ? rows.filter(r => r.photos.length > 1) : rows;
  $("count").textContent = `${shown.length} releases, ${shown.reduce((n, r) => n + r.photos.length, 0)} photos`;
  $("rows").innerHTML = shown.map(r => `<div class="row"><div class="release"><b>${esc(r.release)}</b><span>${esc(r.title)}</span></div><div class="photos">` +
    r.photos.map(p => `<figure>${p.fitted ? `<span class="check ${p.fitted}" title="${p.fitted} fitted">✓</span>` : ""}` +
      `<a href="/image?size=1600&path=${encodeURIComponent(p.path)}" target="_blank"><img loading="lazy" src="/image?size=360&path=${encodeURIComponent(p.path)}" alt=""></a>` +
      `<figcaption title="${esc(p.path)}">${esc(p.source)}<br>${esc(p.path.split("/").pop())}</figcaption>` +
      `<button data-path="${esc(p.path)}">Delete</button></figure>`).join("") + `</div></div>`).join("");
}
$("rows").onclick = async e => {
  const path = e.target.dataset && e.target.dataset.path;
  if (!path || !confirm(`Delete ${path} from photos/?`)) return;
  const response = await fetch("/delete", {method: "POST", body: JSON.stringify({path})});
  if (!response.ok) return alert("Not deleted: " + await response.text());
  for (const r of rows) r.photos = r.photos.filter(p => p.path !== path);
  rows = rows.filter(r => r.photos.length);
  render();
};
$("doubles").onchange = render;
fetch("/rows").then(r => r.json()).then(r => { rows = r; render(); });
</script>
"""


def is_photo(path):
    """Whether path is a photo in photos/ (photos/<source>/<system>/<name>, with an entry in its sources.json)."""
    parts = path.split(os.sep)
    return len(parts) == 4 and parts[0] == photos.ROOT and ".." not in parts and parts[3] in photos.sources(parts[1], parts[2]) and os.path.isfile(path)


class Handler(BaseHTTPRequestHandler):
    def send(self, body, kind="application/json", status=200):
        body = json.dumps(body).encode() if kind == "application/json" else body
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(url.query)
        if url.path == "/":
            self.send(PAGE.encode(), "text/html; charset=utf-8")
        elif url.path == "/rows":
            self.send(rows())
        elif url.path == "/image" and is_photo(path := query.get("path", [""])[0]):
            self.send(image(path, min(1600, int(query.get("size", ["360"])[0]))), "image/jpeg")
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/delete":
            return self.send_error(404)
        path = json.loads(self.rfile.read(int(self.headers["Content-Length"])))["path"]
        if not is_photo(path):
            return self.send(b"not a photo in photos/", "text/plain", 400)
        photos.delete(path)
        with fits.editing():
            pass  # its fits go with it (fits.reconcile)
        print(f"{path} deleted", flush=True)
        self.send({})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"Photos by release at http://localhost:{PORT}/ (ctrl-C to stop)")
    ThreadingHTTPServer(("localhost", PORT), Handler).serve_forever()
