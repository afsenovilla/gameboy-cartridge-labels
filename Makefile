# The steps from photos to label images, one target each. A target runs its step and nothing else: never another step
# first. Each step skips what it has already done; make clean-<step> deletes its output, to redo it.
#
#   make setup
#   Creates the Python environment, .venv/, with the packages in requirements.txt.
#
#   make add-photos
#   Files the photos left in save-new-images-here/ into photos/, each named by the serial read on its label (src/add_photos.py).
#
#   make read-text
#   Reads the text on every photo in photos/ into generated/read-text/<photo>.json: every line of text found, and where it is (src/read_text.py).
#
#   make match-serials
#   Matches the serial on each photo's label, from its text, against gb-game-list's releases, into generated/match-serials/serials.tsv (src/match_serials.py).
#
#   make fit-cartridge
#   Fits the cartridge's model to every photo but Game Boy Advance ones and those listed in special-shells.tsv, started from its text, into generated/fit-cartridge/<photo>.json: the pose of its plastic (the label is left for a later step), and flags for review; a fit judged good in reviews/fits.json is kept, not fitted again (src/fit_cartridge.py, src/cartridge.py).
#
#   make review-fits
#   A tool, not a step: a local page for judging the plastic's fits by eye, each drawn on its photo, flagged ones first; your verdicts are saved to reviews/fits.json (src/review_fits.py).
#
#   make search-photos
#   A tool, not a step: a local page of searches (Google, Bing, the eBay sellers elrocinante and Hit-Japan, Jauce) for photos of the Game Boy and Game Boy Color releases without a fit judged good, into generated/search-photos/index.html (src/search_photos.py).
#
#   make name-photos
#   A tool, not a step: a local page for naming the photos whose serial isn't known, one at a time: type the serial on its label and press enter; the photo is renamed in photos/, its verdicts in reviews/fits.json with it; or delete it (src/name_photos.py). Not while make review-fits runs.
#
# Plain make lists these.

PYTHON := .venv/bin/python

.PHONY: help setup add-photos read-text clean-read-text match-serials clean-match-serials fit-cartridge clean-fit-cartridge review-fits search-photos name-photos
help:
	@awk '/^#   /{line = substr($$0, 5); if (line ~ /^make / && n++) print ""; print line}' Makefile

setup:
	python3 -m venv .venv
	$(PYTHON) -m pip install -r requirements.txt

add-photos: | src/ocr
	$(PYTHON) src/add_photos.py

read-text: | src/ocr
	$(PYTHON) src/read_text.py

clean-read-text:
	rm -rf generated/read-text

match-serials:
	$(PYTHON) src/match_serials.py

clean-match-serials:
	rm -rf generated/match-serials

fit-cartridge:
	$(PYTHON) src/fit_cartridge.py

clean-fit-cartridge:
	rm -rf generated/fit-cartridge

review-fits:
	$(PYTHON) src/review_fits.py

search-photos:
	$(PYTHON) src/search_photos.py

name-photos:
	$(PYTHON) src/name_photos.py

# The text recognition tool, built when missing (macOS).
src/ocr: src/ocr.swift
	swiftc -O $< -o $@
