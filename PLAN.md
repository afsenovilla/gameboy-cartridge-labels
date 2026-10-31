# Plan

The goal: for each Game Boy and Game Boy Color cartridge release, a clean, straight-on image of its label, made from
photos of cartridges, and composited onto a clean cartridge of the right type. For the card images of the cartridge
database in [gb-game-list](../gb-game-list) (`database/releases.json`). Nothing runs unsupervised: every fit and every
image is reviewed before it's used.

## Sources, best first

Photos of a release from a better source replace those from a worse one, whenever one turns up.

1. Real photos: my own (`my-collection`), gbhwdb, and photos from listings and searches (eBay, Jauce, Mercari, Google…).
2. `otakaraou`: real photos, but small (median short side 800 px). Kept only for releases with no photo from (1).
3. `emumovies` and `launchbox-abeezy1388`: **the lowest quality. Not photos but fakes**: one rendered cartridge with a
   label made from box art pasted in. Kept only for releases with nothing else, and never a reason to delete a photo
   from (1) or (2). A release with only these still counts as missing a photo.
   - `launchbox-abeezy1388`: 193 images, one template (1000 × 1132 px, the label in (131, 333)–(868, 980)), so one
     hand fit (DMG-MH-USA_2's) is copied to them all.
   - `emumovies`: 356 images, three templates, each with one hand fit copied to the rest: 199 at 994 × 1132 px
     (DMG-A2BE-USA's), 155 at 878 × 1000 px (DMG-602-CHN's), 2 at 995 × 1132 px (DMG-AK-USA's).

## Steps

Done, run with `make` (see the Makefile): add-photos, read-text, fit-cartridge (the plastic), fit-label (the label in its
recess). Tools for judging and fixing fits: review-fits, review-labels, fit-by-hand; for finding and naming photos:
search-photos, name-photos.

## Open work

- **Check fit-label and review-labels** (built, awaiting my check).
- **Depth layers for the CGB shell** (board and walls behind the front face): waits for my measurements.
- Then: rectify (straighten the label), group the artwork, pick the best photo of each release.
- **A tool comparing labels by their look against their serials**: similar labels with different serials (likely
  misreads: about 2 % of photos named by their text are wrong), and identical serials that look different (misnamed
  photos, or real variants such as reprints).
- **Verify photos against game-boy-database.com's scans.** Its cartridge scans (`cartridges/<id>.jpg`, next to the box
  photos gb-game-list lists, ~660 × 760, tightly cropped, original Game Boy only, one per country serial) are
  watermarked, so hardly usable themselves, but their labels are easy to find. Where a photo's label matches the
  unmasked part of the scan's label (allowing for lightness and the like), the photo counts as verified: its serial
  and its label. The watermark's mask was made on `collection-pipeline` (`experiments/wm_mask.py`; old PLAN.md,
  Pipeline 2): one overlay, scaled to the scan's width and centered vertically; in a 660 × 800 frame, the letters
  (pink in the average of many scans) widened by a 13 px ellipse, plus the robot logo at x 250–410, y 0–215; 16 % of
  the frame. Likely real scans, not composites like the fakes.
- **gb-game-list's serials** are incomplete (AGB 47 %, serials without region): fix later.
- **Cleanup of the branch's history** (hand fits, fits.json redesign): later.
