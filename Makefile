# The steps from photos to label images, one target each. A target runs its step and nothing else: never another step
# first. Each step skips what it has already done; make clean-<step> deletes its output, to redo it. With SAMPLE=1 a
# step works on the photos in sample.txt only, into generated-sample/ instead of generated/.
#
#   make setup
#   Creates the Python environment, .venv/, with the packages in requirements.txt.
#
#   make test
#   Runs the unit tests (tests/).
#
#   make read-text
#   Reads the text on every photo (RapidOCR) into generated/read-text/<sha1>.json; the page generated/read-text/index.html.
#
#   make features
#   SIFT keypoints of every photo into generated/features/<sha1>.npz; the page generated/features/index.html.
#
#   make edges
#   Every straight line segment in every photo (LSD) into generated/edges/<sha1>.npz; the page generated/edges/index.html.
#
#   make match
#   Pairs of photos showing something alike, with their homographies, into generated/match/; the page
#   generated/match/index.html. Needs make features.
#
#   make find
#   The label photos in every photo, from serials read and matches, into generated/find/label-photos.json; the page
#   generated/find/index.html. Needs make read-text and make match.
#
#   make solve
#   Every label photo's homography into ink coordinates (the sticker's cut fitted to the edges, the linked sets aligned
#   by their matches) into generated/solve/solve.json; the page generated/solve/index.html. Needs make find and edges.
#
#   make straighten
#   Every solved label photo in ink coordinates (20 px/mm, 5 mm around the label) into generated/straighten/; the page
#   generated/straighten/index.html. Needs make solve.
#
#   make read-serials
#   Every label photo's serial (OCR of the straightened label photos, settled within its family), the database's
#   entries with no label photo and the serials it doesn't know, into generated/read-serials/. Needs make straighten.
#
#   make prints
#   Each family's label photos split into prints by a tile comparison, into generated/prints/; the page generated/prints/index.html. Needs make read-serials.
#
#   make restore
#   An image of every print from its label photos (bands, the median), cropped to the canonical label, paper white
#   where found, into generated/restore/; the page generated/restore/index.html. Needs make prints.
#
#   make publish
#   The outputs collected into generated/publish/: prints/, label-photos/ (straightened, the same crop), index.json
#   (source and URLs from main's sources.json) and the lists; the page generated/publish/index.html. Needs make restore.
#
# Plain make lists these.

PYTHON := .venv/bin/python
GENERATED := $(if $(SAMPLE),generated-sample,generated)
SAMPLE_FLAG := $(if $(SAMPLE),--sample,)

.PHONY: help setup test read-text clean-read-text features clean-features edges clean-edges match clean-match find clean-find solve clean-solve straighten clean-straighten read-serials clean-read-serials prints clean-prints restore clean-restore publish clean-publish
help:
	@awk '/^#   /{line = substr($$0, 5); if (line ~ /^make / && n++) print ""; print line}' Makefile

setup:
	python3 -m venv .venv
	$(PYTHON) -m pip install -r requirements.txt

test:
	$(PYTHON) -m pytest -q tests

read-text:
	$(PYTHON) src/read_text.py $(SAMPLE_FLAG)

clean-read-text:
	rm -rf $(GENERATED)/read-text

features:
	$(PYTHON) src/features.py $(SAMPLE_FLAG)

clean-features:
	rm -rf $(GENERATED)/features

match:
	$(PYTHON) src/match.py $(SAMPLE_FLAG)

clean-match:
	rm -rf $(GENERATED)/match

find:
	$(PYTHON) src/find.py $(SAMPLE_FLAG)

clean-find:
	rm -rf $(GENERATED)/find

edges:
	$(PYTHON) src/edges.py $(SAMPLE_FLAG)

clean-edges:
	rm -rf $(GENERATED)/edges

solve:
	$(PYTHON) src/solve.py $(SAMPLE_FLAG)

clean-solve:
	rm -rf $(GENERATED)/solve

straighten:
	$(PYTHON) src/straighten.py $(SAMPLE_FLAG)

clean-straighten:
	rm -rf $(GENERATED)/straighten

read-serials:
	$(PYTHON) src/read_serials.py $(SAMPLE_FLAG)

clean-read-serials:
	rm -rf $(GENERATED)/read-serials

prints:
	$(PYTHON) src/prints.py $(SAMPLE_FLAG)

clean-prints:
	rm -rf $(GENERATED)/prints

restore:
	$(PYTHON) src/restore.py $(SAMPLE_FLAG)

clean-restore:
	rm -rf $(GENERATED)/restore

publish:
	$(PYTHON) src/publish.py $(SAMPLE_FLAG)

clean-publish:
	rm -rf $(GENERATED)/publish
