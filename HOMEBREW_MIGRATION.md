# Homebrew migration: Intel (/usr/local) -> Apple Silicon (/opt/homebrew)

Reason: `uname -m` is arm64 but Homebrew was installed at /usr/local, the Intel
prefix, and ran under Rosetta. Homebrew treats that as a Tier 3 configuration
and ships almost no bottles for it on macOS 26, so every install tried to
compile from source and failed on the Command Line Tools version check. That
is what blocked `brew install tesseract tesseract-lang`.

## What was installed before (recorded 2026-09-22)

Top-level packages (the only ones deliberately installed; the other 62 were
dependencies):

    cmake  gcc  mingw-w64  node  poppler

Casks:

    ngrok

Not affected by the migration:
  - /usr/local/mysql, /usr/local/mysql-9.7.0-macos15-arm64  (MySQL 9.7, native arm64)
  - /usr/local/com.cisco.packettracer                        (Cisco Packet Tracer)
  - the sahitya-setu venv, which uses python.org Python 3.13, not brew Python

## Restore after installing the arm64 Homebrew

    eval "$(/opt/homebrew/bin/brew shellenv)"
    brew install cmake gcc mingw-w64 node poppler tesseract
    brew install --cask ngrok

Gujarati OCR data (skip the 1.2 GB `tesseract-lang` formula, which is what
pulled in json-c and triggered the original build failure):

    curl -L -o "$(brew --prefix)/share/tessdata/guj.traineddata" \
      https://github.com/tesseract-ocr/tessdata_best/raw/main/guj.traineddata
    tesseract --list-langs | grep guj

## Update (2026-09-22): Tesseract installed without Homebrew

The Homebrew migration was NOT performed. Tesseract 5.5.3 (native arm64) was
installed from conda-forge into ~/.local/tesseract instead, which needs no
admin rights and does not touch /usr/local. See the README for the commands.

Also found while installing: the startup disk was at 100% (504 MB free), which
is what made the first install attempt fail with a write error. 6.2 GB was
reclaimed by deleting three regenerable caches (Spotify, Homebrew, vscode-cpptools).
The disk is still at 97% — worth a proper cleanup.

The Intel Homebrew at /usr/local is still in place and still cannot build
formulas. The migration above remains the right long-term fix.
