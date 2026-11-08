# Label detection: the plan

Restored images of every print of every Game Boy cartridge in photos/, from the photos alone. Started over on
2026-11-08 from 3fdc1fb (photos/ only); the earlier attempt is on branch `label-detection-attempt-2026-11-08`, with its
measurements in its own label-detection.md.

This time everything is agreed before any code is written, in this order: goal, how results are judged, approach,
architecture, data structures, steps. Each section says whether it's settled.

## Terms (settled)

| Term | Meaning |
|---|---|
| photo | One file in photos/. |
| cartridge | One physical cartridge. A photo can show several; the same cartridge can be in several photos, often without us knowing. |
| label photo | One physical label as seen in one photo. A photo has zero or more. |
| candidate | A place in a photo that may be a label photo, until shown to be one. |
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

- **Restored prints:** at least every print a human has judged visually distinct (judged on the straightened label
  photos): a restored image, reconstructed from all its label photos, in mm, with its serial. Cropped at the median cut position of its label photos (labels are printed with overflow and cut
  sloppily; the whole print is detected first, then cropped).
- **Label photos:** each one straightened in its print's frame, the same crop, with the photo's source and original
  URL.
- **Database entries with no label photo:** a list, for tools that search for more photos (getting photos is part of
  the project).
- **Serials not in the database:** possible new releases, a by-product.

Not output: straightened cartridges, plastic fits, a 5 mm margin, difference images between serials of a design (fun to
make later: mask out every pixel that's the same across serials).

### Done

Every design of the standard-cartridge database entries, as the database is now, has at least one restored print. More
than one print per design is fine. Which designs are meaningfully distinct (DMG-TRA's two Japanese revisions are;
serials and regional logos aren't) is a separate human judgement, not a review of the output. Expanding the database is
out of scope.

The database entries are grouped into designs by main's designs.json: by default one design per game stem and market
(Japan, the USA, the rest of the world), and its 111 records the exceptions judged by hand (merges and splits). It's
input data about database entries, not a verdict on any fit, so it's reused. Several prints within one database entry
(DMG-TRA) can't be known in advance; they're found as separate print groups and judged then.

### Review

No verdicts unless there's no other way. Each step writes a page that can be read, so a problem found later can be
traced to the step that made it. Corrections are a hand-edited file the steps respect (splitting and merging print
groups; later perhaps flags from website visitors).

### What may be used

The point: never build on main's hand-entered verdicts, or more hand entering would be needed.

- Input: the photos, OCR, the database, main's code, main's designs.json.
- Not as input: main's fits.json or any other verdicts main's tools stored, the old file names, the sources.
- Not as ground truth either: main's fits are mostly fairly accurate but have outliers off by about 3 mm, and main's
  approach is what this branch replaces. Comparing with main statistically (distributions, agreement rates) is fine;
  no single photo's data in main is taken as true.
- Main's sources.json (URL by SHA-1; 2950 of 5519 photos have one) is for output only, never read by a detection
  step.

## Approach (being settled)

- **Two coordinate systems, both in mm:**
  - **ink coordinates:** on the printed image; one per shape, shared by all its prints. Prints sharing areas are
    positioned so those areas coincide (two US DMG prints' logo bars on the same mm). The restored prints and the
    straightened label photos are drawn in them, at a fixed px/mm.
  - **plastic coordinates:** on the cartridge, as main's shape models; the recess is there.
  - The paper isn't a coordinate system: each sticker's cut outline is a shape in ink coordinates, different for every
    sticker; their median is the crop.
- **Each label photo has two unknowns,** solved jointly over all label photos:
  - **photo → ink,** a homography (8 numbers), from SIFT matches between label photos of different photos. Not only of
    the same print: nearly-same prints and shared templates (the grey frame and logo bar of US and European DMG labels)
    align too, which is wanted; the pixels decide afterwards what is the same.
  - **ink → plastic, the placement:** where this sticker's ink sits on its cartridge, a shift and a turn (3 numbers;
    about 1 mm and 2° at most), from the recess edges (found to about 0.15 mm; a label can stick out by about 1 mm). The
    recess thus gives scale and perspective through the placement, which absorbs its position (and the small offset of
    the label lying below the face, seen at an angle).
  - The cut edges are close to straight (bowing about 0.1 mm on the long side, from the cutting) and help the
    perspective; their position only gives the crop.
  - **Anchoring:** for each set of prints linked by shared areas, the median placement over their label photos is the
    nominal label place (DMG: main's 42.5 × 37 mm rectangle, 7.25 mm from the cartridge's left edge, 19 mm from its
    top). A print linked to no other is anchored by its own label photos.
- **Finding label photos** (proposed): the plastic isn't needed for it.
  - Seeds: OCR of every photo (it worked well before); a serial read and found in the database makes a candidate where
    it was read, the text line giving rough place, turn and size. A candidate with a serial is a label photo.
  - Spreading: SIFT matches from a label photo to another photo make candidates there; one in the ink area is a label
    photo, even when no serial is read on it (its serial is read once it's straightened, or stays unknown).
  - Matches that never touch a label photo (watermarks, backgrounds, embossing) are never used: no serial, nothing to
    spread from.
  - Photos with no label photo are listed.
  - Several cartridges in a photo: several serials, several matches per pair of photos (RANSAC repeated).
- **Several versions of a step will be tried** before it works reliably: methods are compared on the sample by the
  steps' own measures.
- **After the solve:** prints told apart by the aligned pixels (a difference shared consistently by a subset is a
  print of its own; a random one is dirt); restoration pools every label photo that agrees in an area; the serial is
  read by OCR on the straightened label photos and voted within a print.
- **Fakes** (box art on rendered cartridges) stay in photos/: a fake either matches real label photos or it doesn't. One
  matching nothing is a print from a single label photo, and shows in that list.

- **Scale:** all label photos of a print have exactly the same physical scale. (The 0.46 % spread measured earlier is
  most likely error in finding the recess, about 0.15 mm.)
- **The plastic is a tool, not a goal:** only for the scale and perspective in mm. The recess is a soft constraint: a
  label sometimes sticks out of it by about a mm.
- **Recess evidence is pooled per print:** not every photo has to find the recess. One may give the top and bottom edges,
  another the sides. If none does, the median over the SIFT matches (most photos are about head-on), flagged as such; in
  the worst case, human input.
- **Telling prints apart** (dirt and scratches from layout revisions) is central, not a refinement. With 10 or more label
  photos it should work for about 90 % of releases; the rest are corrected by hand.
- **Few label photos per print:** of main's old names, 2459 (65 %) have one photo, 1034 two, 224 three, 46 four, 25 five
  or more, one (DMG-APSJ-JPN) 12. Different serials are different prints, so most prints have one or two label photos.
  So:
  - **Nearly-same prints are pooled:** where prints agree (everything but the serial, the rating and CE logos, say),
    their label photos are pooled for restoring that area. The rating and CE logos are ignored, both for pooling and for
    judging designs.
  - **More photos on demand:** prints with too few label photos are listed; more are downloaded when needed.
  - **A single label photo is used as it is:** if it's good there's nothing to restore. Its quality can't be measured,
    so it's marked as from one photo; website visitors may report problems.
- **Several cartridges in a photo** are rare (never downloaded on purpose) but happen: never assume one per photo.
- **Prints seen in only one photo** (about half the photos earlier) have nothing to match: their extent and straightening
  come from the recess and the label's own edges.

## How results are judged (under discussion)

There is no ground truth: main's fits aren't one (see above), though main may be compared with statistically. Results
are judged by each step's own measures, on its
page, worst first, so the human looks where things are most likely wrong:

| Step's job | Measure |
|---|---|
| Finding label photos | photos with none; photos with more than plausible |
| Registration to the print | pixel difference after alignment; spread of SIFT inliers in mm |
| Recess and scale | agreement of a print's pooled recess edges, in mm; prints that fell back to the SIFT median, flagged |
| Print groups | regions where a label photo differs from its print consistently (revision) rather than randomly (dirt) |
| Serial | agreement of the reads within a print |

The weakness: consistency can't show an error every label photo of a print shares (all recesses found 1 mm too low,
say). Only looking catches that, so each page shows the images, not only the numbers.

**Development sample:** sample.txt, one SHA-1 per line: 276 photos of 96 old names (DMG 157 photos, CGB 63, AGB 56),
so a change is measured in minutes; full runs only once a step is stable on it. Chosen once from main's old names
(never read by a step), seeded random: DMG-TRA (with the [MINUET] photos), every DMG name with 5 or more photos, every
CGB name with 3 or more, 12 AGB names with 3, and per shape 5 names with 2 photos and 10 with 1. Konsolenkost isn't in
photos/; photos with several cartridges can't be told from the names, so they're in only by chance. Can be changed.

## Still to discuss

Approach, architecture, data structures, steps (each simple for a human to run; no needless steps).
