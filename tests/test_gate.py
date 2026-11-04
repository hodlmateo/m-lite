import sqlite3
from pathlib import Path

import pytest

from mlite.gate.queue import Gate, GateError
from mlite.memory.retrieve import ask


def test_stage_does_not_merge(data_dir: Path, tmp_path: Path):
    gate = Gate(tmp_path)
    item = gate.stage("Quartz sparrow", "The quartz sparrow sleeps in the sample drawer.")
    assert item.status == "pending"
    assert (tmp_path / "staging" / f"{item.id}.md").is_file()
    assert not (tmp_path / "notes" / f"{item.id}.md").exists()
    assert [pending.id for pending in gate.pending()] == [item.id]
    result = ask(
        "where does the quartz sparrow sleep",
        data_dir,
        tmp_path,
        client=None,
    )
    assert result.known is False


def test_approve_merges_markdown_and_sqlite(data_dir: Path, tmp_path: Path):
    gate = Gate(tmp_path)
    body = "The quartz sparrow sleeps in the sample drawer. The sparrow's drawer is small."
    item = gate.stage("Quartz sparrow", body)
    approved = gate.approve(item.id)
    assert approved.status == "approved"
    assert gate.pending() == []
    note = (tmp_path / "notes" / f"{item.id}.md").read_text(encoding="utf-8")
    assert "sparrow's drawer" in note
    connection = sqlite3.connect(tmp_path / "approved.sqlite")
    try:
        row = connection.execute(
            "SELECT title, body FROM notes WHERE id = ?",
            (item.id,),
        ).fetchone()
    finally:
        connection.close()
    assert row[0] == "Quartz sparrow"
    assert "sparrow's drawer" in row[1]
    result = ask("where does the quartz sparrow sleep", data_dir, tmp_path, client=None)
    assert result.known is True
    assert "sample drawer" in result.text
    used = next(hit for hit in result.hits if hit.used)
    assert used.source.startswith("approved/")
    assert f"sqlite:{item.id}" in used.source


def test_reject_never_lands_in_memory(data_dir: Path, tmp_path: Path):
    gate = Gate(tmp_path)
    item = gate.stage("Quartz sparrow", "The quartz sparrow sleeps in the sample drawer.")
    rejected = gate.reject(item.id)
    assert rejected.status == "rejected"
    assert not (tmp_path / "notes" / f"{item.id}.md").exists()
    assert not (tmp_path / "approved.sqlite").exists()
    result = ask("where does the quartz sparrow sleep", data_dir, tmp_path, client=None)
    assert result.known is False


def test_approve_is_explicit_and_single_use(tmp_path: Path):
    gate = Gate(tmp_path)
    item = gate.stage("Quartz sparrow", "The quartz sparrow sleeps in the sample drawer.")
    gate.approve(item.id)
    with pytest.raises(GateError):
        gate.approve(item.id)
    with pytest.raises(GateError):
        gate.reject(item.id)


def test_rejected_item_cannot_be_approved(tmp_path: Path):
    gate = Gate(tmp_path)
    item = gate.stage("Quartz sparrow", "The quartz sparrow sleeps in the sample drawer.")
    gate.reject(item.id)
    with pytest.raises(GateError):
        gate.approve(item.id)


def test_unknown_id_and_empty_title(tmp_path: Path):
    gate = Gate(tmp_path)
    with pytest.raises(GateError):
        gate.approve("missing")
    with pytest.raises(GateError):
        gate.stage("  ", "a body")
    with pytest.raises(GateError):
        gate.stage("Title", "  ")
