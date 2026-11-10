# Crawling eBay

Cartridge photos from eBay searches, for releases no label photo has. Learned on 2026-11-09 and 10, with the USA releases (676 of 715 searched, 3154 photos downloaded, 2945 kept after the user's look).

## What works and what doesn't

- **Search pages need a browser.** curl on `https://www.ebay.com/sch/i.html?...` gets HTTP 403, even with a browser User-Agent. They are fetched from inside an ebay.com tab instead, through the Claude in Chrome extension.
- **Images don't.** curl on `https://i.ebayimg.com/images/g/<image id>/s-l1600.jpg` works: the same bytes as saving the image from Chrome. No browser needed for them.
- **Never open tabs with AppleScript.** Each new tab brings Chrome to the front and takes macOS's focus from whatever the user is doing. AppleScript's `save` of an image tab does work (the file gets a `.html` name but is the JPEG), but it isn't needed.
- **AppleScript can't run JavaScript in Chrome** unless View > Developer > Allow JavaScript from Apple Events is turned on (it's off).
- **Searching inside one tab disturbs nothing.** The page stays on ebay.com; each search is a `fetch()` of the search URL (with the user's cookies), parsed with `DOMParser`. No navigation, no new tabs, no focus.

## Sizes

- `s-l1600` is the largest size eBay serves: the long side is at most 1600 px. Seen: 1600x1600, 1534x1462, 1254x1254, 1200x1600.
- Asking for `s-l1600` of a smaller original gives the original: one was a 300x300 logo. Photos under 1000 px on the long side are dropped.
- `.jpg` and `.webp` both work at the end of the URL; `.jpg` gives JPEG.

## Search results

- One search per release: `<title> <GBA | Game Boy Color | Game Boy> cartridge`, category Video Games (`_sacat=139973`), 60 per page (`_ipg=60`). The database title is turned around for the query ("Lord of the Rings, The - ..." -> "The Lord of the Rings ...", " - " -> " ").
- Results are `li.s-item` or `li.s-card`. The first ones are "Shop on eBay" placeholders with item number 123456: skip them.
- Each result has the item number (`/itm/<number>`), the title (minus "Opens in a new window or tab" and a leading "NEW LISTING") and an image id from `i.ebayimg.com/images/g/<id>/`, in `src`, `data-src` or `srcset` (lazy loading).
- **A result's image is the listing's first photo**, normally the front of the cartridge. So the listing pages need not be opened: one page load per release.
- Below the matches comes "Results matching fewer words": unrelated games. The title-word filter drops them.

## Filters on listing titles

- **Not a loose cartridge:** box, boxed, CIB, complete, manual, lot, bundle, case, sealed, repro, reproduction, custom, sticker, replacement, label only, poster, guide, strategy, insert, cover art, empty, shell only, artwork.
- **Another system:** for GBA releases GBC, Game Boy Color, DS, 3DS, PSP, GameCube, Sega; for Game Boy and Game Boy Color releases GBA, Advance, DS, 3DS, PSP, N64, Sega.
- **Another region** (applied when downloading): Japan, Japanese, JPN, JP, NTSC-J, PAL, EUR, Europe, UK, German, French, Spanish, Italian, import, Chinese, Korean, or a serial like `AGB-P-BJBJ`. Japanese cartridges do get listed on ebay.com.
- **The game itself:** at least ¾ of the title's words (minus "the", "of", "GBA", "game", "boy" and the like) in the listing title.
- At most 10 candidates per search; the first 5 that download at 1000 px or more are kept.
- What the filters miss: dirty cartridges, logos and stock pictures, some boxes. The user went through the photos and deleted 209 of 3154.

## Getting data in and out of the page

- The page can't write files, and the extension returns data only to the conversation. Passing hundreds of results through the conversation costs tokens and means retyping ids.
- **In:** the query list goes in as a file: a file input is added to the page, and the extension's `file_upload` puts the local JSON file in it (147 KB for 715 queries).
- **Out:** a browser download is the page's only way to disk. The page saves the results found since the last time every 2 minutes as `~/Downloads/ebay-batch-usa-<n>.json`; a background shell loop moves each one away and downloads its images with curl. Chrome asks once whether ebay.com may download several files.
- Saving everything only at the end meant nothing showed up for two hours: don't.
- The results are also in the page's `localStorage` (`EB.results`), and it keeps its queue: it can resume after an error as long as the tab isn't closed or reloaded.

## Pace and blocking

- One search every 9 to 13 s (about 11 s): 676 searches in about 2 hours, then HTTP 403 on every search. The loop stops at the first error.
- Not known yet: how long the block lasts, and whether a slower pace (one every 30 s) avoids it.
- `curl` on the images (one a second, about 3000) was never blocked.

## The release list

- generated/read-serials/missing.json holds the database's record ids (`agb-0003`, `AGB-A22J`), not serials: that's why it looks mixed. The cartridge serials are in each record's `cartridgeSerials` in gb-game-list's releases.json; 716 missing releases have a `-USA` one. About 2300 have no cartridge serial; their region is the last letter of the game id (`AGB-A22J` is Japan).
- Searching ebay.com for European or Japanese releases mostly finds US cartridges. Planned: ebay.co.uk and ebay.de for Europe, Japanese titles with "Japan" for Japan. Not tried.

## Files

The downloader:

src/ebay_photos.py

It makes the query list (`queries USA`) and takes in the page's batches (`ingest <batch> <queries>`). Its records, one per downloaded photo, also those deleted by hand afterwards, so they're never downloaded again:

ebay-photos/sources.json

Every release searched, with its counts, so a run can resume:

ebay-photos/searches.json

New photos go to the drop-off folder with a listing.json (page_url, image_url, title_on_page, searched_release, searched_serial, query, fetched), for make add-photos, which files them into photos/ as `<sha1>.jpg` and their origin into photo-sources.json:

save-new-images-here/ebay-search/

The first 2945 photos are still in ebay-photos/, with their listing.json there.

## The page's script

Run in an ebay.com tab with the extension's javascript_tool; then a file input appears top left, and `file_upload` of the query file starts the searches. `EB.stop = true` stops them; `EB.run()` resumes.

```js
window.EB = window.EB || {results: {}, queue: [], running: false};
EB.BAD = /\b(box|boxed|cib|complete|manual|manuals|lot|bundle|case|sealed|repro|reproduction|custom|sticker|replacement|label only|poster|guide|strategy|insert|cover art|empty|shell only|artwork)\b/i;
EB.STOP = new Set(['the','a','an','of','and','in','to','gba','game','boy','color','advance','cartridge','vs','&']);
EB.words = s => s.toLowerCase().normalize('NFKD').replace(/[^a-z0-9 ]/g,' ').split(/\s+/).filter(w => w && !EB.STOP.has(w));
EB.search = async function (q) {
  const url = 'https://www.ebay.com/sch/i.html?_nkw=' + encodeURIComponent(q.query) + '&_sacat=139973&_ipg=60';
  const r = await fetch(url, {credentials: 'include'});
  if (!r.ok) throw new Error('HTTP ' + r.status);
  const html = await r.text();
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const items = doc.querySelectorAll('li.s-item, li.s-card');
  if (!items.length && !/No exact matches|0 results/i.test(html)) throw new Error('no result list (blocked?)');
  const want = EB.words(q.title), other = new RegExp(q.exclude, 'i');
  const out = [];
  for (const li of items) {
    const a = li.querySelector('a[href*="/itm/"]'); if (!a) continue;
    const item = (a.getAttribute('href').match(/\/itm\/(\d+)/) || [])[1]; if (!item || item === '123456') continue;
    const title = ((li.querySelector('.s-item__title, .s-card__title') || {}).textContent || '').replace(/Opens in a new window or tab/, '').replace(/^NEW LISTING/, '').trim();
    const img = [...li.querySelectorAll('img')].map(i => i.getAttribute('src') + ' ' + (i.getAttribute('data-src') || '') + ' ' + (i.getAttribute('srcset') || '')).join(' ');
    const image = (img.match(/i\.ebayimg\.com\/images\/g\/([A-Za-z0-9~_-]+)\//) || [])[1];
    if (!image || EB.BAD.test(title) || other.test(title)) continue;
    const have = new Set(EB.words(title));
    if (want.filter(w => have.has(w)).length / Math.max(1, want.length) < 0.75) continue;
    if (out.some(o => o.image === image)) continue;
    out.push({item, title, image});
    if (out.length >= 10) break;
  }
  return out;
};
EB.flushed = EB.flushed || new Set(); EB.batch = EB.batch || 0;
EB.flush = function () {
  const part = {};
  for (const [r, v] of Object.entries(EB.results)) if (!EB.flushed.has(r)) { part[r] = v; EB.flushed.add(r); }
  if (!Object.keys(part).length) return 0;
  EB.batch++;
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(part)], {type: 'application/json'}));
  a.download = 'ebay-batch-usa-' + String(EB.batch).padStart(3, '0') + '.json'; document.body.appendChild(a); a.click(); a.remove();
  return Object.keys(part).length;
};
EB.run = async function () {
  if (EB.running) return; EB.running = true; EB.error = null; EB.stop = false;
  try {
    for (const q of EB.queue) {
      if (EB.stop) break;
      if (q.release in EB.results) continue;
      EB.current = q.release;
      try { EB.results[q.release] = await EB.search(q); }
      catch (e) { EB.error = q.release + ': ' + e.message; break; }
      try { localStorage.setItem('EB.results', JSON.stringify(EB.results)); } catch (e) {}
      await new Promise(r => setTimeout(r, 9000 + Math.random() * 4000));
    }
  } finally { EB.running = false; EB.flush(); }
};
if (EB.flushTimer) clearInterval(EB.flushTimer);
EB.flushTimer = setInterval(EB.flush, 120000);
const inp = document.createElement('input'); inp.type = 'file'; inp.setAttribute('aria-label', 'EB queries file');
inp.style.cssText = 'position:fixed;top:0;left:0;z-index:99999';
inp.onchange = async () => { EB.queue = JSON.parse(await inp.files[0].text()); EB.run(); };
document.body.prepend(inp);
```

The shell loop that takes in the batches (S: a folder for the query file and the batches taken in):

```bash
cd /Users/vicwid/code/geon/gameboy-labels-detection
while true; do
  for f in $(find ~/Downloads -maxdepth 1 -name 'ebay-batch-usa-*.json' | sort); do
    mv "$f" "$S/batches/" && python3 src/ebay_photos.py ingest "$S/batches/$(basename "$f")" "$S/queries.json"
  done
  sleep 30
done
```

## Open

- 39 USA releases not searched (the block). Resume slower, after a pause.
- Other regions: not started.
- Listing pages (all photos of a listing, not only the first) weren't needed; the listing's own gallery is its `s-l140` thumbnails, and the page also holds other listings' images.
