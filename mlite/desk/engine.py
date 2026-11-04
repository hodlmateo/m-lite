"""Paper ledger for the fictional PIP tape.

Orders stay inside this process. The only market input is the bundled CSV.
A losing close sets cooldown. Further bars do not clear it; ``fresh_read``
does. A position open for ``max_hold`` bars is closed by the time exit.
"""

from __future__ import annotations

from dataclasses import dataclass

from mlite.desk.roles import Vote, vote_risk, vote_sizer, vote_skeptic, vote_trend
from mlite.desk.tape import Bar

DISCLAIMER = "Paper trading demo, not financial advice."


@dataclass(frozen=True)
class Position:
    entry_i: int
    entry_price: float
    size: int


@dataclass(frozen=True)
class Decision:
    bar: int
    action: str
    reason: str
    votes: tuple[Vote, ...]
    price: float
    size: int
    pnl: float | None
    chips: float


class PaperDesk:
    def __init__(
        self,
        bars: list[Bar],
        *,
        max_hold: int = 4,
        max_size: int = 2,
        chips: float = 10_000.0,
    ) -> None:
        if max_hold < 1:
            raise ValueError("max_hold must be at least 1")
        if max_size < 1:
            raise ValueError("max_size must be at least 1")
        self.bars = bars
        self.max_hold = max_hold
        self.max_size = max_size
        self.chips = float(chips)
        self.starting_chips = float(chips)
        self.position: Position | None = None
        self.cooldown = False
        self.reads: list[int] = []

    def fresh_read(self, bar_index: int) -> None:
        """Clear cooldown. This is an explicit read, not a new price."""
        if bar_index < 0:
            raise ValueError("bar_index must be >= 0")
        self.cooldown = False
        self.reads.append(bar_index)

    def step(self, index: int) -> Decision:
        bar = self.bars[index]
        trend = vote_trend(self.bars, index)
        skeptic = vote_skeptic(self.bars, index)
        sizer = vote_sizer(self.bars, index)
        risk = vote_risk(
            bar,
            proposed_size=sizer.size,
            cooldown=self.cooldown,
            max_size=self.max_size,
            chips=self.chips,
        )
        votes = (trend, skeptic, sizer, risk)
        if self.position is not None:
            held = index - self.position.entry_i
            if held >= self.max_hold:
                return self._close(index, "time exit", votes)
            if bar.close < self.position.entry_price:
                return self._close(index, "stop below entry", votes)
            return self._decision(
                index, "hold", f"held {held}", votes, size=self.position.size
            )
        if not trend.allow:
            return self._decision(index, "flat", trend.reason, votes)
        if not skeptic.allow:
            return self._decision(index, "flat", skeptic.reason, votes)
        if sizer.size < 1:
            return self._decision(index, "flat", "sizer returned no size", votes)
        if not risk.allow:
            return self._decision(index, "block", risk.reason, votes, size=sizer.size)
        return self._open(index, sizer.size, votes)

    def run(self, fresh_before: list[int] | tuple[int, ...] = ()) -> list[Decision]:
        unknown = [
            index for index in fresh_before if index < 0 or index >= len(self.bars)
        ]
        if unknown:
            raise ValueError(f"fresh read bar out of range: {unknown}")
        pending = set(fresh_before)
        decisions: list[Decision] = []
        for index in range(len(self.bars)):
            if index in pending:
                self.fresh_read(index)
            decisions.append(self.step(index))
        return decisions

    def _open(self, index: int, size: int, votes: tuple[Vote, ...]) -> Decision:
        bar = self.bars[index]
        self.chips -= bar.close * size
        self.position = Position(entry_i=index, entry_price=bar.close, size=size)
        return self._decision(index, "enter", "long", votes, size=size)

    def _close(self, index: int, reason: str, votes: tuple[Vote, ...]) -> Decision:
        bar = self.bars[index]
        position = self.position
        assert position is not None
        pnl = (bar.close - position.entry_price) * position.size
        self.chips += bar.close * position.size
        self.position = None
        if pnl < 0:
            self.cooldown = True
        return self._decision(
            index, "exit", reason, votes, size=position.size, pnl=pnl
        )

    def _decision(
        self,
        index: int,
        action: str,
        reason: str,
        votes: tuple[Vote, ...],
        *,
        size: int = 0,
        pnl: float | None = None,
    ) -> Decision:
        bar = self.bars[index]
        return Decision(
            bar=index,
            action=action,
            reason=reason,
            votes=votes,
            price=bar.close,
            size=size,
            pnl=pnl,
            chips=self.chips,
        )


def format_trace(desk: PaperDesk, decisions: list[Decision]) -> str:
    lines = [
        DISCLAIMER,
        "Synthetic prices for the fictional symbol PIP. No order leaves this process.",
        "",
    ]
    reads = set(desk.reads)
    for decision in decisions:
        if decision.bar in reads:
            lines.append(
                f"bar {decision.bar:>2}  read   fresh read clears cooldown before this bar"
            )
        lines.append(
            f"bar {decision.bar:>2}  {decision.action:<5}  "
            f"{_reason(decision)}  [{_flags(decision.votes)}]"
        )
    lines.append("")
    lines.append(f"paper chips {desk.starting_chips:.2f} -> {desk.chips:.2f}")
    return "\n".join(lines)


def _reason(decision: Decision) -> str:
    if decision.action == "enter":
        return f"long {decision.size} @ {decision.price:.2f}"
    if decision.action == "exit" and decision.pnl is not None:
        cooldown = "on" if decision.pnl < 0 else "off"
        return f"{decision.reason}  pnl {decision.pnl:.2f}  cooldown {cooldown}"
    return decision.reason


def _flags(votes: tuple[Vote, ...]) -> str:
    parts: list[str] = []
    for vote in votes:
        if vote.role == "sizer":
            parts.append(f"sizer={vote.size}")
        else:
            parts.append(f"{vote.role}={'yes' if vote.allow else 'no'}")
    return " ".join(parts)
