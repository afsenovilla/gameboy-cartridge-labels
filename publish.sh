#!/usr/bin/env bash
# make publish: src/publish.py writes into a temporary work tree of the gh-pages branch, replacing all it held; the
# result is committed there and pushed to origin.
set -e

git fetch origin gh-pages:gh-pages
temp=$(mktemp -d)
trap 'chmod -R u+w "$temp"; rm -rf "$temp"' EXIT
git clone --local --shared --no-checkout --single-branch --branch gh-pages . "$temp/repo"
.venv/bin/python src/publish.py "$temp/site"

cd "$temp/repo"
git --work-tree=../site add --all
if git diff --cached --quiet; then
	echo "nothing changed: not published"
	exit 0
fi
git --work-tree=../site commit --quiet -m "Published"
git push --quiet
cd - > /dev/null
git push origin gh-pages
