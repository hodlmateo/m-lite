"""Route a task to the single bot whose job fits.

score = shared job terms / job terms
      + 0.20 per hint whose terms all appear in the task (capped at 0.60)

If any anti-job shares two or more terms with the task, that bot is out:
two points are subtracted, which a normal job match cannot earn back.

The owner is the best score at or above ``threshold`` and above zero.
Otherwise the owner is none.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from mlite.text import lexemes

HINT_WEIGHT = 0.20
HINT_CAP = 0.60
ANTI_PENALTY = 2.0
ANTI_MIN_SHARED = 2


class RegistryError(ValueError):
    pass


@dataclass(frozen=True)
class Bot:
    id: str
    job: str
    anti_jobs: tuple[str, ...]
    hints: tuple[str, ...]


@dataclass(frozen=True)
class BotScore:
    id: str
    score: float
    job: str
    anti_jobs: tuple[str, ...]


@dataclass(frozen=True)
class Route:
    owner: str | None
    score: float
    threshold: float
    job: str | None
    anti_jobs: tuple[str, ...]
    ranked: tuple[BotScore, ...]


def route(task: str, registry_path: Path) -> Route:
    bots, threshold = load_registry(registry_path)
    task_terms = lexemes(task)
    ranked = tuple(
        sorted(
            (score_bot(task_terms, bot) for bot in bots),
            key=lambda item: (-item.score, item.id),
        )
    )
    best = ranked[0]
    owner: BotScore | None = best
    if best.score < threshold or best.score <= 0:
        owner = None
    chosen = owner or best
    return Route(
        owner=None if owner is None else owner.id,
        score=chosen.score,
        threshold=threshold,
        job=chosen.job,
        anti_jobs=chosen.anti_jobs,
        ranked=ranked,
    )


def score_bot(task_terms: set[str], bot: Bot) -> BotScore:
    job_terms = lexemes(bot.job)
    overlap = len(task_terms & job_terms)
    job_score = overlap / len(job_terms)
    hint_hits = 0
    for hint in bot.hints:
        hint_terms = lexemes(hint)
        if hint_terms and hint_terms <= task_terms:
            hint_hits += 1
    hint_score = min(HINT_CAP, HINT_WEIGHT * hint_hits)
    disqualified = False
    for anti in bot.anti_jobs:
        shared = len(task_terms & lexemes(anti))
        if shared >= ANTI_MIN_SHARED:
            disqualified = True
            break
    score = job_score + hint_score
    if disqualified:
        score -= ANTI_PENALTY
    return BotScore(
        id=bot.id,
        score=score,
        job=bot.job,
        anti_jobs=bot.anti_jobs,
    )


def load_registry(path: Path) -> tuple[tuple[Bot, ...], float]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RegistryError(f"registry is not valid json: {path}") from exc
    if not isinstance(data, dict):
        raise RegistryError("registry must be an object")
    threshold = data.get("threshold")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise RegistryError("threshold must be a number")
    raw_bots = data.get("bots")
    if not isinstance(raw_bots, list) or not raw_bots:
        raise RegistryError("bots must be a non-empty list")
    bots: list[Bot] = []
    seen: set[str] = set()
    for raw in raw_bots:
        bots.append(_bot(raw, seen))
    return tuple(bots), float(threshold)


def format_route(result: Route) -> str:
    lines = [
        f"owner: {result.owner or 'none'}",
        f"score: {result.score:.2f}",
        f"threshold: {result.threshold:.2f}",
    ]
    if result.owner is None:
        lines.append("No bot cleared the threshold.")
        if result.score > 0 and result.ranked:
            lines.append(f"closest: {result.ranked[0].id}")
    # A zero score has no closest owner worth describing.
    if result.job and (result.owner is not None or result.score > 0):
        lines.append(f"job: {result.job}")
        if result.anti_jobs:
            lines.append("anti-jobs:")
            for anti in result.anti_jobs:
                lines.append(f"- {anti}")
    lines.append("ranked:")
    for item in result.ranked:
        lines.append(f"- {item.id} {item.score:.2f}")
    return "\n".join(lines)


def _bot(raw: object, seen: set[str]) -> Bot:
    if not isinstance(raw, dict):
        raise RegistryError("each bot must be an object")
    missing = {"id", "job", "anti_jobs", "hints"} - set(raw)
    if missing:
        raise RegistryError(f"bot is missing {sorted(missing)}")
    bot_id = raw["id"]
    job = raw["job"]
    anti_jobs = raw["anti_jobs"]
    hints = raw["hints"]
    if not isinstance(bot_id, str) or not bot_id.strip():
        raise RegistryError("bot id must be a string")
    if bot_id in seen:
        raise RegistryError(f"duplicate bot id {bot_id}")
    seen.add(bot_id)
    if not isinstance(job, str) or "\n" in job or not job.strip():
        raise RegistryError(f"{bot_id} job must be a single line")
    if not lexemes(job):
        raise RegistryError(f"{bot_id} job has no content words")
    if not isinstance(anti_jobs, list) or not anti_jobs:
        raise RegistryError(f"{bot_id} needs at least one anti-job")
    if not all(isinstance(item, str) and item.strip() for item in anti_jobs):
        raise RegistryError(f"{bot_id} anti-jobs must be strings")
    if not isinstance(hints, list) or not all(isinstance(item, str) for item in hints):
        raise RegistryError(f"{bot_id} hints must be a list of strings")
    return Bot(
        id=bot_id,
        job=job.strip(),
        anti_jobs=tuple(item.strip() for item in anti_jobs),
        hints=tuple(item.strip() for item in hints if item.strip()),
    )
