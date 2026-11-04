"""Load the sample corpus.

Two stores, both local:

- Markdown files under ``notes/`` (and approved files under the workspace).
- SQLite rows. The bundled seed is ``sample_notes.sql``, executed in memory.
  Approved imports live in ``workspace/approved.sqlite``.

Staging is not a store. Nothing under ``staging/`` is readable here.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Chunk:
    source: str
    title: str
    text: str
    origin: str


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "note"


def load_chunks(data_dir: Path, workspace: Path | None = None) -> list[Chunk]:
    chunks: list[Chunk] = []
    notes = data_dir / "notes"
    if notes.is_dir():
        for path in sorted(notes.glob("*.md")):
            chunks.extend(parse_markdown(path, bucket="notes"))
    seed = data_dir / "sample_notes.sql"
    if seed.is_file():
        chunks.extend(load_sql_script(seed))
    if workspace is not None:
        approved = workspace / "notes"
        if approved.is_dir():
            for path in sorted(approved.glob("*.md")):
                chunks.extend(parse_markdown(path, bucket="approved"))
        database = workspace / "approved.sqlite"
        if database.is_file():
            chunks.extend(load_sqlite(database))
    return dedupe(chunks)


def parse_markdown(path: Path, bucket: str) -> list[Chunk]:
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    chunks: list[Chunk] = []
    for section in re.split(r"(?m)^(?=## )", raw):
        section = section.strip()
        if not section:
            continue
        lines = section.splitlines()
        header = lines[0]
        if header.startswith("#"):
            title = header.lstrip("#").strip()
            body = "\n".join(lines[1:]).strip()
        else:
            title = path.stem
            body = section
        if not body:
            continue
        chunks.append(
            Chunk(
                source=f"{bucket}/{path.name}#{slugify(title)}",
                title=title,
                text=body,
                origin="markdown",
            )
        )
    return chunks


def load_sql_script(path: Path) -> list[Chunk]:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(path.read_text(encoding="utf-8"))
        return _rows(connection)
    finally:
        connection.close()


def load_sqlite(path: Path) -> list[Chunk]:
    # Read-only. Imports become visible here only after the gate has merged them.
    uri = "file:" + path.resolve().as_posix() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        return _rows(connection)
    except sqlite3.OperationalError:
        return []
    finally:
        connection.close()


def _rows(connection: sqlite3.Connection) -> list[Chunk]:
    cursor = connection.execute(
        "SELECT id, title, body FROM notes ORDER BY id"
    )
    return [
        Chunk(source=f"sqlite:{note_id}", title=title, text=body, origin="sqlite")
        for note_id, title, body in cursor
        if body and str(body).strip()
    ]


def dedupe(chunks: list[Chunk]) -> list[Chunk]:
    """Same text written to markdown and sqlite is cited once, with both sources."""
    groups: dict[tuple[str, str], list[Chunk]] = {}
    for chunk in chunks:
        key = (chunk.title.strip().lower(), " ".join(chunk.text.split()))
        groups.setdefault(key, []).append(chunk)
    merged: list[Chunk] = []
    for group in groups.values():
        first = group[0]
        source = " | ".join(chunk.source for chunk in group)
        origins = "+".join(sorted({chunk.origin for chunk in group}))
        merged.append(
            Chunk(source=source, title=first.title, text=first.text, origin=origins)
        )
    return merged
