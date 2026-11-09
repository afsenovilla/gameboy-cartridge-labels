# Label detection: the plan

Restored images of every print of every Game Boy cartridge in photos/, from the photos alone. Started over on 2026-11-08 from 3fdc1fb (photos/ only); the earlier attempt is on branch `label-detection-attempt-2026-11-08`, with its measurements in its own label-detection.md.

This time everything is agreed before any code is written, in this order: goal, how results are judged, approach, architecture, data structures, steps. Each section says whether it's settled.

## Terms (settled)

| Term | Meaning |
|---|---|
| photo | One file in photos/. |
| cartridge | One physical cartridge. A photo can show several; the same cartridge can be in several photos, often without us knowing. |
| label photo | One physical label as seen in one photo. A photo has zero or more. |
| candidate | A place in a photo that may be a label photo, until shown to be one. |
| label photo key | The photo's SHA-1 and the label photo's centre where first found, in whole percent of the photo's width and height: `<sha1>@48,55`. A later detection whose centre falls inside an existing label photo's outline is that label photo and keeps its key. Stickers can't overlap in a photo, so two label photos can't share a key. |
| print | The idealized image made by one set of printing plates. Two label photos of one print differ only by physical imperfections: dirt, smear, scratches, glare, misregistration of the color plates, lens distortion, compression, lighting, sensor noise. |
| design | Prints judged not meaningfully different (only the serial or the regional logos differ). Judged by hand, never computed. |
| the database | gb-game-list. One record is a database entry. "Release" is informal. |
| shape | The cartridge's plastic: DMG (grey, also the black dual-mode cartridges), CGB (clear, CGB only), AGB. Not the platform, which is the serial's prefix. |
| ink / plastic coordinates | mm on the printed image (one per shape) / mm on the cartridge (main's shape models). |
| placement | Where one sticker's ink sits on its plastic: a shift and a turn. |
| similar | A measured quantity (aligned pixels alike). Never means "the same print". |

"Label" alone is informal: never in names, files or fields.

## Goal (settled)

### Output

- **Restored prints:** at least every print a human has judged visually distinct (judged on the straightened label photos): a restored image, reconstructed from all its label photos, in mm, with its serial. Cropped at the median cut of its linked set's label photos (labels are printed with overflow and cut sloppily; the whole print is detected first, then cropped).
- **Label photos:** each one straightened in its print's frame, the same crop, with the photo's source and original URL.
- **Database entries with no label photo:** a list, for tools that search for more photos (getting photos is part of the project).
- **Serials not in the database:** possible new releases, a by-product.

Not output: straightened cartridges, plastic fits, a 5 mm margin, difference images between serials of a design (fun to make later: mask out every pixel that's the same across serials).

### Done

Every design of the standard-cartridge database entries, as the database is now, has at least one restored print. More than one print per design is fine. Which designs are meaningfully distinct (DMG-TRA's two Japanese revisions are; serials and regional logos aren't) is a separate human judgement, not a review of the output. Expanding the database is out of scope.

The database entries are grouped into designs by main's designs.json: by default one design per game stem and market (Japan, the USA, the rest of the world), and its 111 records the exceptions judged by hand (merges and splits). It's input data about database entries, not a verdict on any fit, so it's reused. Several prints within one database entry (DMG-TRA) can't be known in advance; they're found as separate print groups and judged then.

### Review

No verdicts unless there's no other way. Each step writes a page that can be read, so a problem found later can be traced to the step that made it. Corrections are a hand-edited file the steps respect (splitting and merging print groups; later perhaps flags from website visitors).

### What may be used

The point: never build on main's hand-entered verdicts, or more hand entering would be needed.

- Input: the photos, OCR, the database, main's code, main's designs.json.
- Not as input: main's fits.json or any other verdicts main's tools stored, the old file names, the sources.
- Not as ground truth either: main's fits are mostly fairly accurate but have outliers off by about 3 mm, and main's approach is what this branch replaces. Comparing with main statistically (distributions, agreement rates) is fine; no single photo's data in main is taken as true.
- Main's sources.json (URL by SHA-1; 2950 of 5519 photos have one) is for output only, never read by a detection step.

## Approach (settled)

- **Two coordinate systems, both in mm:**
  - **ink coordinates:** on the printed image; one per shape, shared by all its prints. Prints sharing areas are positioned so those areas coincide (two US DMG prints' logo bars on the same mm). The restored prints and the straightened label photos are drawn in them, at a fixed px/mm.
  - **plastic coordinates:** on the cartridge, as main's shape models; the recess is there.
  - The paper isn't a coordinate system: each sticker's cut outline is a shape in ink coordinates, different for every sticker; the median over a linked set anchors ink coordinates and is the crop.
- **Each label photo has two unknowns,** solved jointly over all label photos:
  - **photo → ink,** a homography (8 numbers), from SIFT matches between label photos of different photos. Not only of the same print: nearly-same prints and shared templates (the grey frame and logo bar of US and European DMG labels) align too, which is wanted; the pixels decide afterwards what is the same.
  - **ink → plastic, the placement:** where this sticker's ink sits on its cartridge, a shift and a turn (3 numbers; about 1 mm and 2° at most), from the recess edges (found to about 0.15 mm; a label can stick out by about 1 mm). The recess thus gives scale and perspective through the placement, which absorbs its position (and the small offset of the label lying below the face, seen at an angle).
  - The cut edges are close to straight (bowing about 0.1 mm on the long side, from the cutting) and help the perspective; their position only gives the crop.
  - **Anchoring:** for each linked set, ink coordinates are anchored by the median cut outline of all its label photos (position and turn): the median cut is the nominal label place (DMG: main's 42.5 × 37 mm rectangle, at 0, 0 in ink coordinates). Ink coordinates are then the restored labels' coordinates: the crop is axis-aligned, the straightened images are in final coordinates, and publishing crops whole pixels with no resampling. Every print of a set gets the same crop: prints may sit slightly differently against their cuts (the fixed-place logos spread about 0.3 mm), but any plausible position will do, none is more right. A set of one label photo is anchored by its own cut.
- **To experiment with: links only through uniquely shared areas.** A match through common areas alone (the grey frame of US and European DMG labels) links label photos of hundreds of games into one linked set with one anchor. Instead, a match would link two label photos only if enough of its inliers lie outside the common areas (where a label photo's keypoints match many label photos of many looks; the same idea as the details). Linked sets then become families of nearly-same prints. Lost: the frame's help in aligning a label photo whose print is seen once; it's then a set of one, from its own cut and recess edges and the details at fixed places (the template, used deliberately).
- **Finding label photos:** the plastic isn't needed for it. Evidence adds up; no single piece is required.
  - Seeds: OCR of every photo (it worked well before). A serial-looking string is a candidate, the text line giving rough place, turn and size.
  - A SIFT match near a similar string in another photo is a strong sign of a label photo. The database confirms the serial, more so when the title is read too and matches the entry's. (Not requiring the database is also what lets serials not in it be found.)
  - Spreading: SIFT matches from a label photo make candidates in other photos, also where no serial is read (it's read once straightened, or stays unknown).
  - The ink's extent: the continuous area where a match's aligned pixels agree; it may run onto the plastic where that looks alike, so it's bounded by the label's cut edges, detected at this stage. Matches off it (a watermark in the same photo) don't spread.
  - Watermarks, backgrounds and embossing carry no serial-looking string and so never start anything.
  - The shape comes from the serial's prefix (DMG-, CGB-, AGB-; the black dual-mode cartridges are DMG- on the DMG shape); a label photo found only by matching takes its match's.
  - Photos with no label photo are listed.
  - Several cartridges in a photo: several strings, several matches per pair of photos (RANSAC repeated).
- **Several versions of a step will be tried** before it works reliably: methods are compared on the sample by the steps' own measures.
- **The joint solve:**
  - Each linked set (label photos connected by matches) is solved on its own: sets share nothing, a bad match spoils only its own set. A label photo linked to no other is a set of one, from its own edges.
  - One least-squares fit per set, each constraint weighted by its precision (a match spread over the whole label weighs more than one on the logo bar alone; the recess to about 0.15 mm; the placement softly limited to about 1 mm).
  - Label photos of one print share their scale exactly. Nearly-same prints are assumed to line up as they are (the same size and position in ink coordinates). Nothing dictates it, and some include logos or background art at a different scale; such an element is simply an area that differs. A scale, turn and shift per print, lining its drawing up with its nearly-same prints', is not built until the leftover errors show it's needed.
  - Starts chained through the set's matches.
  - A plain homography, no lens distortion: it hasn't seemed to matter. Each label photo's leftover error shows if it does.
- **Common details** (the Game Boy Color logo, the Nintendo seals, the ESRB E, CE...): found automatically, named once by hand. Uses: the rating and CE logos masked out when pooling and judging designs; seeds for finding label photos (like a serial-looking string); starts (a 2D picture with many keypoints gives place, turn and rough size; their size varies between labels); a difference that is only a known detail is named as such, not taken for a revision.
  - Found once, from main's fits (a one-off, like the sample; no step reads main): main's label fits straightened, areas that match across label photos of many different serials (a game's own art doesn't recur across games) cut out in mm, one image per detail, committed. Named once on a page, and marked whether ignored.
  - Made 2026-11-08 (one-off scripts, not in the repo): main's 3941 accepted label fits straightened at 20 px/mm with a 3 mm margin (the mm approximate); SIFT matches between labels of different games, only within a platform; recurring areas found from 1200 of them, then every label of the platform searched for each; each instance aligned by a homography (SIFT, then ECC against the median, twice), in the median of the copies' own straightenings (not the reference's, which skewed some); each copy's contrast and brightness per channel fitted to the median; the median color, no alpha (the spread mostly marked edges, not content), cropped 0.5 mm around the keypoints matched in at least 30 % of the copies. Then by hand and on request: named; serial fragments deleted (text is OCR's job); duplicates merged (all their copies in the most complete one's frame); the CE + seal + licensed split. 25 details in details/; no pairs left that align with a high correlation. No masks: noise around a detail only adds keypoints that match nothing.
  - **Where they sit (measured 2026-11-08,** every straightened label of main's accepted fits searched for every detail; positions in mm on main's label model, whose fits are off by about 0.3 mm, so spreads of that size are the limit of the measurement):
    - At one place on almost every label (97 % or more within 1 mm, spread about 0.3 mm): both GAME BOY COLOR logos (CGB at 3.8, 18.8 mm; DMG at 3.8, 18.6), KONAMI (AGB, 100 %), ONLY FOR GAME BOY COLOR (CGB, 96 %); licensed by nintendo on CGB 88 %. These can anchor the label's position.
    - At a few fixed places, one main: THIS SIDE OUT (DMG 76 %), ゲームボーイ アドバンス (AGB about 65 %), licensed by nintendo (DMG, AGB), MADE IN JAPAN (DMG 42 %, several others).
    - Anywhere: ORIGINAL, the Super GAME BOY logo, the link cable logos, HUDSON and its bee, K-A esrb rating, Ubi Soft.
    - Not found at all: seal of quality and CE dark bg + top of seal (18 keypoints each, too few for the SIFT search).
    - Copies found on another platform at unrelated places are mostly false matches (similar katakana, turned 5° or more).
  - The spread of the fixed-place logos (about 0.3 mm) is measured on main's label fits, which follow each sticker's cut outline: cut sloppiness and fit error together are about 0.3 mm on those labels (accepted fits only, which may favour clean cuts), less than the "up to about 1 mm" assumed above. In ink coordinates a template's logo sits at the same place by definition, so its spread measured against the cut is the best measure of the cut.
  - Details with few keypoints (seal of quality, CE: 18 each, after being split and cropped) aren't found by SIFT in a raw photo. In straightened label photos (known scale and turn) they're found by template matching instead; that's where they're needed (masking the CE when pooling and judging).
  - **To experiment with: details as evidence of region.** A detail's wording tells nothing (MADE IN JAPAN is on US and European labels too), but its version and place tell the label's layout, and the layout correlates with region: this MADE IN JAPAN, on the grey side strip at about 2.0, 28.8 mm, is found on 300 USA labels and some European ones, never on Japanese ones. As evidence for the serial vote (a region where OCR reads only the game code), not proof.
  - Later, new details can be found the same way from this branch's own label photos.
- **Telling prints apart** (settled), per linked set, in ink coordinates:
  1. Each label photo's colors evened: per channel a scale and offset fitted to the set's median.
  2. Compared in tiles (1 mm to start; 5 mm may do as well) after a blur of about 0.25 mm, so sub-pixel misalignment and sharpness don't count. Tile size and blur are set on the sample by the steps' own measures.
  3. Per tile, label photos grouped by how alike they look: all alike, a shared area; one different, a defect on that sticker (dirt, scratch, glare); two or more groups of at least two each, a print difference.
  4. Label photos agreeing on every tile with a print difference are one print.
  5. Per print, which other prints share each tile: the pooling masks for restoration.
  - A difference seen in one label photo only counts as a defect: a revision seen once is missed until more photos of it turn up (it shows in the list of prints with few label photos).
  - Different serials, ratings or CE logos are different prints (different plates), so every one gets its own restored image; they're masked out only when pooling and judging designs.
  - Designs may be judged by hand before a print has more than one label photo, so designs group **label photos**, not prints (print groups change as photos are added; label photos don't). A print whose label photos are in different designs is a contradiction, flagged, never resolved silently.
  - Main's designs.json (designs of database entries) is converted once into designs of label photos, as soon as label photos have serials, and then dropped; if it doesn't convert easily, it's ignored and regrouped by hand.
- **Restoration** (settled), per print, in ink coordinates at 20 px/mm (508 dpi: prints are commonly 600 dpi or less; one setting):
  - Contributing to a pixel: the print's own label photos, plus other prints' wherever the pooling masks say the tile is shared.
  - Each label photo, colors evened, split into frequency bands in Oklab: a Laplacian pyramid from 20 px/mm, halving until one pixel is left (about 10 bands). A label photo counts in a band only where it carries it, as in focus stacking: per band, a weight map from the band's local energy, blurred over a radius larger than the details, compared between the label photos at each pixel; bands finer than a photo's own resolution get no weight. A partly focused label photo then counts where it's sharp.
  - Per band, weighted by sharpness: one label photo as it is; two averaged (halving scratches and glare); three or more by a soft median, an M-estimator such as Tukey's biweight (starting from the median, values reweighted smoothly by their distance from the estimate: no ridges where gradients point different ways), its scale from the bands' own noise. The plain median is made too; the user judges which is better.
  - To try: the lowest bands de-emphasized to even the lighting (like the iPhone's "Brilliance"); not sound, may look fine. Dropped if complex.
  - Crop: the linked set's median cut (the anchor of ink coordinates: axis-aligned, the same for every print of the set); size main's canonical label sizes (DMG 42.5 x 37 mm, CGB 41.5 x 37, AGB 43 x 22).
  - Colors: to be experimented with (paper white with clipping as in main, which was noticeable as it had to be strong; the median of the label photos; others). Pooling in bands should leave less noise in the paper.
- **After the solve:** prints told apart by the aligned pixels (a difference shared consistently by a subset is a print of its own; a random one is dirt); restoration pools every label photo that agrees in an area; the serial is read by OCR on the straightened label photos and voted within a print.
- **Fakes** (box art on rendered cartridges) stay in photos/: a fake either matches real label photos or it doesn't. One matching nothing is a print from a single label photo, and shows in that list.

- **Scale:** all label photos of a print have exactly the same physical scale. (The 0.46 % spread measured earlier is most likely error in finding the recess, about 0.15 mm.)
- **The plastic is a tool, not a goal:** only for the scale and perspective in mm. The recess is a soft constraint: a label sometimes sticks out of it by about a mm.
- **Recess evidence is pooled per print:** not every photo has to find the recess. One may give the top and bottom edges, another the sides. If none does, the median over the SIFT matches (most photos are about head-on), flagged as such; in the worst case, human input.
- **Telling prints apart** (dirt and scratches from layout revisions) is central, not a refinement. With 10 or more label photos it should work for about 90 % of releases; the rest are corrected by hand.
- **Few label photos per print:** of main's old names, 2459 (65 %) have one photo, 1034 two, 224 three, 46 four, 25 five or more, one (DMG-APSJ-JPN) 12. Different serials are different prints, so most prints have one or two label photos. So:
  - **Nearly-same prints are pooled:** where prints agree (everything but the serial, the rating and CE logos, say), their label photos are pooled for restoring that area. The rating and CE logos are ignored, both for pooling and for judging designs.
  - **More photos on demand:** prints with too few label photos are listed; more are downloaded when needed.
  - **A single label photo is used as it is:** if it's good there's nothing to restore. Its quality can't be measured, so it's marked as from one photo; website visitors may report problems.
- **Several cartridges in a photo** are rare (never downloaded on purpose) but happen: never assume one per photo.
- **Prints seen in only one photo** (about half the photos earlier) have nothing to match: their extent and straightening come from the recess and the label's own edges.

## How results are judged (settled)

There is no ground truth: main's fits aren't one (see above), though main may be compared with statistically. Results are judged by each step's own measures, on its page, worst first, so the human looks where things are most likely wrong:

| Step's job | Measure |
|---|---|
| Finding label photos | photos with none; photos with more than plausible |
| Registration to the print | pixel difference after alignment; spread of SIFT inliers in mm |
| Recess and scale | agreement of a print's pooled recess edges, in mm; prints that fell back to the SIFT median, flagged |
| Print groups | regions where a label photo differs from its print consistently (revision) rather than randomly (dirt) |
| Serial | agreement of the reads within a print |

The weakness: consistency can't show an error every label photo of a print shares (all recesses found 1 mm too low, say). Only looking catches that, so each page shows the images, not only the numbers.

**Development sample:** sample.txt, one SHA-1 per line: 276 photos of 96 old names (DMG 157 photos, CGB 63, AGB 56), so a change is measured in minutes; full runs only once a step is stable on it. Chosen once from main's old names (never read by a step), seeded random: DMG-TRA (with the [MINUET] photos), every DMG name with 5 or more photos, every CGB name with 3 or more, 12 AGB names with 3, and per shape 5 names with 2 photos and 10 with 1. Konsolenkost isn't in photos/; photos with several cartridges can't be told from the names, so they're in only by chance. Can be changed.

## Architecture (settled)

- **A step owns its output and never changes another step's.** Data flows one way: no step's output feeds an earlier step. (The last attempt broke this: three steps deleted each other's fits, and results depended on the order they ran in.) Steps iterate within themselves (find's spreading, solve's least squares, restore's soft median), never between each other. The one loop across steps is through hand input: new details found later go into details/ by hand, and find uses them on the next run.
- **One make target per step:** it runs its own step only, skips what's done, redoes what's older than its step's code (as main; misses changes in shared modules, enough for now); make clean-<step> redoes all of it.
- **Output in generated/<step>/:** one file per photo where the work is per photo (by SHA-1: a photo is processed once, unless the step's settings change), else one file for the step.
- **Each step writes a page,** generated/<step>/index.html: its measures, worst first, with the images.
- **Hand input,** committed, read by steps and never written: details/ and designs.json (label photo key -> design). No corrections file: print detection splits prints; a label photo put in a design of its own makes a wrongly lumped print a flagged contradiction; merges are what designs.json does.
- **Keys aren't remembered between runs:** each run names a label photo by its current centre; a key in designs.json belongs to the label photo whose outline contains that point.
- **The sample:** make <step> SAMPLE=1 runs on sample.txt into generated-sample/, so trying a version of a step never touches the full run.

| Step | Work | Output |
|---|---|---|
| read-text | OCR of each photo; first, RapidOCR compared with Apple Vision on the sample (valid serials read, agreement), the better one kept | text lines and their corners, per photo |
| features | SIFT of each photo, nothing label-specific | keypoints, per photo |
| edges | every straight line segment in each photo, no interpretation | segments, per photo |
| match | one index of all keypoints; pairs checked by RANSAC, several homographies per pair; incremental (a new photo matched against all; old pairs kept) | matches and their inlier areas |
| find | label photos from the evidence (serial-looking strings, details, matches, the database; the ink's extent from agreeing pixels and cut edges); spreading until nothing changes | label photos: keys, rough outlines, evidence |
| solve | the joint solve per linked set; which segments are a cut or a recess decided against the shape model | homography into ink and placement, per label photo |
| straighten | each label photo drawn in ink coordinates | images, for the next steps and the user's judging |
| read-serials | OCR of the straightened label photos, voted per linked set | serials |
| prints | the tile comparison | prints, pooling masks |
| restore | bands, weights, combining, crop | restored prints |
| publish | the outputs | label photo crops with source and URL, restored prints, the lists |

match and find are separate so that the rule for a label photo can be tried in versions without redoing the matching.

## Data structures (settled)

**Conventions:**
- Photo coordinates: pixels of the photo as stored, its EXIF turn applied; x right, y down.
- Ink coordinates: mm, origin at the nominal label's top left (main's label model moved to 0, 0); plastic coordinates: main's cartridge mm.
- Homographies: 3 x 3 lists named `<from>_to_<to>` (photo_to_ink).
- JSON for what a person might read; .npz for large arrays; generated images AVIF at a high quality (they can be regenerated; checked once on the sample: tile differences and file sizes with and without compression); details/ stays PNG (used for matching).
- Label photo key: `<sha1>@<x>,<y>`. Print id: the smallest key among its label photos (within a run only, never in hand files).

| Step | File | Contents |
|---|---|---|
| read-text | read-text/<sha1>.json | size, engine; lines: text, confidence, corners |
| features | features/<sha1>.npz | points, sizes, angles, descriptors (uint8) |
| edges | edges/<sha1>.npz | segments (x1, y1, x2, y2), strength |
| match | match/<sha1>.npz | matches against the photos processed before it: each pair once, in the later photo's file; a file never changes once written; per match the other SHA-1, a_to_b, the inlier point pairs |
| find | find/label-photos.json | per label photo: key, outline (rough), shape, evidence (strings and whether in the database, title, details, matches and their pixel agreement); sets (lists of keys); rejected candidates and why |
| solve | solve/solve.json | per label photo: photo_to_ink, placement (dx, dy mm, turn), fallback (null or "sift median"), leftover error; per set: recess spread, leftover errors |
| straighten | straighten/<key>.avif | 20 px/mm, the nominal label plus 5 mm around it, uncropped (the crop is decided by restore, and restoration pools the overflow past the cut) |
| read-serials | read-serials/serials.json, missing.json, unknown-serials.json | per key: reads, serial (voted or null), in_database; database entries with no label photo; serials not in the database |
| prints | prints/prints.json, prints/<print>/<other>.png, few-photos.json | per print: id, keys, serial, shape. Optional pair images, one pixel per tile, white where the two look alike; only for pairs whose shared area, less the tiles many prints of the set share (the grey frame), is above a limit (tuned on the sample) |
| restore | restore/<print>.avif, restore/<print>.json | the image (cropped); label photos used, how many count in each band, single-photo flag |
| publish | publish/ | prints/<print>.avif; label-photos/<key>.avif (cut from its straightened image: whole pixels, no resampling); index.json (per label photo: print, serial, source, URL; per print: label photos, serial); the lists collected |

designs.json (hand-edited): `{"<key>": "<design name>"}`; a label photo not listed has no design yet.

- To try (restore): the designer's vision, a print restored without the extra logos and seals.

## Tests (settled)

Unit tests are written along with the code, from the first step on (the last attempt had none, nor has main). Mostly on small made-up cases with known answers (a joint solve recovering known homographies, the key matching, the tile grouping telling a planted revision from planted dirt), so they run in seconds; pytest, run with `make test`.

## Next

The first code: read-text, starting with RapidOCR compared with Apple Vision on the sample.
