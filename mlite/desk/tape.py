"""Read the bundled synthetic tape. This module only reads a local file."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Bar:
    i: int
    open: float
    high: float
    low: float
    close: float


def load_bars(path: Path) -> list[Bar]:
    bars: list[Bar] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            bar = Bar(
                i=int(row["i"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
            )
            _check(bar)
            bars.append(bar)
    if [bar.i for bar in bars] != list(range(len(bars))):
        raise ValueError("bar index must start at 0 and increase by 1")
    if not bars:
        raise ValueError("price file is empty")
    return bars


def load_script(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("desk script must be an object")
    return data


def _check(bar: Bar) -> None:
    if bar.high < max(bar.open, bar.close, bar.low):
        raise ValueError(f"bar {bar.i} high is below another price")
    if bar.low > min(bar.open, bar.close, bar.high):
        raise ValueError(f"bar {bar.i} low is above another price")
    if bar.close <= 0 or bar.open <= 0:
        raise ValueError(f"bar {bar.i} price must be positive")
