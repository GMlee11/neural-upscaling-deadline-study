"""SQLite storage helpers for reproducible dataset and experiment records."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping


DEFAULT_DATABASE_PATH = Path("data/research.sqlite3")
DEFAULT_SCHEMA_PATH = Path("database/schema.sql")


# Pandas and NumPy scalars expose item(), while pathlib values are naturally
# represented as strings. Supporting both keeps the database API lightweight.
def json_default(value: object) -> object:
    """Convert common scientific scalar/path objects into JSON-native values."""
    item = getattr(value, "item", None)
    if callable(item):
        return item()
    if isinstance(value, Path):
        return value.as_posix()
    raise TypeError(f"value is not JSON serializable: {type(value).__name__}")


# JSON deliberately has no NaN or infinity values. Metrics can legitimately
# produce positive infinity for a perfect PSNR match, so preserve that meaning
# with explicit strings rather than writing nonstandard JSON tokens.
def normalize_json_value(value: object) -> object:
    """Recursively convert records into strict, portable JSON values."""
    converted = json_default(value) if not isinstance(
        value, (dict, list, tuple, str, int, float, bool, type(None))
    ) else value
    if isinstance(converted, float) and not math.isfinite(converted):
        if math.isnan(converted):
            return "nan"
        return "inf" if converted > 0 else "-inf"
    if isinstance(converted, Mapping):
        return {str(key): normalize_json_value(item) for key, item in converted.items()}
    if isinstance(converted, (list, tuple)):
        return [normalize_json_value(item) for item in converted]
    return converted


# Store timestamps in a stable, timezone-explicit representation so records
# created on different machines remain directly comparable.
def utc_now() -> str:
    """Return the current UTC time in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


# Open connections with foreign-key enforcement enabled on every call; SQLite
# does not retain this setting globally between processes.
def connect(database_path: Path) -> sqlite3.Connection:
    """Open a row-addressable SQLite connection to the research database."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    # Independent experiment workers may finish an epoch at nearly the same
    # moment. Waiting for the short writer transaction preserves both records
    # instead of turning harmless scheduling overlap into a failed long run.
    connection = sqlite3.connect(database_path, timeout=60.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 60000")
    return connection


# Apply the checked-in schema idempotently. Keeping DDL in a standalone SQL file
# makes the storage contract inspectable without reading Python implementation.
def initialize_database(
    database_path: Path = DEFAULT_DATABASE_PATH,
    schema_path: Path = DEFAULT_SCHEMA_PATH,
) -> None:
    """Create or upgrade the research database using the checked-in schema."""
    if not schema_path.is_file():
        raise FileNotFoundError(f"database schema does not exist: {schema_path}")
    with closing(connect(database_path)) as connection:
        connection.executescript(schema_path.read_text(encoding="utf-8"))


# Hash source artifacts before import so a database can prove exactly which
# flat-file snapshot supplied a legacy record set during migration.
def sha256_file(path: Path) -> str:
    """Calculate a source file's SHA-256 digest without loading it all at once."""
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# Replacing a complete record set in one transaction prevents dashboards and
# report builders from observing a half-written experiment.
def replace_record_set(
    database_path: Path,
    name: str,
    records: Iterable[Mapping[str, object]],
    *,
    source_path: str | None = None,
    source_sha256: str | None = None,
) -> int:
    """Atomically replace one named collection of ordered research records."""
    normalized_records = [dict(record) for record in records]
    if not name.strip():
        raise ValueError("record-set name must not be empty")
    initialize_database(database_path)
    with closing(connect(database_path)) as connection:
        with connection:
            # Delete children explicitly before replacing the parent key. This
            # remains correct even when a database was created by an older
            # client that did not enable SQLite foreign-key cascades.
            connection.execute(
                "DELETE FROM records WHERE record_set_name = ?", (name,)
            )
            connection.execute("DELETE FROM record_sets WHERE name = ?", (name,))
            connection.execute(
                """
                INSERT INTO record_sets(name, source_path, source_sha256, row_count, updated_at_utc)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name, source_path, source_sha256, len(normalized_records), utc_now()),
            )
            connection.executemany(
                """
                INSERT INTO records(record_set_name, row_index, payload_json)
                VALUES (?, ?, ?)
                """,
                [
                    (
                        name,
                        index,
                        json.dumps(
                            normalize_json_value(record),
                            separators=(",", ":"),
                            allow_nan=False,
                            default=json_default,
                        ),
                    )
                    for index, record in enumerate(normalized_records)
                ],
            )
    return len(normalized_records)


# Consumers receive ordinary dictionaries, preserving the simple record shape
# used throughout the existing evaluation and plotting code.
def read_record_set(database_path: Path, name: str) -> list[dict[str, object]]:
    """Read one record set in its original deterministic row order."""
    if not database_path.is_file():
        raise FileNotFoundError(f"research database does not exist: {database_path}")
    with closing(connect(database_path)) as connection:
        rows = connection.execute(
            "SELECT payload_json FROM records WHERE record_set_name = ? ORDER BY row_index",
            (name,),
        ).fetchall()
    return [json.loads(row["payload_json"]) for row in rows]


# Producers use this check before expensive work when replacement was not
# explicitly requested. It gives SQL outputs the same accidental-overwrite
# protection previously provided by checking whether a CSV file existed.
def record_set_exists(database_path: Path, name: str) -> bool:
    """Return whether a named record set is present in the database."""
    if not database_path.is_file():
        return False
    with closing(connect(database_path)) as connection:
        row = connection.execute(
            "SELECT 1 FROM record_sets WHERE name = ?",
            (name,),
        ).fetchone()
    return row is not None


# Screening experiments can intentionally retain compact scene/summary rows
# while dropping bulky frame-level intermediates. Keep deletion transactional
# and explicit instead of allowing callers to manipulate schema tables ad hoc.
def delete_record_set(database_path: Path, name: str) -> bool:
    """Delete one complete record set and return whether it existed."""

    if not database_path.is_file():
        return False
    with closing(connect(database_path)) as connection:
        with connection:
            row = connection.execute(
                "SELECT 1 FROM record_sets WHERE name = ?", (name,)
            ).fetchone()
            if row is None:
                return False
            connection.execute("DELETE FROM records WHERE record_set_name = ?", (name,))
            connection.execute("DELETE FROM record_sets WHERE name = ?", (name,))
    return True


# Centralizing replacement protection keeps every command's SQL behavior
# consistent and avoids each producer open-coding its own existence query.
def publish_record_set(
    database_path: Path,
    name: str,
    records: Iterable[Mapping[str, object]],
    *,
    overwrite: bool = False,
    source_path: str | None = None,
) -> int:
    """Publish records atomically while protecting existing results by default."""
    if record_set_exists(database_path, name) and not overwrite:
        raise FileExistsError(
            f"database record set already exists: {name}; use --overwrite"
        )
    return replace_record_set(
        database_path,
        name,
        records,
        source_path=source_path,
    )


# Project facts hold small stable values used in prose and generated LaTeX,
# such as parameter count and dataset size, without inventing one-row CSV files.
def upsert_project_facts(
    database_path: Path,
    facts: Iterable[tuple[str, object, str | None, str]],
) -> None:
    """Insert or update scalar project facts with their units and provenance."""
    initialize_database(database_path)
    timestamp = utc_now()
    with closing(connect(database_path)) as connection:
        with connection:
            connection.executemany(
                """
                INSERT INTO project_facts(key, value, unit, source, updated_at_utc)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    unit = excluded.unit,
                    source = excluded.source,
                    updated_at_utc = excluded.updated_at_utc
                """,
                [(key, str(value), unit, source, timestamp) for key, value, unit, source in facts],
            )
