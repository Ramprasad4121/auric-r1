"""End-to-end pipeline: parse -> extract (model) -> aggregate -> solve -> decide.

Components (each can be switched off for the ablation table):
  prefilter   drop lines that mention no rota person, station or block before
              the model sees them (lexical, phrasing-independent)
  vote        with >1 extraction samples, per-line majority vote over readings
  prior_pick  use the brief's structural priors (ambiguous => 2..4 rotas,
              conflict sets >= 3 lines) to reject implausible extractions and
              search nearby readings for a plausible one
  adaptive    stop sampling early once the solved answer is stable; with it
              off, every allowed call is spent

Aggregation and stopping are pure functions of the samples drawn so far, so
the same code runs live and in the offline simulator (dev/simulate.py).
"""
from __future__ import annotations

import itertools
import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from . import extract as ex
from .client import BudgetExceeded, GraniteClient
from .decide import decide, plausibility
from .parse import parse_header, split_item
from .solver import Header

BUDGETS = {"1x": 1, "3x": 3, "10x": 10}
Sample = Dict[int, Tuple[str, Optional[dict]]]


@dataclass
class Config:
    prefilter: bool = True
    vote: bool = True
    prior_pick: bool = True
    adaptive: bool = False
    calls: int = 1


def relevant_mask(h: Header, lines: List[str], prefilter: bool) -> List[bool]:
    if not prefilter:
        return [True] * len(lines)
    toks = list(h.people) + list(h.stations) + list(h.blocks)
    return [any(re.search(rf"\b{re.escape(t)}\b", l, re.I) for t in toks) for l in lines]


@dataclass
class Ctx:
    h: Header
    lines: List[str]   # lines sent to the model (citations come from here, verbatim)


def _assemble(ctx: Ctx, choice: Dict[int, Optional[dict]]):
    return [(ctx.lines[k], c) for k, c in sorted(choice.items()) if c is not None]


def _flat(s: Sample, n: int) -> Dict[int, Optional[dict]]:
    return {k: (s[k][1] if k in s and s[k][0] == "ok" else None) for k in range(n)}


def _tally(samples: List[Sample], n: int):
    tallies, rep = {}, {}
    for k in range(n):
        cnt: Counter = Counter()
        for s in samples:
            if k in s and s[k][0] in ("ok", "none"):
                key = ex.canon(s[k][1])
                cnt[key] += 1
                rep[(k, key)] = s[k][1]
        tallies[k] = cnt
    return tallies, rep


def _vote(samples: List[Sample], n: int) -> Dict[int, Optional[dict]]:
    """Per-line plurality over valid readings; malformed/missing abstain.
    Ties break toward the earliest sample's reading (deterministic)."""
    tallies, rep = _tally(samples, n)
    choice = {}
    for k in range(n):
        cnt = tallies[k]
        if not cnt:
            choice[k] = None
            continue
        top = max(cnt.values())
        tied = [key for key in cnt if cnt[key] == top]
        if len(tied) > 1:
            for s in samples:
                if k in s and s[k][0] in ("ok", "none") and ex.canon(s[k][1]) in tied:
                    tied = [ex.canon(s[k][1])]
                    break
        choice[k] = rep[(k, tied[0])]
    return choice


def _answer_key(ans: dict) -> str:
    import json
    a = {k: v for k, v in ans.items() if not k.startswith("_")}
    if a.get("case") == "ambiguous":
        a["assignments"] = sorted(json.dumps(x, sort_keys=True) for x in a["assignments"])
    if a.get("case") == "inconsistent":
        a = {"case": "inconsistent"}  # citations differ legitimately between MUSes
    return json.dumps(a, sort_keys=True)


def aggregate(ctx: Ctx, samples: List[Sample], cfg: Config) -> dict:
    n = len(ctx.lines)
    if len(samples) == 1 or not cfg.vote:
        cands = [decide(ctx.h, _assemble(ctx, _flat(s, n))) for s in samples]
        if not cfg.prior_pick or len(cands) == 1:
            return cands[0] if not cfg.prior_pick else (
                _prior_repair(ctx, samples, cands[0]) if plausibility(cands[0]) < 1 else cands[0])
        # answer-level majority among plausible candidates
        good = [c for c in cands if plausibility(c) >= 1] or cands
        cnt = Counter(_answer_key(c) for c in good)
        best = max(good, key=lambda c: cnt[_answer_key(c)])
        return best
    ans = decide(ctx.h, _assemble(ctx, _vote(samples, n)))
    if cfg.prior_pick and plausibility(ans) < 1.0:
        ans = _prior_repair(ctx, samples, ans)
    return ans


def should_stop(ctx: Ctx, samples: List[Sample], cfg: Config) -> bool:
    """Called after each sample with calls left. Without 'adaptive' we never
    stop early. With it: stop once at least two samples exist, the aggregated
    answer is plausible, and the newest sample on its own agrees with it."""
    if not cfg.adaptive or len(samples) < 2:
        return False
    agg = aggregate(ctx, samples, cfg)
    if plausibility(agg) < 1.0:
        return False
    last = decide(ctx.h, _assemble(ctx, _flat(samples[-1], len(ctx.lines))))
    prev = aggregate(ctx, samples[:-1], cfg)
    return _answer_key(last) == _answer_key(agg) and _answer_key(prev) == _answer_key(agg)


def _prior_repair(ctx: Ctx, samples: List[Sample], fallback: dict) -> dict:
    """The extraction violates a structural prior (too many rotas, or a 1-2
    line contradiction). Look for the smallest change that fixes it:
      (a) flip a contested line to a reading another sample gave it;
      (b) for a too-small contradiction, drop one of its lines or reverse
          the direction of an ordering fact in it (the commonest misread).
    Changes supported by other samples are preferred; at most two changes."""
    n = len(ctx.lines)
    base = _vote(samples, n) if len(samples) > 1 else _flat(samples[0], n)
    tallies, rep = _tally(samples, n)
    moves = []  # (cost, k, new_constraint_or_None)
    for k, cnt in tallies.items():
        cur = ex.canon(base.get(k))
        top = cnt.get(cur, 0)
        for key, c in cnt.items():
            if key != cur:
                moves.append((1 + top - c, k, rep[(k, key)]))
    d = fallback.get("_diag", {})
    if d.get("n_solutions") == 0:
        from .solver import minimal_unsat_subsets
        chosen = [(k, c) for k, c in sorted(base.items()) if c is not None]
        muses = minimal_unsat_subsets(ctx.h, [c for _, c in chosen], limit=5, max_size=2)
        for m in muses:
            for i in m:
                k, c = chosen[i]
                moves.append((3, k, None))
                if c["type"] in ("before", "next"):
                    moves.append((2, k, {**c, "a": c["b"], "b": c["a"]}))
    moves.sort(key=lambda x: x[0])
    moves = moves[:12]
    best, best_cost = fallback, None
    for r in (1, 2):
        for combo in itertools.combinations(moves, r):
            if len({k for _, k, _ in combo}) < r:
                continue
            ch = dict(base)
            for _, k, c in combo:
                ch[k] = c
            a = decide(ctx.h, _assemble(ctx, ch))
            cost = sum(x[0] for x in combo)
            if plausibility(a) >= 1.0 and (best_cost is None or cost < best_cost):
                best, best_cost = a, cost
        if best_cost is not None:
            break
    return best


def prepare(item: dict, cfg: Config) -> Ctx:
    head, lines = split_item(item["text"])
    h = parse_header(head)
    mask = relevant_mask(h, lines, cfg.prefilter)
    return Ctx(h=h, lines=[l for l, m in zip(lines, mask) if m])


def run_item(client: GraniteClient, item: dict, cfg: Config) -> Tuple[dict, dict]:
    item_id = item["id"]
    ctx = prepare(item, cfg)
    client.set_cap(item_id, cfg.calls)
    msgs = ex.build_messages(ctx.h, ctx.lines)
    samples: List[Sample] = []
    while client.remaining(item_id) > 0:
        try:
            reply = client.chat(item_id, msgs)
        except BudgetExceeded:
            break
        except RuntimeError:
            reply = ""
        samples.append(ex.parse_reply(ctx.h, reply, len(ctx.lines)))
        if client.remaining(item_id) > 0 and should_stop(ctx, samples, cfg):
            break
    if not samples:
        samples = [{}]
    ans = aggregate(ctx, samples, cfg)
    trace = {"n_sent": len(ctx.lines), "calls": client.calls[item_id], "diag": ans.get("_diag"),
             "samples": [{k: ex.canon(v[1]) if v[0] != "bad" else "BAD" for k, v in s.items()}
                         for s in samples],
             "sub_lines": ctx.lines}
    return ans, trace
