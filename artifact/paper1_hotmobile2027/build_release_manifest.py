"""Create the complete Paper 1 release SHA-256 manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "FILES.txt"
OUTPUT = ROOT / "artifact/paper1_hotmobile2027/release_manifest.json"
SELF = OUTPUT.relative_to(ROOT).as_posix()


def sha256_file(path: Path) -> str:
    """Return a lowercase SHA-256 digest without loading a file at once."""

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inventory_paths() -> list[str]:
    """Return the sorted exact release allowlist."""

    rows = [row.strip() for row in INVENTORY.read_text(encoding="utf-8").splitlines()]
    if not rows or any(not row for row in rows):
        raise ValueError("FILES.txt must contain one nonempty path per line")
    if rows != sorted(set(rows)):
        raise ValueError("FILES.txt must be sorted and contain no duplicates")
    if SELF not in rows:
        raise ValueError(f"FILES.txt must include {SELF}")
    return rows


def build_manifest() -> dict[str, object]:
    """Hash the complete allowlist except this self-referential manifest."""

    rows = []
    total_size = 0
    for relative in inventory_paths():
        if relative == SELF:
            continue
        path = ROOT / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        size = path.stat().st_size
        total_size += size
        rows.append(
            {"path": relative, "sha256": sha256_file(path), "size_bytes": size}
        )
    return {
        "schema_version": 1,
        "artifact": "paper1_hotmobile2027_v1_complete_release",
        "coverage": "every FILES.txt entry except this self-referential manifest",
        "self_excluded": SELF,
        "hashed_file_count": len(rows),
        "hashed_size_bytes": total_size,
        "files": rows,
    }


def main() -> int:
    """Write the complete release manifest for maintainer freeze operations."""

    payload = build_manifest()
    OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"PAPER1_HOTMOBILE_RELEASE_MANIFEST files={payload['hashed_file_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
