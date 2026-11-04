import json
from pathlib import Path

import pytest

from mlite.registry.router import RegistryError, format_route, load_registry, route


def test_each_bot_has_one_job_and_anti_jobs(data_dir: Path):
    bots, threshold = load_registry(data_dir / "registry.json")
    assert threshold == 0.45
    assert {bot.id for bot in bots} == {"quill", "archivist", "ledger", "porter", "warden"}
    for bot in bots:
        assert isinstance(bot.job, str)
        assert "\n" not in bot.job
        assert bot.anti_jobs
        assert all(isinstance(item, str) and item.strip() for item in bot.anti_jobs)


@pytest.mark.parametrize(
    ("task", "owner"),
    [
        ("draft and revise the markdown note", "quill"),
        ("cite the source for the fern note", "archivist"),
        ("run the paper desk on the next synthetic bar", "ledger"),
        ("stage this import until a human approves the merge", "porter"),
        ("veto an oversized paper entry", "warden"),
    ],
)
def test_tasks_route_to_the_owner(data_dir: Path, task: str, owner: str):
    result = route(task, data_dir / "registry.json")
    assert result.owner == owner
    assert result.score >= result.threshold
    text = format_route(result)
    assert f"owner: {owner}" in text
    assert "anti-jobs:" in text
    assert "job:" in text


def test_unrelated_task_has_no_owner(data_dir: Path):
    result = route("compose a string quartet", data_dir / "registry.json")
    assert result.owner is None
    assert result.score < result.threshold or result.score <= 0
    text = format_route(result)
    assert "owner: none" in text
    assert "No bot cleared the threshold." in text
    assert "job:" not in text
    assert "ranked:" in text


def test_empty_task_has_no_owner(data_dir: Path):
    result = route("???", data_dir / "registry.json")
    assert result.owner is None


def test_anti_job_removes_the_bot(data_dir: Path):
    registry = data_dir / "registry.json"
    plain = route("draft and revise the markdown note", registry)
    mixed = route(
        "draft and revise the markdown note and place paper trades",
        registry,
    )
    plain_scores = {item.id: item.score for item in plain.ranked}
    mixed_scores = {item.id: item.score for item in mixed.ranked}
    assert plain.owner == "quill"
    assert mixed.owner != "quill"
    assert mixed.owner == "ledger"
    assert mixed_scores["quill"] < 0
    assert mixed_scores["quill"] < plain_scores["quill"]


def test_threshold_can_leave_a_task_unowned(data_dir: Path, tmp_path: Path):
    raw = json.loads((data_dir / "registry.json").read_text(encoding="utf-8"))
    raw["threshold"] = 5
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    result = route("draft and revise the markdown note", path)
    assert result.owner is None
    assert result.ranked[0].id == "quill"
    text = format_route(result)
    assert "closest: quill" in text
    assert "No bot cleared the threshold." in text


def test_tie_prefers_the_lower_id(tmp_path: Path):
    raw = {
        "threshold": 0.1,
        "bots": [
            {
                "id": "bravo",
                "job": "paint the sample fence",
                "anti_jobs": ["bake bread"],
                "hints": [],
            },
            {
                "id": "alpha",
                "job": "paint the sample fence",
                "anti_jobs": ["bake bread"],
                "hints": [],
            },
        ],
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    result = route("paint the sample fence", path)
    assert result.owner == "alpha"
    assert result.ranked[0].score == result.ranked[1].score


def test_a_list_of_jobs_is_rejected(tmp_path: Path):
    raw = {
        "threshold": 0.45,
        "bots": [
            {
                "id": "quill",
                "job": ["draft notes", "place trades"],
                "anti_jobs": ["bake bread"],
                "hints": [],
            }
        ],
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RegistryError):
        load_registry(path)


def test_missing_anti_jobs_is_rejected(tmp_path: Path):
    raw = {
        "threshold": 0.45,
        "bots": [{"id": "quill", "job": "draft markdown notes", "hints": []}],
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RegistryError):
        load_registry(path)
