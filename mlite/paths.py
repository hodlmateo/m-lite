"""Locate the checkout. Sample data lives next to this package, not in site-packages."""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "data" / "registry.json").is_file():
            return candidate
    raise FileNotFoundError(
        "data/registry.json not found. Run m-lite from a checkout of the repo."
    )


def data_dir() -> Path:
    return repo_root() / "data"


def workspace_dir() -> Path:
    """Local queue and approved imports. Gitignored. Created on first use.

    ``MLITE_WORKSPACE`` overrides the directory so a demo can run without
    writing into the checkout.
    """
    override = os.environ.get("MLITE_WORKSPACE", "").strip()
    if override:
        return Path(override)
    return repo_root() / "var"
