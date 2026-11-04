import ast
import csv
from pathlib import Path

import pytest

from mlite.desk.engine import DISCLAIMER, PaperDesk, format_trace
from mlite.desk.tape import Bar, load_bars, load_script


def test_disclaimer_is_the_required_notice():
    assert DISCLAIMER == "Paper trading demo, not financial advice."


def test_risk_vetoes_a_wide_bar_the_others_accept():
    bars = [
        Bar(0, 100, 100.2, 99.8, 100),
        Bar(1, 100, 100.2, 99.8, 100),
        Bar(2, 100, 130, 70, 100.4),
    ]
    desk = PaperDesk(bars)
    decision = desk.run()[-1]
    assert decision.action == "block"
    assert "range" in decision.reason
    assert _vote(decision, "trend").allow
    assert _vote(decision, "skeptic").allow
    assert not _vote(decision, "risk").allow
    assert desk.position is None


def test_risk_vetoes_an_oversized_sizer():
    bars = [
        Bar(0, 100, 100.3, 99.8, 100),
        Bar(1, 102, 102.2, 100.5, 101),
        Bar(2, 103, 103.2, 101.5, 102),
        Bar(3, 102.1, 102.5, 102.0, 102.4),
    ]
    desk = PaperDesk(bars)
    decision = desk.run()[-1]
    assert decision.action == "block"
    assert "size 3" in decision.reason
    assert _vote(decision, "trend").allow
    assert _vote(decision, "skeptic").allow
    assert desk.position is None


def test_loss_sets_cooldown_until_a_fresh_read():
    bars = [
        Bar(0, 100, 100.2, 99.8, 100),
        Bar(1, 100, 100.2, 99.8, 100),
        Bar(2, 100, 100.5, 99.9, 100.4),
        Bar(3, 100.4, 100.5, 98.8, 99.0),
        Bar(4, 99.2, 100.8, 99.1, 100.7),
    ]
    blocked = PaperDesk(bars).run()
    assert blocked[2].action == "enter"
    assert blocked[3].action == "exit"
    assert blocked[3].pnl is not None and blocked[3].pnl < 0
    assert blocked[4].action == "block"
    assert "cooldown" in blocked[4].reason
    assert _vote(blocked[4], "trend").allow
    assert _vote(blocked[4], "skeptic").allow

    desk = PaperDesk(bars)
    for index in range(4):
        desk.step(index)
    assert desk.cooldown is True
    desk.fresh_read(4)
    opened = desk.step(4)
    assert desk.cooldown is False
    assert opened.action == "enter"
    assert _vote(opened, "risk").allow


def test_more_bars_do_not_clear_cooldown():
    bars = [
        Bar(0, 100, 100.2, 99.8, 100),
        Bar(1, 100, 100.2, 99.8, 100),
        Bar(2, 100, 100.5, 99.9, 100.4),
        Bar(3, 100.4, 100.5, 98.8, 99.0),
        Bar(4, 99.2, 100.8, 99.1, 100.7),
        Bar(5, 100.7, 101.0, 100.6, 100.9),
    ]
    desk = PaperDesk(bars)
    decisions = desk.run()
    assert decisions[3].pnl is not None and decisions[3].pnl < 0
    assert desk.cooldown is True
    assert all(item.action != "enter" for item in decisions[4:])


def test_time_exit_closes_a_winner_without_cooldown():
    bars = [
        Bar(0, 100, 100.2, 99.8, 100),
        Bar(1, 100, 100.2, 99.8, 100),
        Bar(2, 100, 100.5, 99.9, 100.4),
        Bar(3, 100.4, 100.6, 100.3, 100.5),
        Bar(4, 100.5, 100.7, 100.4, 100.6),
        Bar(5, 100.6, 100.8, 100.5, 100.7),
        Bar(6, 100.7, 100.9, 100.6, 100.8),
    ]
    desk = PaperDesk(bars, max_hold=4)
    decisions = desk.run()
    assert [item.action for item in decisions[2:]] == [
        "enter",
        "hold",
        "hold",
        "hold",
        "exit",
    ]
    assert decisions[6].reason == "time exit"
    assert decisions[6].pnl is not None and decisions[6].pnl > 0
    assert desk.cooldown is False
    assert desk.position is None


def test_a_losing_time_exit_sets_cooldown():
    bars = [
        Bar(0, 100, 100.2, 99.8, 100),
        Bar(1, 100, 100.2, 99.8, 100),
        Bar(2, 100, 100.5, 99.9, 100.4),
        Bar(3, 100.4, 100.6, 100.3, 100.5),
        Bar(4, 100.5, 100.5, 90.0, 90.0),
    ]
    desk = PaperDesk(bars, max_hold=2)
    decisions = desk.run()
    assert decisions[4].reason == "time exit"
    assert decisions[4].pnl is not None and decisions[4].pnl < 0
    assert desk.cooldown is True


def test_empty_chip_stack_is_a_veto():
    bars = [
        Bar(0, 100, 100.2, 99.8, 100),
        Bar(1, 100, 100.2, 99.8, 100),
        Bar(2, 100, 100.5, 99.9, 100.4),
    ]
    desk = PaperDesk(bars, chips=0)
    decision = desk.run()[-1]
    assert decision.action == "block"
    assert "chips" in decision.reason
    assert desk.position is None


def test_bundled_tape_matches_its_notes(data_dir: Path):
    bars = load_bars(data_dir / "prices.csv")
    script = load_script(data_dir / "desk_script.json")
    desk = PaperDesk(bars)
    decisions = desk.run(fresh_before=list(script["fresh_before"]))
    by_bar = {item.bar: item for item in decisions}
    with (data_dir / "prices.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    trace = format_trace(desk, decisions)
    assert trace.startswith(DISCLAIMER)
    for row in rows:
        decision = by_bar[int(row["i"])]
        note = row["note"]
        if note == "warmup":
            assert decision.action == "flat", trace
        elif note == "skeptic blocks a chase":
            assert decision.action == "flat", trace
            assert not _vote(decision, "skeptic").allow
        elif note == "risk vetoes size":
            assert decision.action == "block" and "size" in decision.reason, trace
        elif note == "risk vetoes a wide range":
            assert decision.action == "block" and "range" in decision.reason, trace
        elif note == "trend stands down":
            assert decision.action == "flat", trace
            assert not _vote(decision, "trend").allow
        elif note == "entry":
            assert decision.action == "enter", trace
        elif note == "stop and cooldown":
            assert decision.action == "exit", trace
            assert decision.pnl is not None and decision.pnl < 0
        elif note == "cooldown blocks a valid signal":
            assert decision.action == "block" and "cooldown" in decision.reason, trace
            assert _vote(decision, "trend").allow
            assert _vote(decision, "skeptic").allow
        elif note == "entry after fresh read":
            assert decision.action == "enter", trace
        elif note == "hold":
            assert decision.action == "hold", trace
        elif note == "time exit":
            assert decision.reason == "time exit", trace
            assert decision.pnl is not None and decision.pnl > 0
        else:
            raise AssertionError(note)
    assert desk.position is None
    assert desk.cooldown is False
    assert desk.chips == pytest.approx(desk.starting_chips + 0.1)
    assert "No order leaves this process." in trace


def test_bundled_tape_stays_blocked_without_a_fresh_read(data_dir: Path):
    bars = load_bars(data_dir / "prices.csv")
    desk = PaperDesk(bars)
    decisions = desk.run()
    loss = next(item for item in decisions if item.pnl is not None and item.pnl < 0)
    assert desk.cooldown is True
    assert all(item.action != "enter" for item in decisions if item.bar > loss.bar)


def test_entries_require_a_risk_allow_and_never_overlap(data_dir: Path):
    bars = load_bars(data_dir / "prices.csv")
    script = load_script(data_dir / "desk_script.json")
    decisions = PaperDesk(bars).run(fresh_before=list(script["fresh_before"]))
    open_position = False
    for decision in decisions:
        if decision.action == "enter":
            assert not open_position
            assert _vote(decision, "risk").allow
            open_position = True
        elif decision.action == "exit":
            assert open_position
            open_position = False
    assert not open_position


def test_fresh_read_rejects_an_unknown_bar(data_dir: Path):
    bars = load_bars(data_dir / "prices.csv")
    with pytest.raises(ValueError):
        PaperDesk(bars).run(fresh_before=[99])


def test_desk_has_no_network_imports():
    banned = {"socket", "http", "urllib", "requests", "httpx", "aiohttp"}
    root = Path("mlite/desk")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "http://" not in text
        tree = ast.parse(text)
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            assert not (set(names) & banned)


def _vote(decision, role: str):
    return next(vote for vote in decision.votes if vote.role == role)
