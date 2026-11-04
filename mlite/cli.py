"""Command line for the demo. ``ask-m`` and ``python -m mlite`` share this."""

from __future__ import annotations

import argparse
import sys

from mlite.desk.engine import PaperDesk, format_trace
from mlite.desk.tape import load_bars, load_script
from mlite.gate.queue import Gate, GateError
from mlite.memory.ollama import Ollama
from mlite.memory.retrieve import ask, format_answer
from mlite.paths import data_dir, workspace_dir
from mlite.prove import prove
from mlite.registry.router import format_route, route

USAGE = """
ask-m: local sample memory, bot routing, a paper desk, and an approval gate.

  ask-m "when do we water the fern"
  ask-m --who "draft and revise the markdown note"
  ask-m desk run [--no-fresh-read]
  ask-m gate stage --title TITLE --body BODY
  ask-m gate list
  ask-m gate approve ID
  ask-m gate reject ID
  ask-m prove

Add --no-ollama to skip a local model even if one is installed.
Paper trading demo, not financial advice.
""".strip()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help", "help"}:
        print(USAGE)
        return 0
    if args[0] == "prove":
        if len(args) != 1:
            print(USAGE)
            return 2
        return prove()
    if args[0] == "--who":
        task = " ".join(args[1:]).strip()
        if not task:
            print('usage: ask-m --who "task"')
            return 2
        print(format_route(route(task, data_dir() / "registry.json")))
        return 0
    if args[0] == "desk":
        return _desk(args[1:])
    if args[0] == "gate":
        return _gate(args[1:])
    allow_model = True
    if "--no-ollama" in args:
        allow_model = False
        args = [arg for arg in args if arg != "--no-ollama"]
    if not args or args[0].startswith("-"):
        print(USAGE)
        return 2
    return _ask(args, allow_model)


def console_main() -> None:
    sys.exit(main())


def _ask(args: list[str], allow_model: bool) -> int:
    question = " ".join(args).strip()
    if not question:
        print(USAGE)
        return 2
    client = Ollama.from_env() if allow_model else None
    answer = ask(question, data_dir(), workspace_dir(), client=client)
    print(format_answer(answer))
    return 0


def _desk(args: list[str]) -> int:
    if not args or args[0] != "run" or any(arg not in {"run", "--no-fresh-read"} for arg in args):
        print("usage: ask-m desk run [--no-fresh-read]")
        return 2
    fresh = "--no-fresh-read" not in args
    root = data_dir()
    bars = load_bars(root / "prices.csv")
    script = load_script(root / "desk_script.json")
    before = list(script.get("fresh_before", [])) if fresh else []
    desk = PaperDesk(bars)
    decisions = desk.run(fresh_before=before)
    print(format_trace(desk, decisions))
    return 0


def _gate(args: list[str]) -> int:
    if not args:
        print("usage: ask-m gate stage|list|approve|reject")
        return 2
    gate = Gate(workspace_dir())
    action = args[0]
    if action == "list":
        pending = gate.pending()
        if not pending:
            print("queue empty")
            return 0
        for item in pending:
            print(f"{item.id}  pending  {item.title}")
        return 0
    if action == "stage":
        title, body = _stage_args(args[1:])
        if title is None or body is None:
            return 2
        item = gate.stage(title, body)
        print(f"staged {item.id}  pending")
        return 0
    if action in {"approve", "reject"}:
        if len(args) != 2:
            print(f"usage: ask-m gate {action} ID")
            return 2
        try:
            item = gate.approve(args[1]) if action == "approve" else gate.reject(args[1])
        except GateError as exc:
            print(exc)
            return 1
        print(f"{item.status} {item.id}")
        return 0
    print("usage: ask-m gate stage|list|approve|reject")
    return 2


def _stage_args(args: list[str]) -> tuple[str | None, str | None]:
    parser = argparse.ArgumentParser(prog="ask-m gate stage", add_help=False)
    parser.add_argument("--title")
    parser.add_argument("--body")
    try:
        parsed = parser.parse_args(args)
    except SystemExit:
        print("usage: ask-m gate stage --title TITLE --body BODY")
        return None, None
    if not parsed.title or not parsed.body:
        print("usage: ask-m gate stage --title TITLE --body BODY")
        return None, None
    return parsed.title, parsed.body
