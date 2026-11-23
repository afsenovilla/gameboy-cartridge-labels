# Working on this repository

This is afsenovilla's fork of geon/gameboy-cartridge-labels. geon's repository restores Game Boy, Game Boy Color and
Game Boy Advance cartridge labels from photos (`src/restore.py`, `src/publish.py` and the rest of the pipeline in
the Makefile and `label-detection.md`). The fork adds a **local catalogue**: a page to browse every label we have,
with a Missing list to complete the database. Restoring labels is no longer the main focus.

## Where things run

- The owner works on Windows in PowerShell, in `C:\Users\villa\Desktop\Code\gameboy-cartridge-labels`, and runs
  everything as `python run.py py src/<script>.py ...` from the repository folder. Give commands in that form.
- The release database is `C:\Users\villa\Desktop\Code\gb-game-list\database\releases.json` (`serials.DATABASE`). It
  is a stand-in built from geon's site listing (`src/bootstrap_database.py`), so it has gaps and a few misread
  serials. Correct them in `screenscraper-labels/database-fixes.json` and leave the database itself alone.
- The catalogue is **local only**. Don't publish anything under `screenscraper-labels/`. Its images come from
  ScreenScraper and LaunchBox users' uploads, and publishing them would redistribute those sites' databases.
- Another session also commits to `main` on the fork (the 3D viewer in `docs/3d/`). Always
  `git fetch && git rebase` onto the fork's main before pushing.

## The catalogue

Everything lives in `screenscraper-labels/` (git-ignored):

| What | Made by | Notes |
|---|---|---|
| `gb/`, `gbc/`, `gba/`, `index.json` | `screenscraper_download.py` | Label images from ScreenScraper, one per game and region |
| `matches.json`, `ocr/` | `screenscraper_match.py` | Each image's serial, read by OCR (`read_text`, `serials`) |
| `added/`, `added.json` | the review page, "Add label" or by hand | Labels found by hand. **The `added/` folder is what counts**: a file named `SERIAL.png` or `SERIAL_2.png` is a label even if `added.json` lost its entry |
| `ignore.txt` | by hand, or reports applied on the page | Images to leave out, by file name or ScreenScraper game id |
| `database-fixes.json` | by hand | `{"wrong serial": "right serial"}`, or `""` to drop a serial or a whole release (`agb-0488`) |
| `labels.json`, `wanted.json`, `index.html` | `screenscraper_site.py` (uses `build_site.build`) | The page. Missing has one entry per serial, with `kind` "game" (no label of the game at all) or "variant" |
| `reports.json` | the page, through `serve_catalogue.py` | Labels reported as wrong |
| `inbox/`, `candidates/`, `candidates.json` | `inbox.py`, `serve_catalogue.py` | Photos waiting for review |
| `launchbox/`, `launchbox.json` | `launchbox_fetch.py` | LaunchBox's Metadata.zip and what has been fetched |

`python run.py py src/serve_catalogue.py` serves it at http://localhost:8000/. It rebuilds the page when it starts
and whenever `added.json`, `added/`, `ignore.txt`, `matches.json` or `database-fixes.json` change, and open pages
reload by themselves. The review page is at `/review`.

### ScreenScraper

- `screenscraper_download.py` searches by title (`--missing` searches only Missing titles, in GB and GBC both). It
  remembers finished searches and saves `index.json` atomically, so it can be stopped and rerun safely.
- Searches are punctuation-sensitive: "10-Pin Bowling" finds the game and "10 pin bowling" doesn't.
- `--dedupe` removes byte-identical images, keeping the most specific region: a single country beats `eu`.
- Hacks, fangames and e-Reader cards are filtered out (publisher ROMhacking.net, a synopsis saying "a hack of",
  no country and no publisher).
- Credentials are in `screenscraper.json`.

### Review inbox

A photo dropped into `inbox/`, uploaded on `/review`, or fetched by a script goes through these steps:

1. `label_crop.detect` finds the label's corners. It is a best guess and right about half the time.
2. `label_crop.crop` straightens the label to 820 px wide at its true proportions (`ASPECT`: 1.139 for GB/GBC,
   1.986 for GBA) and fills the rounded corners.
3. OCR reads the serial. A serial in the file name (`DMG-QC-NOE__launchbox_x.jpg`) is the fallback and marks what
   the photo was fetched for (`fetched_as`).
4. The page shows one line of advice per photo (`verdict()` in `review_page.py`) and rings the button to press. The
   corners can be dragged, with a loupe, or nudged with the arrow keys; then OCR reads the serial again.
5. Accept straightens the photo at full size, saves it into `added/`, and moves the photo to `inbox/done/`.

Some photos are rejected without being shown, and stay in `inbox/`. Nothing is ever deleted:

- **Too small:** the label is under 200 px wide even with the corners right (`inbox.TOO_SMALL`). Those are better
  found by hand.
- **Already there:** a label of that serial exists at least as sharp, and the serial is not Missing. This applies
  only when OCR read the serial on the label and no look-alike serial (8/B, 0/O, 1/I, 5/S, 2/Z, 6/G) is Missing.
  **When in doubt, keep the photo for review.**

A label narrower than 450 px in its source is flagged low resolution (`lowres`) for a second pass.

### Photo sources

- `launchbox_fetch.py` matches LaunchBox's "Cart - Front" photos by title and region (`--any-region` takes any
  region) and keeps at most 3 per cartridge. It has been run to the end.
- eBay is next, through its API, once the owner has a key.
- game-boy-database.com was tried and dropped: its photos are watermarked.
- Never remove watermarks from photos.

## Conventions

- Python, no framework. Tests are in `tests/` (`python -m pytest tests -q`). Two tests in
  `tests/test_remove_photos.py` were already failing before the catalogue work.
- Comments and docstrings say why, in plain words, with a real example (a serial, a title).
- Page text is in English. Talk to the owner in Spanish.
- After writing a file on the owner's computer through the device bridge, stage it again and check that it changed:
  commits through the bridge have sometimes written stale content.
