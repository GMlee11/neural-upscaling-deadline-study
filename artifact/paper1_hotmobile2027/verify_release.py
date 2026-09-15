"""Verify exact inventory, hygiene, and complete Paper 1 release hashes."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "FILES.txt"
MANIFEST = ROOT / "artifact/paper1_hotmobile2027/release_manifest.json"
SCANNER_SOURCE = "artifact/paper1_hotmobile2027/verify_release.py"
PROHIBITED_DIRS = {
    ".godot",
    ".pytest_cache",
    ".tmp",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "tmp",
}
PROHIBITED_SUFFIXES = {
    ".aux",
    ".bbl",
    ".blg",
    ".ipynb",
    ".log",
    ".onnx",
    ".out",
    ".pyc",
    ".pyo",
    ".rknn",
    ".toc",
}
TEXT_SUFFIXES = {
    ".bib",
    ".gd",
    ".gdshader",
    ".gitignore",
    ".json",
    ".jsonl",
    ".md",
    ".ps1",
    ".py",
    ".tex",
    ".txt",
    ".yaml",
    ".yml",
}
PRIVATE_PATTERNS = (
    ("Windows absolute path", re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")),
    ("UNC path", re.compile(r"\\\\[A-Za-z0-9._-]+[\\/]")),
    ("private IPv4 address", re.compile(r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b")),
    ("private home path", re.compile(r"/(?:home|Users)/[^/\s]+/")),
)


def sha256_file(path: Path) -> str:
    """Return a lowercase SHA-256 digest for one file."""

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def listed_paths() -> list[str]:
    """Load and validate the exact release allowlist."""

    rows = [row.strip() for row in INVENTORY.read_text(encoding="utf-8").splitlines()]
    if rows != sorted(set(rows)) or any(not row for row in rows):
        raise ValueError("FILES.txt must be sorted, unique, and nonempty")
    if "FILES.txt" not in rows:
        raise ValueError("FILES.txt must include itself")
    return rows


def actual_paths() -> list[str]:
    """Return artifact files, excluding only root Git metadata, without following links."""

    rows = []
    for directory, dirs, files in os.walk(ROOT, followlinks=False):
        parent = Path(directory)
        # A normal clone has a .git directory; a worktree has a .git file.
        # Neither is scientific evidence. Do not walk it or follow its links.
        if parent == ROOT:
            dirs[:] = [name for name in dirs if name != ".git"]
            files = [name for name in files if name != ".git"]
        for name in dirs + files:
            path = parent / name
            if path.is_symlink():
                raise ValueError(f"release contains a symlink: {path.relative_to(ROOT)}")
        rows.extend((parent / name).relative_to(ROOT).as_posix() for name in files)
    return sorted(rows)


def verify_inventory_and_hygiene() -> list[str]:
    """Reject missing/extra files, build state, binaries, and private paths."""

    listed = listed_paths()
    actual = actual_paths()
    if listed != actual:
        missing = sorted(set(listed) - set(actual))
        extra = sorted(set(actual) - set(listed))
        raise ValueError(f"inventory mismatch; missing={missing}, extra={extra}")

    for relative in actual:
        path = ROOT / relative
        if PROHIBITED_DIRS.intersection(path.relative_to(ROOT).parts):
            raise ValueError(f"prohibited directory in release: {relative}")
        suffixes = path.suffixes
        combined_suffix = "".join(suffixes[-2:]).lower() if len(suffixes) >= 2 else ""
        if path.suffix.lower() in PROHIBITED_SUFFIXES or combined_suffix == ".synctex.gz":
            raise ValueError(f"prohibited file extension in release: {relative}")

        # Regex source necessarily contains encoded path signatures. Its hash
        # and inventory are still checked; private-path scanning covers every
        # other reviewer-facing text file.
        if (
            relative != SCANNER_SOURCE
            and (path.suffix.lower() in TEXT_SUFFIXES or path.name == ".gitignore")
        ):
            text = path.read_text(encoding="utf-8")
            for label, pattern in PRIVATE_PATTERNS:
                if pattern.search(text):
                    raise ValueError(f"{label} in reviewer-facing file: {relative}")
    return listed


def verify_release_manifest(listed: list[str]) -> None:
    """Verify complete-release hashes and coverage."""

    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    self_path = str(payload["self_excluded"])
    expected = [path for path in listed if path != self_path]
    rows = payload["files"]
    declared = [str(row["path"]) for row in rows]
    if declared != expected:
        raise ValueError("complete-release manifest does not match FILES.txt coverage")
    for row in rows:
        path = ROOT / str(row["path"])
        if sha256_file(path) != str(row["sha256"]):
            raise ValueError(f"release hash mismatch: {row['path']}")


def main() -> int:
    """Run the non-mutating release gate."""

    listed = verify_inventory_and_hygiene()
    verify_release_manifest(listed)
    size = sum((ROOT / relative).stat().st_size for relative in listed)
    print(f"PAPER1_HOTMOBILE_RELEASE_HYGIENE_PASS files={len(listed)} bytes={size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
