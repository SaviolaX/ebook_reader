#!/bin/bash
# Usage: bash release.sh 0.2.4
set -e
V="$1"
[ -z "$V" ] && { echo "Usage: bash release.sh <version>, e.g. 0.2.4"; exit 1; }
[ -n "$(git status --porcelain)" ] && { echo "Commit or stash your changes first."; exit 1; }

sed -i -E "s/__version__ = \"[^\"]*\"/__version__ = \"$V\"/" src/ebooks_reader/version.py
sed -i -E "0,/^version = \"[^\"]*\"/s//version = \"$V\"/" pyproject.toml

git add src/ebooks_reader/version.py pyproject.toml
git commit -m "chore: bump version to $V"
git tag "v$V"
git push origin main
git push origin "v$V"
echo "Released v$V. Watch: https://github.com/SaviolaX/ebook_reader/actions"
