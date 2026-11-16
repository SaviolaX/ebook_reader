#!/bin/bash
set -e
export MSYS_NO_PATHCONV=1   # stop Git Bash from mangling the paths below

rm -rf build dist
uv run python make_icon.py
uv run pyinstaller --noconfirm --windowed \
  --name EbooksReader \
  --icon src/ebooks_reader/resources/icon.ico \
  --paths src \
  --add-data "src/ebooks_reader/resources;ebooks_reader/resources" \
  run_app.py

echo
echo "Done: dist/EbooksReader/EbooksReader.exe"
