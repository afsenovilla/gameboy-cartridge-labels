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
| print | The idealized image made by one set of printing plates. Two label photos of one print differ only by physical imperfections: dirt, smear, scratches, glare, misregistration of the color plates, lens distortion, compression, lighting, sensor noise. |
| design | Prints judged not meaningfully different (only the serial or the regional logos differ). Judged by hand, never computed. |
| the database | gb-game-list. One record is a database entry. "Release" is informal. |
| shape | The cartridge's plastic: DMG (grey, also the black dual-mode cartridges), CGB (clear, CGB only), AGB. Not the platform, which is the serial's prefix. |
| similar | A measured quantity (aligned pixels alike). Never means "the same print". |

"Label" alone is informal: never in names, files or fields.

## Goal (settled)

### Output

- **Restored prints:** for every print a human has judged visually distinct, a restored image, reconstructed from all
  its label photos, in mm, with its serial. Other prints are ignored in the output, but every print group gets a quick
  restoration first, since there's nothing to judge before that. Cropped at the median cut position of its label photos (labels are printed with overflow and cut
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
(DMG-TRA) can't be known in advance; they're found as separate print groups and judged then. *(Proposed: is designs.json
the design input, and is "done" then "every design has a restored print"?)*

### Review

No verdicts unless there's no other way. Each step writes a page that can be read, so a problem found later can be
traced to the step that made it. Corrections are a hand-edited file the steps respect (splitting and merging print
groups; later perhaps flags from website visitors).

### What may be used

The point: never build on main's hand-entered verdicts, or more hand entering would be needed.

- Input: the photos, OCR, the database, main's code, main's designs.json.
- Not as input: main's fits.json or any other verdicts main's tools stored, the old file names, the sources.
- Not as ground truth either: main's fits are mostly fairly accurate but have outliers off by about 3 mm, and main's
  approach is what this branch replaces.
- Main's sources.json (URL by SHA-1; 2950 of 5519 photos have one) is for output only, never read by a detection
  step.

## Approach notes so far

- **Scale:** all label photos of a print have exactly the same physical scale. (The 0.46 % spread measured earlier is
  most likely error in finding the recess, about 0.15 mm.)
- **The plastic is a tool, not a goal:** only for the scale and perspective in mm. The recess is a soft constraint: a
  label sometimes sticks out of it by about a mm.
- **Recess evidence is pooled per print:** not every photo has to find the recess. One may give the top and bottom edges,
  another the sides. If none does, the median over the SIFT matches (most photos are about head-on), flagged as such; in
  the worst case, human input.
- **Telling prints apart** (dirt and scratches from layout revisions) is central, not a refinement. With 10 or more label
  photos it should work for about 90 % of releases; the rest are corrected by hand.
- **Prints seen in only one photo** (about half the photos earlier) have nothing to match: their extent and straightening
  come from the recess and the label's own edges.

## How results are judged (under discussion)

There is no ground truth: main's fits aren't one (see above). Results are judged by each step's own measures, on its
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

**Development sample (agreed):** a fixed set of about 300 photos, committed, so a change is measured in minutes. Full
runs only once a step is stable on it. How to choose it is open (below).

Open questions:

1. **Choosing the sample.** It needs prints seen many times, or grouping prints can't be tried: 300 random photos of
   5518 would hold few repeats. Knowing which photos show which print takes the old names. Proposal: use main's names
   only to pick the sample, never in a step: about 35 database entries and all their photos (about 300): DMG-TRA-JPN
   (two revisions), entries with 20 or more photos, entries with one, all three shapes, Konsolenkost composites, photos
   with several cartridges.
2. **Designs:** is designs.json the design input, and "done" every design having a restored print (above)?

## Still to discuss

Approach, architecture, data structures, steps (each simple for a human to run; no needless steps).
