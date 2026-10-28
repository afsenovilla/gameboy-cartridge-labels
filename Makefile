# The steps from photos to label images, one target each. A target runs its step and nothing else: never another step
# first. Each step skips what it has already done; make clean-<step> deletes its output, to redo it.
#
#   make setup
#   Creates the Python environment, .venv/, with the packages in requirements.txt.
#
# Plain make lists these.

PYTHON := .venv/bin/python

.PHONY: help setup
help:
	@awk '/^#   /{line = substr($$0, 5); if (line ~ /^make / && n++) print ""; print line}' Makefile

setup:
	python3 -m venv .venv
	$(PYTHON) -m pip install -r requirements.txt
