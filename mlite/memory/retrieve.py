"""Lexical lookup that quotes a note or says it does not know.

A hit is accepted when the question shares enough terms with the chunk.
The spoken answer is a sentence copied from that chunk. Embeddings may
reorder accepted chunks. A model phrase is kept only when every content
word already appears in the cited text. A miss never calls the model, so
a generative reply cannot invent a fact the notes do not contain.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

from mlite.memory.corpus import Chunk, load_chunks
from mlite.memory.ollama import Ollama
from mlite.text import lexemes, words

TOP_K = 3
COVERAGE = 0.34


@dataclass(frozen=True)
class Hit:
    source: str
    title: str
    text: str
    origin: str
    score: float
    accepted: bool
    used: bool


@dataclass(frozen=True)
class Answer:
    text: str
    known: bool
    hits: tuple[Hit, ...]


def ask(
    question: str,
    data_dir: Path,
    workspace: Path | None = None,
    client: Ollama | None = None,
) -> Answer:
    return answer_from(question, load_chunks(data_dir, workspace), client=client)


def answer_from(
    question: str,
    chunks: list[Chunk],
    client: Ollama | None = None,
) -> Answer:
    query = lexemes(question)
    if not query or not chunks:
        return Answer("I don't know.", False, ())

    idf = _idf(chunks)
    ranked = sorted(
        (_score(query, chunk, idf) for chunk in chunks),
        key=lambda item: (-item[0], item[1].source),
    )
    accepted_ids = {
        chunk.source
        for score, chunk in ranked
        if _accepts(query, chunk)
    }
    # Score is for ordering. Acceptance is the term gate above.
    preliminary = [
        Hit(
            source=chunk.source,
            title=chunk.title,
            text=chunk.text,
            origin=chunk.origin,
            score=score,
            accepted=chunk.source in accepted_ids,
            used=False,
        )
        for score, chunk in ranked
    ]
    ordered = _rerank(question, preliminary, client)
    known = any(hit.accepted for hit in ordered)
    if not known:
        return Answer("I don't know.", False, tuple(ordered[:TOP_K]))

    chosen = next(hit for hit in ordered if hit.accepted)
    sentence = best_sentence(question, chosen.text)
    phrased = _phrase(question, chosen, sentence, client)
    text = phrased if phrased is not None else sentence
    hits = []
    for hit in ordered[:TOP_K]:
        hits.append(replace(hit, used=hit.source == chosen.source))
    if chosen.source not in {hit.source for hit in hits}:
        hits.append(replace(chosen, used=True))
    return Answer(text, True, tuple(hits))


def best_sentence(question: str, text: str) -> str:
    flat = " ".join(text.split())
    parts = [part for part in re.split(r"(?<=[.!?])\s+", flat) if part]
    if not parts:
        return flat
    query = lexemes(question)

    def rank(sentence: str) -> tuple[int, int]:
        overlap = len(query & lexemes(sentence))
        return (overlap, -parts.index(sentence))

    return max(parts, key=rank)


def format_answer(answer: Answer) -> str:
    lines: list[str] = []
    if answer.known:
        lines.append(answer.text)
        lines.append("")
        lines.append("From the local sample notes. Nothing was added.")
    else:
        lines.append("I don't know.")
        lines.append("")
        lines.append(
            "Closest notes are under the cutoff. They are cited so the miss is visible."
        )
    lines.append("")
    lines.append("Sources:")
    if not answer.hits:
        lines.append("(none)")
    for index, hit in enumerate(answer.hits, start=1):
        if hit.used:
            state = "used"
        elif hit.accepted:
            state = "matched"
        else:
            state = "below cutoff"
        lines.append(
            f"{index}. {hit.source} — {hit.title} — {hit.origin} — "
            f"score {hit.score:.2f} — {state}"
        )
        lines.append(f"   {_snippet(hit.text)}")
    return "\n".join(lines)


def _accepts(query: set[str], chunk: Chunk) -> bool:
    matched = len(query & lexemes(chunk.title + " " + chunk.text))
    size = len(query)
    if size <= 0 or matched <= 0:
        return False
    if size == 1:
        return True
    return matched >= 2 and (matched / size) >= COVERAGE


def _score(query: set[str], chunk: Chunk, idf: dict[str, float]) -> tuple[float, Chunk]:
    counts = Counter(lexemes(chunk.title + " " + chunk.text))
    # Title terms count a bit more so a heading can win a tie.
    title_terms = lexemes(chunk.title)
    total = 0.0
    for term in query:
        if term not in counts:
            continue
        weight = 1.5 if term in title_terms else 1.0
        total += weight * (1.0 + math.log(counts[term])) * idf.get(term, 1.0)
    return total, chunk


def _idf(chunks: list[Chunk]) -> dict[str, float]:
    df: Counter[str] = Counter()
    for chunk in chunks:
        df.update(lexemes(chunk.title + " " + chunk.text))
    total = len(chunks)
    return {
        term: math.log((total + 1) / (count + 1)) + 1.0 for term, count in df.items()
    }


def _rerank(question: str, hits: list[Hit], client: Ollama | None) -> list[Hit]:
    if client is None or not client.enabled() or not hits:
        return hits
    query_vector = client.embed(question)
    if not query_vector:
        return hits
    rescored: list[Hit] = []
    for hit in hits:
        vector = client.embed(hit.title + "\n" + hit.text)
        if not vector:
            return hits
        rescored.append(replace(hit, score=hit.score + _cosine(query_vector, vector)))
    rescored.sort(key=lambda hit: (-hit.score, hit.source))
    return rescored


def _phrase(
    question: str,
    chosen: Hit,
    sentence: str,
    client: Ollama | None,
) -> str | None:
    if client is None or not client.enabled():
        return None
    evidence = chosen.title + "\n" + chosen.text
    raw = client.answer(question, evidence)
    if raw is None:
        return None
    if len(raw) > 300:
        return None
    if not _grounded(raw, evidence, question):
        return None
    return raw


def _grounded(answer: str, evidence: str, question: str) -> bool:
    allowed = lexemes(evidence) | lexemes(question)
    used = set(words(answer))
    # Stems of the answer must be allowed too.
    used |= lexemes(answer)
    if not used:
        return False
    return used <= allowed


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def _snippet(text: str, limit: int = 160) -> str:
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 3].rstrip() + "..."
