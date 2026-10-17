# Auric R1: a weak model as a translator, not a reasoner

Granite 4.2 8B scores 0.0% macro exact match on these items one-shot. This system
scores **0.739 at 1x, 0.806 at 3x, 0.861 at 10x** (macro exact match, visible set,
3 live runs each) with the same model, by giving it the one job it can do:
translate each note line into a small formal fact. Everything that needs
reasoning (search, counting solutions, finding the contradiction) is exact code.

```
./run data/items.json --budget 1x --out answers.json
python3 data/score.py data/visible_key.json answers.json
```

The write-up (the "two pages") is [WRITEUP.md](WRITEUP.md).

## Setup

- Python 3.12 (tested on 3.12.15). Standard library only; `requirements.txt`
  pins nothing because nothing is imported from outside the stdlib.
- Put the endpoint credentials in `.env` at the repo root (same keys as the
  provided `.env`: `OPENROUTER_API_KEY`, and the base URL if given). `.env` is gitignored.
- Every call: `ibm-granite/granite-4.2-8b`, `temperature=1.0`, `top_p=0.95`,
  `reasoning: {enabled: false}`, header `X-Item-Id: <item id>`
  (`src/auric/client.py`). The per-item cap counts every HTTP attempt,
  retries included, so the proxy can never see more than the budget.

## Entry point

```
./run <items.json> --budget <1x|3x|10x> --out <answers.json>
      [--ablate prefilter,vote,prior_pick] [--enable adaptive]
      [--workers 8] [--trace traces.jsonl] [--log raw_replies.jsonl]
```

`1x` makes exactly one call per item; `3x`/`10x` make exactly 3/10 by default
(adaptive early stopping exists but is off; see the write-up for why).

## How it works

![pipeline](docs/how-it-works.png)

1. **Header, symbolic** (`parse.py`): people, blocks, stations and who holds a
   station are read from the item's fixed-format header.
2. **Prefilter** (`pipeline.py`): note lines that mention no person, block or
   station are dropped before the model sees them (pure token match on the
   header's own strings, so it does not depend on phrasing).
3. **Extraction, model-based** (`extract.py`): one call per sample sends all
   remaining lines; Granite answers `N | short rewrite | FACT` per line in an
   8-operator language (`AT, NOT_AT, ON, NOT_ON, BEFORE, JUST_BEFORE, BETWEEN,
   NONE`). A tolerant parser accepts its corrections and stray prose and
   validates every name/block/station against the header.
4. **Aggregation** (`pipeline.py`): per-line plurality vote across samples;
   then a structural-prior repair (ambiguous items have 2 to 4 rotas,
   contradictions need at least 3 lines) that tries the smallest change,
   preferring readings other samples gave.
5. **Exact solve and decide** (`solver.py`, `decide.py`): enumerate all
   5! x 3! = 720 rotas, keep the consistent ones. 1 => unique, 2+ => ambiguous
   (all of them), 0 => inconsistent, and a minimal unsatisfiable subset is
   found exactly and cited verbatim from the notes.

![solver](docs/solver-3d.png)

## Results (visible set, live endpoint)

| budget | runs | macro mean (min to max) | unique | ambiguous | inconsistent | calls/item | $/run |
|---|---|---|---|---|---|---|---|
| 1x | 3 | 0.739 (0.700 to 0.783) | 0.62 | 0.80 | 0.80 | 1.00 | 0.016 |
| 3x | 3 | 0.806 (0.800 to 0.817) | 0.67 | 0.92 | 0.83 | 3.00 | 0.047 |
| 10x | 3 | 0.861 (0.850 to 0.883) | 0.72 | 0.97 | 0.90 | 10.00 | 0.158 |

Ablations, confusion matrices and failure analysis: [WRITEUP.md](WRITEUP.md).

## Reproduce

```
python3 tests/test_solver.py          # 20 pure tests, no network
./dev/final_runs.sh main              # 3 live runs per budget -> results/final/
./dev/final_runs.sh all               # + live ablation runs
python3 dev/summarize.py              # markdown table from results/final/
python3 dev/build_pool.py 10 dev/pool.json   # 10 i.i.d. extraction samples per item
python3 dev/simulate.py dev/pool.json        # offline ablation replay over that pool
```

## Layout

```
run                     launcher
src/auric/solver.py     constraint model, exact enumeration, MUS search
src/auric/parse.py      header parser, line splitting
src/auric/extract.py    prompt + tolerant parser for the model's replies
src/auric/client.py     endpoint client, budget accounting
src/auric/pipeline.py   prefilter, vote, prior repair, (adaptive), run_item
src/auric/decide.py     unique/ambiguous/inconsistent + citations
src/auric/cli.py        argument handling, ablation switches
src/auric/regex_baseline.py  DEV ONLY: hand regexes for the visible phrasings,
                        used to check solver semantics (scores 1.00 with the
                        solver). Never used by ./run.
tests/test_solver.py    unit tests
dev/                    pool builder, offline simulator, line-error report, run scripts
results/final/          answers, scores, traces and logs of every reported run
```
