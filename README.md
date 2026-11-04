# m-lite

**Paper trading demo, not financial advice.**

m-lite is a small public demo of a local-first personal agent stack. The real stack is private. This repo is invented sample data plus the patterns around it, so a developer or a coding agent can read the code and copy the shape.

The notes, the bots, and the prices are fiction. The program runs offline. Runtime dependencies are the Python standard library.

## Quickstart

```bash
python -m mlite prove
python -m pytest
python -m mlite "when do we water the fern"
python -m mlite --who "draft and revise the markdown note"
python -m mlite desk run
```

`python -m pytest` needs pytest (`pip install -e ".[dev]"`). The demo commands do not.

Installing the package exposes the same program as `ask-m`:

```bash
pip install -e .
ask-m prove
```

## The ideas

### One job per bot

`data/registry.json` lists five fictional bots. Each `job` is a single line.

| Bot | Job |
| --- | --- |
| quill | Draft and revise markdown notes |
| archivist | Answer from local notes and cite the source |
| ledger | Run the paper desk on synthetic prices |
| porter | Stage imports until a human approves the merge |
| warden | Veto paper entries that break risk, cooldown, or size rules |

A task is scored against that one job, plus a few hints. The best score at or above the threshold (0.45) and above zero owns the task. Otherwise the owner is none.

### Anti-jobs

An anti-job is work the bot must refuse even when the task also sounds like its job. If the task shares two or more content words with any anti-job, that bot is out of the running: two points come off the score, which a normal match cannot earn back.

"Draft and revise the markdown note and place paper trades" does not go to quill. Placing paper trades is one of quill's anti-jobs, so ledger gets it. The arithmetic is in `mlite/registry/router.py`.

### Local memory with citations

`ask` reads markdown under `data/notes/` and the SQLite seed in `data/sample_notes.sql` (loaded in memory at startup). Approved imports, if you have any, are read from the local workspace. The staging queue is not readable.

Retrieval is lexical. It does not need a model. A chunk is accepted when it shares two or more terms and those terms cover at least a third of the question, or when the question is a single term that hits. The reply is a sentence copied from the winning chunk. Every reply lists its top sources. A miss starts with `I don't know.` and still lists the closest notes, marked below the cutoff, so the refusal is visible.

Try the SQLite note with:

```bash
python -m mlite "where does the fictional pantry keep flake salt"
```

That answer is cited as `sqlite:pantry-salt`.

Optional local model: if `OLLAMA_HOST` is set, or an `ollama` program is on PATH, embeddings may reorder the notes and a generate call may rephrase the sentence. A rephrase is kept only when every content word is already in the cited note. Embeddings cannot turn a miss into a hit, and a miss never asks the model to phrase an answer. `--no-ollama` skips the model. With the variable unset and no `ollama` program, nothing is contacted. `MLITE_EMBED_MODEL` and `MLITE_ANSWER_MODEL` override the model names.

### Approval gates

Imports land in a staging queue. `approve` is the only step that merges one into memory: a markdown file and a SQLite row. The staged text is bound as a SQL parameter. `reject` drops the item. Nothing in the gate approves itself.

```bash
python -m mlite gate stage --title "Quartz sparrow" --body "The quartz sparrow sleeps in the sample drawer."
python -m mlite gate list
python -m mlite "where does the quartz sparrow sleep"
python -m mlite gate approve ID
```

The question returns `I don't know.` until the approve step. The queue lives in `var/`, which is gitignored.

### Paper-only trading

**Paper trading demo, not financial advice.**

The desk reads `data/prices.csv`, a synthetic tape for the fictional symbol PIP. Four roles vote on each bar:

- **trend** proposes a long when the close is above a short average
- **skeptic** rejects a bar that chases
- **sizer** names a size from how many recent closes rose
- **risk** can veto

A veto stops the entry even when trend and skeptic both say yes. On this tape, risk vetoes a size of 3 (max is 2) and a bar whose high-low range is too wide.

After any losing close, new entries stay blocked until `fresh_read`. Walking more bars does not clear the cooldown. The bundled script records that read before bar 9, which is why a second entry happens. `python -m mlite desk run --no-fresh-read` leaves the later signal blocked.

A position still open after 4 bars is closed by the time exit. A losing time exit starts the cooldown too. The book is an in-memory chip ledger. The only market input is the CSV. No order leaves the process. There is no exchange client and no keys.

### Prove it works

`python -m mlite prove` asks a question the notes can answer, asks one they cannot, routes five tasks, checks that a staged note is invisible until approve, and checks that the tape shows a veto, a cooldown, and a time exit. It prints `PASS` or `FAIL`.

`tests/` covers the same pieces one at a time: retrieval and citations, the registry and the threshold, each desk rule, the gate, the command line, and a scan that the checkout stays free of contact addresses and similar markers.

## Sample output

A question the notes answer:

```text
$ python -m mlite "when do we water the fern"
Water the fern on even days, half a cup, and skip if the soil is still dark.

From the local sample notes. Nothing was added.

Sources:
1. notes/garden.md#fern — Fern — markdown — score 7.18 — used
   Water the fern on even days, half a cup, and skip if the soil is still dark. The pot is green.
2. notes/desk-rules.md#cooldown — Cooldown — markdown — score 0.00 — below cutoff
   After any losing close, the desk blocks new entries until a fresh read is recorded.
3. notes/desk-rules.md#paper-desk-rules — Paper desk rules — markdown — score 0.00 — below cutoff
   Rules for the fictional PIP book. PIP prices are synthetic. The desk never sends an order.
```

A question they do not answer:

```text
$ python -m mlite "what is the cargo code for station northwind"
I don't know.

Closest notes are under the cutoff. They are cited so the miss is visible.

Sources:
1. notes/desk-rules.md#cooldown — Cooldown — markdown — score 0.00 — below cutoff
   After any losing close, the desk blocks new entries until a fresh read is recorded.
2. notes/desk-rules.md#paper-desk-rules — Paper desk rules — markdown — score 0.00 — below cutoff
   Rules for the fictional PIP book. PIP prices are synthetic. The desk never sends an order.
3. notes/desk-rules.md#time-exit — Time exit — markdown — score 0.00 — below cutoff
   A position held longer than the max bar count is closed, even when the other roles still like it.
```

Routing:

```text
$ python -m mlite --who "draft and revise the markdown note"
owner: quill
score: 1.10
threshold: 0.45
job: draft and revise markdown notes in the local sample memory
anti-jobs:
- place paper trades
- merge staged imports
- cite memory sources
ranked:
- quill 1.10
- archivist 0.12
- porter 0.12
- ledger 0.00
- warden 0.00

$ python -m mlite --who "compose a string quartet"
owner: none
score: 0.00
threshold: 0.45
No bot cleared the threshold.
ranked:
- archivist 0.00
- ledger 0.00
- porter 0.00
- quill 0.00
- warden 0.00
```

The paper tape, with the fresh read before bar 9:

```text
$ python -m mlite desk run
Paper trading demo, not financial advice.
Synthetic prices for the fictional symbol PIP. No order leaves this process.

bar  0  flat   need 3 closes  [trend=no skeptic=yes sizer=1 risk=yes]
bar  1  flat   need 3 closes  [trend=no skeptic=yes sizer=1 risk=yes]
bar  2  flat   chase 0.041 is over the limit  [trend=yes skeptic=no sizer=2 risk=yes]
bar  3  block  veto: size 3 is over max 2  [trend=yes skeptic=yes sizer=3 risk=no]
bar  4  block  veto: bar range 0.20 is over 0.08  [trend=yes skeptic=yes sizer=2 risk=no]
bar  5  flat   close 101.00 is not a long  [trend=no skeptic=yes sizer=1 risk=yes]
bar  6  enter  long 1 @ 101.80  [trend=yes skeptic=yes sizer=1 risk=yes]
bar  7  exit   stop below entry  pnl -1.30  cooldown on  [trend=no skeptic=yes sizer=1 risk=yes]
bar  8  block  veto: cooldown until a fresh read  [trend=yes skeptic=yes sizer=2 risk=no]
bar  9  read   fresh read clears cooldown before this bar
bar  9  enter  long 2 @ 101.90  [trend=yes skeptic=yes sizer=2 risk=yes]
bar 10  hold   held 1  [trend=yes skeptic=yes sizer=3 risk=no]
bar 11  hold   held 2  [trend=yes skeptic=yes sizer=3 risk=no]
bar 12  hold   held 3  [trend=yes skeptic=yes sizer=3 risk=no]
bar 13  exit   time exit  pnl 1.40  cooldown off  [trend=yes skeptic=yes sizer=3 risk=no]

paper chips 10000.00 -> 10000.10
```

## Where the patterns live

- One job and anti-jobs: `data/registry.json`, `mlite/registry/router.py`
- Memory, citations, and the refusal: `mlite/memory/corpus.py`, `mlite/memory/retrieve.py`
- Optional local model: `mlite/memory/ollama.py`
- Paper desk: `mlite/desk/roles.py`, `mlite/desk/engine.py`, `data/prices.csv`, `data/desk_script.json`
- Approval gate: `mlite/gate/queue.py`
- The tour: `mlite/prove.py`
- Commands: `mlite/cli.py`

## Left out on purpose

Sample files are invented. They do not contain real names, real places, email addresses, network addresses, or keys. The desk has no exchange client and no network order path. A model is optional and cannot override `I don't know.`

## License

MIT. See `LICENSE`.
