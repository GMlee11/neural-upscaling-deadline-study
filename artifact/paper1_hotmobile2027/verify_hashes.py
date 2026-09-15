"""Verify the frozen Paper 1 output manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[2]


def sha256_file(path: Path) -> str:
    """Return a lowercase SHA-256 digest for one file."""

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_manifest(manifest_path: Path) -> int:
    """Check every declared file and print a stable success marker."""

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    for row in payload["files"]:
        path = ROOT / str(row["path"])
        if not path.is_file():
            raise FileNotFoundError(path)
        actual = sha256_file(path)
        if actual != str(row["sha256"]):
            raise ValueError(
                f"hash mismatch for {row['path']}: expected {row['sha256']}, got {actual}"
            )
    print("PAPER1_HOTMOBILE_ARTIFACT_HASHES_PASS")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the hash-verification command line."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Verify the selected manifest and return a shell-friendly status."""

    args = build_parser().parse_args(argv)
    return verify_manifest(args.manifest)


if __name__ == "__main__":
    raise SystemExit(main())

