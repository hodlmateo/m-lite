from mlite.cli import main
from mlite.desk.engine import DISCLAIMER


def test_help():
    assert main(["--help"]) == 0


def test_question_cites_a_note(capsys, monkeypatch):
    class Off:
        def enabled(self) -> bool:
            return False

    monkeypatch.setattr("mlite.cli.Ollama.from_env", lambda: Off())
    assert main(["when do we water the fern"]) == 0
    out = capsys.readouterr().out
    assert "even days" in out
    assert "notes/garden.md#fern" in out
    assert "Sources:" in out


def test_no_ollama_flag(capsys):
    assert main(["--no-ollama", "when do we water the fern"]) == 0
    assert "even days" in capsys.readouterr().out


def test_unknown_question(capsys):
    assert main(["--no-ollama", "cargo code for station northwind"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("I don't know.")
    assert "Sources:" in out


def test_who(capsys):
    assert main(["--who", "draft and revise the markdown note"]) == 0
    out = capsys.readouterr().out
    assert "owner: quill" in out
    assert "anti-jobs:" in out
    assert main(["--who", "compose a string quartet"]) == 0
    assert "owner: none" in capsys.readouterr().out


def test_desk_run_prints_the_notice(capsys):
    assert main(["desk", "run"]) == 0
    out = capsys.readouterr().out
    assert out.startswith(DISCLAIMER)
    assert "veto:" in out
    assert "cooldown" in out
    assert "time exit" in out
    assert "fresh read" in out


def test_desk_without_fresh_read_has_no_second_entry(capsys):
    assert main(["desk", "run", "--no-fresh-read"]) == 0
    out = capsys.readouterr().out
    assert "clears cooldown" not in out
    assert "bar  9  enter" not in out
    assert "cooldown on" in out


def test_gate_cli_roundtrip(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("MLITE_WORKSPACE", str(tmp_path))
    assert (
        main(
            [
                "gate",
                "stage",
                "--title",
                "Quartz sparrow",
                "--body",
                "The quartz sparrow sleeps in the sample drawer.",
            ]
        )
        == 0
    )
    staged = capsys.readouterr().out.strip()
    item_id = staged.split()[1]
    assert main(["gate", "list"]) == 0
    assert item_id in capsys.readouterr().out
    assert main(["--no-ollama", "where does the quartz sparrow sleep"]) == 0
    assert capsys.readouterr().out.startswith("I don't know.")
    assert main(["gate", "approve", item_id]) == 0
    assert "approved" in capsys.readouterr().out
    assert main(["--no-ollama", "where does the quartz sparrow sleep"]) == 0
    assert "sample drawer" in capsys.readouterr().out
    assert main(["gate", "approve", item_id]) == 1
