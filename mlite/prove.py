"""One command that walks the demo and prints PASS or FAIL.

This is the prove-it-works path: memory cites or refuses, routing respects
jobs and the threshold, a staged note stays invisible until approve, and the
paper tape shows a veto, a cooldown, and a time exit.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from mlite.desk.engine import DISCLAIMER, PaperDesk
from mlite.desk.tape import load_bars, load_script
from mlite.gate.queue import Gate
from mlite.memory.retrieve import Answer, ask
from mlite.paths import data_dir
from mlite.registry.router import route


def prove(data: Path | None = None) -> int:
    data = data or data_dir()
    lines = [DISCLAIMER, ""]
    failed = 0

    def check(name: str, ok: bool, note: str = "") -> None:
        nonlocal failed
        if not ok:
            failed += 1
        lines.append(f"{'PASS' if ok else 'FAIL'}  {name}")
        if note:
            lines.append(f"      {note}")

    fern = ask("when do we water the fern", data, client=None)
    check(
        "memory cites the fern note",
        fern.known and "even days" in fern.text and _has(fern, "garden.md#fern"),
        fern.text,
    )
    miss = ask("what is the cargo code for station northwind", data, client=None)
    check(
        "memory refuses when the notes do not say",
        (not miss.known) and miss.text == "I don't know." and len(miss.hits) > 0,
        "I don't know.",
    )

    routes = [
        ("draft and revise the markdown note", "quill"),
        ("cite the source for the fern note", "archivist"),
        ("run the paper desk on the next synthetic bar", "ledger"),
        ("stage this import until a human approves the merge", "porter"),
        ("veto an oversized paper entry", "warden"),
    ]
    registry = data / "registry.json"
    for task, expected in routes:
        result = route(task, registry)
        check(f"route {expected}", result.owner == expected, result.owner or "none")
    none = route("compose a string quartet", registry)
    check("route returns no owner under the threshold", none.owner is None, "none")

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        gate = Gate(workspace)
        item = gate.stage(
            "Quartz sparrow",
            "The quartz sparrow sleeps in the sample drawer.",
        )
        before = ask("where does the quartz sparrow sleep", data, workspace, client=None)
        gate.approve(item.id)
        after = ask("where does the quartz sparrow sleep", data, workspace, client=None)
        check(
            "staged import stays invisible until approve",
            (not before.known) and after.known,
        )

    bars = load_bars(data / "prices.csv")
    script = load_script(data / "desk_script.json")
    desk = PaperDesk(bars)
    decisions = desk.run(fresh_before=list(script["fresh_before"]))
    check(
        "desk risk veto",
        any(item.action == "block" and item.reason.startswith("veto:") for item in decisions),
    )
    check(
        "desk cooldown after a loss",
        any(item.pnl is not None and item.pnl < 0 for item in decisions)
        and any("cooldown" in item.reason for item in decisions),
    )
    check(
        "desk time exit",
        any(item.reason == "time exit" and item.pnl is not None and item.pnl > 0 for item in decisions),
    )
    lines.append("")
    lines.append("prove-it-works: " + ("all checks passed" if failed == 0 else f"{failed} failed"))
    print("\n".join(lines))
    return 0 if failed == 0 else 1


def _has(answer: Answer, needle: str) -> bool:
    return any(needle in hit.source for hit in answer.hits)
