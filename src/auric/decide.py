"""Turn extracted constraints into an answer: unique / ambiguous / inconsistent."""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from .solver import Header, minimal_unsat_subsets, solve

MAX_AMBIG = 4   # brief: ambiguous items have 2..4 assignments
MIN_MUS = 3     # brief: on this set every conflict set has >= 3 statements


def decide(h: Header, cons: Sequence[Tuple[str, dict]]) -> dict:
    """cons: list of (source_line, constraint). Returns an answer object plus
    a private '_diag' entry (stripped before writing)."""
    only = [c for _, c in cons]
    sols = solve(h, only)
    if len(sols) == 1:
        return {"case": "unique", "assignment": sols[0].to_answer(h),
                "_diag": {"n_solutions": 1}}
    if len(sols) > 1:
        return {"case": "ambiguous", "assignments": [s.to_answer(h) for s in sols],
                "_diag": {"n_solutions": len(sols)}}
    muses = minimal_unsat_subsets(h, only)
    if not muses:  # should not happen: 0 solutions implies some MUS
        return {"case": "inconsistent", "conflicts": [l for l, _ in cons],
                "_diag": {"n_solutions": 0, "mus": None}}
    # Prefer the smallest MUS that meets the >=3 prior; fall back to smallest.
    ok = [m for m in muses if len(m) >= MIN_MUS]
    best = (ok or muses)[0]
    lines: List[str] = []
    for i in best:
        if cons[i][0] not in lines:
            lines.append(cons[i][0])
    return {"case": "inconsistent", "conflicts": lines,
            "_diag": {"n_solutions": 0, "mus_sizes": [len(m) for m in muses[:10]]}}


def plausibility(ans: dict) -> float:
    """How well an answer fits the brief's structural priors (higher = better).
    Used to choose between candidate extractions when we have spare calls."""
    d = ans.get("_diag", {})
    n = d.get("n_solutions", 0)
    if n == 1:
        return 1.0
    if 2 <= n <= MAX_AMBIG:
        return 1.0
    if n > MAX_AMBIG:
        return 0.2  # under-constrained: almost certainly a missed constraint
    sizes = d.get("mus_sizes") or []
    if sizes and min(sizes) >= MIN_MUS:
        return 1.0
    return 0.3      # a 1- or 2-line contradiction: almost certainly a misread line


def strip(ans: dict) -> dict:
    return {k: v for k, v in ans.items() if not k.startswith("_")}
