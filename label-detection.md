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

- **Restored prints:** for every print seen in photos/, a restored image, reconstructed from all its label photos, in
  mm, with its serial. Cropped at the median cut position of its label photos (labels are printed with overflow and cut
  sloppily; the whole print is detected first, then cropped).
- **Label photos:** each one straightened in its print's frame, the same crop, with the photo's source and original
  URL.
- **Database entries with no label photo:** a list, for tools that search for more photos (getting photos is part of
  the project).
- **Serials not in the database:** possible new releases, a by-product.

Not output: straightened cartridges, plastic fits, a 5 mm margin, difference images between serials of a design (fun to
make later: mask out every pixel that's the same across serials).

### Done

Every standard-cartridge database entry, as the database is now, has at least one restored print. More than one print
per design is fine. Which designs are meaningfully distinct (DMG-TRA's two Japanese revisions are; serials and
regional logos aren't) is a separate human judgement, not a review of the output. Expanding the database is out of
scope.

### Review

No verdicts unless there's no other way. Each step writes a page that can be read, so a problem found later can be
traced to the step that made it. Corrections are a hand-edited file the steps respect (splitting and merging print
groups; later perhaps flags from website visitors).

### What may be used

- Input: the photos, OCR, the database, main's code.
- Not as input: main's fits.json or any other data main's tools made, the old file names, the sources.
- Main's data may be used to evaluate. Main's sources.json (URL by SHA-1; 2950 of 5519 photos have one) is used for
  output only. *(Proposed, not yet confirmed.)*

## Approach notes so far

- **Scale:** all label photos of a print have exactly the same physical scale. (The 0.46 % spread measured earlier is
  most likely error in finding the recess, about 0.15 mm.)
- **The plastic is a tool, not a goal:** only for the scale and perspective in mm. The recess is a soft constraint: a
  label sometimes sticks out of it by about a mm.
- **Recess evidence is pooled per print:** not every photo has to find the recess. One may give the top and bottom edges,
  another the sides. If none does, the median over the SIFT matches (most photos are about head-on); in the worst case,
  human input.
- **Telling prints apart** (dirt and scratches from layout revisions) is central, not a refinement. With 10 or more label
  photos it should work for about 90 % of releases; the rest are corrected by hand.
- **Prints seen in only one photo** (about half the photos earlier) have nothing to match: their extent and straightening
  come from the recess and the label's own edges.

## How results are judged (proposed, under discussion)

**A. Each step's own measures, on its page** (no ground truth needed; worst first):

| Step's job | Measure |
|---|---|
| Finding label photos | photos with none; photos with more than plausible |
| Registration to the print | pixel difference after alignment; spread of SIFT inliers in mm |
| Recess and scale | agreement of a print's pooled recess edges, in mm |
| Print groups | regions where a label photo differs from its print consistently (revision) rather than randomly (dirt) |
| Serial | agreement of the reads within a print |

**B. Comparison with main's data,** in a separate step nothing else reads:

| Main's data | Checks |
|---|---|
| hand and accepted fits (fits.json) | the label's position in mm, compared at the cut edge (up to about 1 mm expected: print against cut) |
| serials in the old file names | serial reading and grouping |
| designs.json | print groups splitting or merging designs wrongly |

Limit: main's fits favor photos that fitted well; photos never fitted there only get A.

**Development sample:** a fixed set of about 300 photos, chosen once and committed, so a change is measured in minutes:
photos with hand fits in main, all three shapes, photos with several cartridges, a few Konsolenkost composites, prints
seen many times and prints seen once. Full runs only once a step is stable on the sample.

Open questions:

1. Is main's data acceptable as ground truth, or are parts of it untrusted (some accepted fits were automatic)?
2. A committed development sample of about 300 photos?

## Still to discuss

Approach, architecture, data structures, steps (each simple for a human to run; no needless steps).
