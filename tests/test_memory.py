from pathlib import Path

from mlite.memory.corpus import Chunk, load_chunks
from mlite.memory.ollama import Ollama, loopback_base
from mlite.memory.retrieve import answer_from, ask, format_answer


def test_markdown_note_is_quoted_and_cited(data_dir: Path):
    result = ask("when do we water the fern", data_dir, client=None)
    assert result.known is True
    assert result.text == (
        "Water the fern on even days, half a cup, and skip if the soil is still dark."
    )
    assert "green" not in result.text
    used = [hit for hit in result.hits if hit.used]
    assert len(used) == 1
    assert used[0].source == "notes/garden.md#fern"
    assert used[0].origin == "markdown"
    text = format_answer(result)
    assert text.startswith(result.text)
    assert "Sources:" in text
    assert "notes/garden.md#fern" in text
    assert "used" in text


def test_sqlite_note_is_quoted_and_cited(data_dir: Path):
    result = ask("where does the fictional pantry keep flake salt", data_dir, client=None)
    assert result.known is True
    assert "blue tin" in result.text
    assert "label" not in result.text
    used = next(hit for hit in result.hits if hit.used)
    assert used.source == "sqlite:pantry-salt"
    assert used.origin == "sqlite"


def test_unknown_question_does_not_invent_and_still_cites(data_dir: Path):
    result = ask("what is the cargo code for station northwind", data_dir, client=None)
    assert result.known is False
    assert result.text == "I don't know."
    assert result.hits
    assert all(not hit.accepted and not hit.used for hit in result.hits)
    text = format_answer(result)
    assert text.startswith("I don't know.")
    assert "under the cutoff" in text
    assert "Sources:" in text
    assert "below cutoff" in text
    assert "(none)" not in text


def test_one_shared_word_is_not_enough(data_dir: Path):
    result = ask("what is the fern cargo code", data_dir, client=None)
    assert result.known is False
    assert result.text == "I don't know."
    assert "even days" not in result.text
    assert any("garden.md#fern" in hit.source for hit in result.hits)
    text = format_answer(result)
    assert "below cutoff" in text
    assert "garden.md#fern" in text


def test_desk_rule_is_retrieved(data_dir: Path):
    result = ask("what happens after a losing close", data_dir, client=None)
    assert result.known is True
    assert "fresh read" in result.text
    assert any("desk-rules.md#cooldown" in hit.source for hit in result.hits if hit.used)


def test_empty_corpus_cites_nothing():
    result = answer_from("where is the fern", [], client=None)
    assert result.known is False
    assert result.hits == ()
    assert "(none)" in format_answer(result)


def test_staging_directory_is_not_memory(data_dir: Path, tmp_path: Path):
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "pending.md").write_text(
        "# Approved import\n\n## Violet compass\n\n"
        "The violet compass points at the sample drawer.\n",
        encoding="utf-8",
    )
    result = ask("where does the violet compass point", data_dir, tmp_path, client=None)
    assert result.known is False


def test_sources_are_relative(data_dir: Path):
    for chunk in load_chunks(data_dir):
        assert not chunk.source.startswith("/")
        assert ".." not in chunk.source


def test_embeddings_can_choose_among_accepted_notes():
    chunks = [
        Chunk("notes/a.md#note", "Note", "alpha zebra fern water", "markdown"),
        Chunk("notes/b.md#note", "Note", "beta zebra fern water", "markdown"),
    ]
    lexical = answer_from("zebra fern water", chunks, client=None)
    assert "alpha" in lexical.text

    class Fake:
        def enabled(self) -> bool:
            return True

        def embed(self, text: str) -> list[float]:
            if "beta zebra" in text:
                return [1.0, 0.0]
            if "alpha zebra" in text:
                return [0.0, 1.0]
            return [1.0, 0.0]

        def answer(self, question: str, evidence: str) -> None:
            return None

    reranked = answer_from("zebra fern water", chunks, client=Fake())
    assert "beta" in reranked.text
    assert reranked.known is True


def test_ungrounded_model_text_is_dropped(data_dir: Path):
    class Bad:
        def enabled(self) -> bool:
            return True

        def embed(self, text: str) -> None:
            return None

        def answer(self, question: str, evidence: str) -> str:
            return "unicorn milk is the best drink"

    result = ask("when do we water the fern", data_dir, client=Bad())
    assert "unicorn" not in result.text
    assert "even days" in result.text
    assert any("garden.md#fern" in hit.source for hit in result.hits if hit.used)


def test_grounded_model_text_is_kept(data_dir: Path):
    class Good:
        def enabled(self) -> bool:
            return True

        def embed(self, text: str) -> None:
            return None

        def answer(self, question: str, evidence: str) -> str:
            return "Water the fern on even days."

    result = ask("when do we water the fern", data_dir, client=Good())
    assert result.text == "Water the fern on even days."
    assert any(hit.used and "garden.md#fern" in hit.source for hit in result.hits)


def test_model_is_not_asked_to_phrase_a_miss(data_dir: Path):
    class Boom:
        def enabled(self) -> bool:
            return True

        def embed(self, text: str) -> list[float]:
            return [1.0, 0.0]

        def answer(self, question: str, evidence: str) -> str:
            raise AssertionError("model should not phrase a miss")

    result = ask("what is the cargo code for station northwind", data_dir, client=Boom())
    assert result.text == "I don't know."
    assert result.known is False


def test_from_env_stays_off_without_a_daemon(monkeypatch):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.setattr("mlite.memory.ollama.shutil.which", lambda name: None)
    client = Ollama.from_env()
    assert client.host == ""
    assert client.embed("fern") is None
    assert client.answer("when", "the fern") is None


def test_ollama_source_has_no_address_literal():
    import re

    text = Path("mlite/memory/ollama.py").read_text(encoding="utf-8")
    assert re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text) is None


def test_down_daemon_falls_back():
    client = Ollama(host=loopback_base(port=9), timeout=0.3)
    assert client.embed("fern") is None
    assert client.answer("when", "the fern") is None
