#!/usr/bin/env bash
# make publish: generated/publish/ (make build) committed to the gh-pages branch as it is, replacing all the branch
# held, and pushed to origin. The commit is made in a temporary clone, with generated/publish/ as its work tree.
set -e

site="$PWD/generated/publish"
if [ ! -f "$site/index.html" ]; then
	echo "no $site/index.html: run make build first"
	exit 1
fi

git fetch origin gh-pages:gh-pages
temp=$(mktemp -d)
trap 'chmod -R u+w "$temp"; rm -rf "$temp"' EXIT
git clone --local --shared --no-checkout --single-branch --branch gh-pages . "$temp/repo"

cd "$temp/repo"
git --work-tree="$site" add --all
if git diff --cached --quiet; then
	echo "nothing changed: not published"
	exit 0
fi
git --work-tree="$site" commit --quiet -m "Published"
git push --quiet
cd - > /dev/null
git push origin gh-pages
