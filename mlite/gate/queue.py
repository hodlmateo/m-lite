"""Stage an import, then merge it only on ``approve``.

``stage`` writes the queue. ``approve`` is the only method that copies a
note into the workspace corpus (markdown plus sqlite). ``reject`` drops it.
There is no path that approves itself.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class GateError(ValueError):
    pass


@dataclass(frozen=True)
class Item:
    id: str
    title: str
    body: str
    status: str


class Gate:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.staging = workspace / "staging"
        self.notes = workspace / "notes"
        self.database = workspace / "approved.sqlite"
        self.queue_path = self.staging / "queue.json"

    def stage(self, title: str, body: str) -> Item:
        title = _clean(title, "title")
        body = _clean(body, "body")
        self.staging.mkdir(parents=True, exist_ok=True)
        queue = self._read()
        item_id = _mint(title, body, len(queue))
        while any(row["id"] == item_id for row in queue):
            item_id = _mint(title, body, len(queue) + len(item_id))
        row = {
            "id": item_id,
            "title": title,
            "body": body,
            "status": "pending",
            "created": _now(),
        }
        queue.append(row)
        self._write(queue)
        (self.staging / f"{item_id}.md").write_text(_markdown(title, body), encoding="utf-8")
        return Item(item_id, title, body, "pending")

    def pending(self) -> list[Item]:
        return [_item(row) for row in self._read() if row["status"] == "pending"]

    def approve(self, item_id: str) -> Item:
        return self._decide(item_id, "approved")

    def reject(self, item_id: str) -> Item:
        return self._decide(item_id, "rejected")

    def get(self, item_id: str) -> Item:
        for row in self._read():
            if row["id"] == item_id:
                return _item(row)
        raise GateError(f"unknown id {item_id}")

    def _decide(self, item_id: str, status: str) -> Item:
        queue = self._read()
        for row in queue:
            if row["id"] != item_id:
                continue
            if row["status"] != "pending":
                raise GateError(f"{item_id} is {row['status']}, not pending")
            row["status"] = status
            row["decided_by"] = "human"
            row["decided_at"] = _now()
            self._write(queue)
            if status == "approved":
                self._merge(row)
            return _item(row)
        raise GateError(f"unknown id {item_id}")

    def _merge(self, row: dict) -> None:
        self.notes.mkdir(parents=True, exist_ok=True)
        (self.notes / f"{row['id']}.md").write_text(
            _markdown(row["title"], row["body"]),
            encoding="utf-8",
        )
        self.workspace.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database)
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS notes (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT ''
                )
                """
            )
            # Bind the staged text. Do not interpolate it into the statement.
            connection.execute(
                "INSERT INTO notes (id, title, body, tags) VALUES (?, ?, ?, ?)",
                (row["id"], row["title"], row["body"], "approved"),
            )
            connection.commit()
        finally:
            connection.close()

    def _read(self) -> list[dict]:
        if not self.queue_path.is_file():
            return []
        data = json.loads(self.queue_path.read_text(encoding="utf-8"))
        items = data.get("items", [])
        if not isinstance(items, list):
            raise GateError("queue items must be a list")
        return items

    def _write(self, items: list[dict]) -> None:
        self.staging.mkdir(parents=True, exist_ok=True)
        payload = {"items": items}
        self.queue_path.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )


def _markdown(title: str, body: str) -> str:
    return f"# Approved import\n\n## {title}\n\n{body}\n"


def _clean(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise GateError(f"{label} must be a string")
    cleaned = value.strip()
    if not cleaned:
        raise GateError(f"{label} is empty")
    if "\n" in cleaned and label == "title":
        raise GateError("title must be a single line")
    return cleaned


def _mint(title: str, body: str, series: int) -> str:
    digest = hashlib.sha256(f"{series}\n{title}\n{body}".encode("utf-8")).hexdigest()
    return digest[:8]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _item(row: dict) -> Item:
    return Item(row["id"], row["title"], row["body"], row["status"])
