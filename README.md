# Game Boy labels

Clean, straight-on images of Game Boy cartridge labels, made from photos of cartridges: my own, and ones found online,
collected into a database with a quality grade and the origin of every label.

## Setup

Needs Python 3.12 or newer and, for the release names and to know which releases are missing,
[gb-game-list](../gb-game-list) checked out next to this repository (or wherever the environment variable `GB_GAME_LIST`
says). Without it everything runs, using only the serials in the photos' names, and the database says so.

### Windows

No admin rights, `make` or macOS needed. In PowerShell:

```powershell
git config --global core.longpaths true
git clone https://github.com/afsenovilla/gameboy-cartridge-labels.git
cd gameboy-cartridge-labels
py -3 run.py setup
py -3 run.py test
```

The repository is about 3 GB. Then `py -3 run.py` lists the steps, and `py -3 run.py <step>` runs one.

### macOS and Linux

`make setup`, then `make` lists the steps; `python3 run.py <step>` works too. macOS reads text with its Vision framework,
other systems with RapidOCR; `OCR_ENGINE=vision` or `rapidocr` chooses.

## From photos to the database

```
python run.py rectify    # generated/labels/: every accepted label, straightened, at 20 px/mm
python run.py database   # generated/database/labels.sqlite and report.html
```

Only labels whose plastic and label were accepted or placed by hand get in. Nothing is edited in the database: it's made
afresh each time, so a wrong row is corrected where it comes from (a photo's name, `fits.json`, `preferred.json`).

| Table | What's in it |
| --- | --- |
| `releases` | each release known |
| `photos` | every photo: source, URLs, serial, state of its fit |
| `labels` | every straightened label: file, SHA-256, measures, grade, why it isn't better, `is_best` |
| `issues` | what to check: wrong or misnamed files, labels that look like another serial's, releases with poor labels |
| `best_labels` (view) | each release's label to use |

The grades:

| Grade | Means |
| --- | --- |
| A | a real photo, sharp, well exposed, at least 12 px/mm |
| B | a real photo, with one measure below A's |
| C | a real photo that's poor or watermarked (otakaraou): only until a better one turns up |
| F | a fake (box art on a rendered cartridge): a placeholder, never more |

A photo chosen by hand in `find-doubles` is the best one of its release, whatever its grade; `issues` says if a better
grade exists. The grades' thresholds, at the top of `src/build_database.py`, are a first setting.

Most photos come from third parties and the repository has no license: check the rights before publishing the images.

## Where things are

- `save-new-images-here/`: drop off new photos here, in a subfolder named after where they came from.
- `photos/`: every photo of a cartridge, `photos/<source>/<system>/<serial>[_<n>].<ext>`, with a `sources.json` per folder
  saying where each photo came from. A photo is named by the serial printed on its label; to correct one, rename it.
- `special-shells.tsv`: the cartridges whose shell isn't the usual one (rumble, tilt sensor, infrared…), left out of the
  fitting. Edited by hand.
- `src/`: the scripts.
- `fits.json`: every photo's fit, and my verdicts on it.
- `preferred.json`: the photo chosen by hand for a release.
- `generated/`: everything made from the photos (not committed).

## Steps

Run `make` or `python run.py` to list them. Each step is one target, and runs only that step.
