"""Four votes on one bar.

Trend proposes a long. Skeptic rejects a chase. Sizer names a size.
Risk may veto. A veto stops the entry even when the other three agree.
"""

from __future__ import annotations

from dataclasses import dataclass

from mlite.desk.tape import Bar

SMA_WINDOW = 3
CHASE_LIMIT = 0.035
RANGE_LIMIT = 0.08


@dataclass(frozen=True)
class Vote:
    role: str
    allow: bool
    reason: str
    size: int = 0


def vote_trend(bars: list[Bar], index: int) -> Vote:
    if index + 1 < SMA_WINDOW:
        return Vote("trend", False, f"need {SMA_WINDOW} closes")
    window = [bars[pos].close for pos in range(index - SMA_WINDOW + 1, index + 1)]
    average = sum(window) / len(window)
    bar = bars[index]
    if bar.close > average and bar.close >= bar.open:
        return Vote("trend", True, f"close {bar.close:.2f} is above the average")
    return Vote("trend", False, f"close {bar.close:.2f} is not a long")


def vote_skeptic(bars: list[Bar], index: int) -> Vote:
    bar = bars[index]
    chase = (bar.close - bar.open) / bar.open
    if chase > CHASE_LIMIT:
        return Vote("skeptic", False, f"chase {chase:.3f} is over the limit")
    return Vote("skeptic", True, "bar is not a chase")


def vote_sizer(bars: list[Bar], index: int) -> Vote:
    ups = 0
    for pos in range(max(1, index - 2), index + 1):
        if bars[pos].close > bars[pos - 1].close:
            ups += 1
    size = 1
    if ups >= 2:
        size += 1
    if ups >= 3:
        size += 1
    return Vote("sizer", True, f"{ups} rising closes, size {size}", size=size)


def vote_risk(
    bar: Bar,
    *,
    proposed_size: int,
    cooldown: bool,
    max_size: int,
    chips: float,
) -> Vote:
    if cooldown:
        return Vote("risk", False, "veto: cooldown until a fresh read", size=proposed_size)
    span = (bar.high - bar.low) / bar.close
    if span > RANGE_LIMIT:
        return Vote(
            "risk",
            False,
            f"veto: bar range {span:.2f} is over {RANGE_LIMIT:.2f}",
            size=proposed_size,
        )
    if proposed_size > max_size:
        return Vote(
            "risk",
            False,
            f"veto: size {proposed_size} is over max {max_size}",
            size=proposed_size,
        )
    cost = bar.close * proposed_size
    if cost > chips:
        return Vote("risk", False, "veto: not enough paper chips", size=proposed_size)
    return Vote("risk", True, "risk allows the entry", size=proposed_size)
