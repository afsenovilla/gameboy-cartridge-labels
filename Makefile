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
#   make match
#   Pairs of photos showing something alike, with their homographies, into generated/match/; the page
#   generated/match/index.html. Needs make features.
#
# Plain make lists these.

PYTHON := .venv/bin/python
GENERATED := $(if $(SAMPLE),generated-sample,generated)
SAMPLE_FLAG := $(if $(SAMPLE),--sample,)

.PHONY: help setup test read-text clean-read-text features clean-features match clean-match
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
