from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from PySide6.QtCore import QThread, Signal

from ..version import GITHUB_REPO, __version__


def parse_version(text: str) -> tuple[int, ...]:
    """'v1.2.3' -> (1, 2, 3). Anything after a '-' (pre-release) is ignored."""
    return tuple(int(n) for n in re.findall(r"\d+", text.split("-")[0]))


def check_latest() -> dict:
    """Ask GitHub for the latest release. Returns a dict with a 'status' key:
    'update', 'latest' or 'error'."""
    if "OWNER" in GITHUB_REPO:
        return {"status": "error", "message": "The update source is not configured yet."}
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "EbooksReader-updater",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"status": "error", "message": "No releases have been published yet."}
        return {"status": "error", "message": f"GitHub answered with error {e.code}."}
    except Exception as e:
        return {"status": "error", "message": f"Could not reach GitHub: {e}"}

    tag = str(data.get("tag_name", ""))
    try:
        newer = parse_version(tag) > parse_version(__version__)
    except Exception:
        return {"status": "error", "message": f"Unexpected version tag: {tag!r}"}
    if newer:
        return {
            "status": "update",
            "version": tag.lstrip("vV"),
            "url": data.get("html_url", ""),
            "notes": str(data.get("body") or "")[:600],
        }
    return {"status": "latest", "version": __version__}


class UpdateChecker(QThread):
    """Runs check_latest() in the background so the window never freezes."""

    result = Signal(dict)

    def run(self) -> None:
        self.result.emit(check_latest())
