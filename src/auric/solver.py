"""Exact symbolic solver for rota-logic items.

Pure Python, no model, no I/O. A rota is a bijection people -> blocks plus a
bijection station-holders -> stations. Items are tiny (5! * 3! = 720 rotas),
so we enumerate everything exactly and never approximate.

Constraint representation (a plain dict, which is also what the model is
asked to emit after normalisation):

    {"type": "at",          "who": X, "block": "11:00"}
    {"type": "not_at",      "who": X, "block": "11:00"}
    {"type": "on",          "who": P, "station": "intake"}
    {"type": "not_on",      "who": P, "station": "intake"}
    {"type": "before",      "a": X, "b": Y}          # X's block earlier than Y's
    {"type": "next",        "a": X, "b": Y}          # Y's block immediately after X's
    {"type": "between",     "mid": M, "ends": [A, B]} # M strictly between A and B, either order

A term X is either a person name or a station reference written "@station"
("whoever has packing").
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

Constraint = dict


@dataclass
class Header:
    people: List[str]
    blocks: List[str]
    stations: List[str]
    station_people: List[str]

    @property
    def off_station(self) -> List[str]:
        return [p for p in self.people if p not in self.station_people]


@dataclass(frozen=True)
class Rota:
    block: Tuple[Tuple[str, str], ...]     # (person, block)
    station: Tuple[Tuple[str, str], ...]   # (person, station)

    def block_of(self) -> Dict[str, str]:
        return dict(self.block)

    def station_of(self) -> Dict[str, str]:
        return dict(self.station)

    def to_answer(self, header: Header) -> dict:
        b, s = self.block_of(), self.station_of()
        out = {}
        for p in header.people:
            entry = {"block": b[p]}
            if p in s:
                entry["station"] = s[p]
            out[p] = entry
        return out


def enumerate_rotas(h: Header) -> List[Rota]:
    rotas = []
    for bperm in itertools.permutations(h.blocks, len(h.people)):
        for sperm in itertools.permutations(h.stations, len(h.station_people)):
            rotas.append(Rota(tuple(zip(h.people, bperm)), tuple(zip(h.station_people, sperm))))
    return rotas


class ConstraintError(ValueError):
    """Raised when a constraint is malformed for this header."""


def _check_term(h: Header, t) -> None:
    if not isinstance(t, str):
        raise ConstraintError(f"bad term {t!r}")
    if t.startswith("@"):
        if t[1:] not in h.stations:
            raise ConstraintError(f"unknown station {t!r}")
    elif t not in h.people:
        raise ConstraintError(f"unknown person {t!r}")


def validate(h: Header, c: Constraint) -> Constraint:
    """Return c if it is well-formed for header h, else raise ConstraintError."""
    if not isinstance(c, dict):
        raise ConstraintError("not a dict")
    ty = c.get("type")
    if ty in ("at", "not_at"):
        _check_term(h, c.get("who"))
        if c.get("block") not in h.blocks:
            raise ConstraintError(f"unknown block {c.get('block')!r}")
    elif ty in ("on", "not_on"):
        if c.get("who") not in h.people:
            raise ConstraintError("unknown person")
        if c.get("station") not in h.stations:
            raise ConstraintError("unknown station")
    elif ty in ("before", "next"):
        _check_term(h, c.get("a")); _check_term(h, c.get("b"))
        if c["a"] == c["b"]:
            raise ConstraintError("self relation")
    elif ty == "between":
        ends = c.get("ends")
        if not isinstance(ends, (list, tuple)) or len(ends) != 2:
            raise ConstraintError("between needs two ends")
        for t in [c.get("mid"), *ends]:
            _check_term(h, t)
        if len({c["mid"], ends[0], ends[1]}) != 3:
            raise ConstraintError("between needs three distinct terms")
    else:
        raise ConstraintError(f"unknown type {ty!r}")
    return c


def _idx(h: Header, rota: Rota, term: str) -> Optional[int]:
    """Block index of a term in this rota (None if a station is unheld)."""
    b = rota.block_of()
    if term.startswith("@"):
        st = term[1:]
        holder = next((p for p, s in rota.station if s == st), None)
        if holder is None:
            return None
        return h.blocks.index(b[holder])
    return h.blocks.index(b[term])


def holds(h: Header, rota: Rota, c: Constraint) -> bool:
    ty = c["type"]
    if ty in ("at", "not_at"):
        i = _idx(h, rota, c["who"])
        r = i is not None and h.blocks[i] == c["block"]
        return r if ty == "at" else not r
    if ty in ("on", "not_on"):
        r = rota.station_of().get(c["who"]) == c["station"]
        return r if ty == "on" else not r
    if ty in ("before", "next"):
        a, b = _idx(h, rota, c["a"]), _idx(h, rota, c["b"])
        if a is None or b is None:
            return False
        if a == b:  # same person via station reference: never before itself
            return False
        return a < b if ty == "before" else b == a + 1
    if ty == "between":
        m = _idx(h, rota, c["mid"])
        x, y = (_idx(h, rota, e) for e in c["ends"])
        if None in (m, x, y) or len({m, x, y}) < 3:
            return False
        return min(x, y) < m < max(x, y)
    raise ConstraintError(ty)


def solve(h: Header, constraints: Sequence[Constraint], rotas: Optional[List[Rota]] = None) -> List[Rota]:
    rotas = rotas if rotas is not None else enumerate_rotas(h)
    return [r for r in rotas if all(holds(h, r, c) for c in constraints)]


def minimal_unsat_subsets(h: Header, constraints: Sequence[Constraint], limit: int = 50,
                          max_size: int = 7) -> List[Tuple[int, ...]]:
    """All minimal unsatisfiable subsets (by index), smallest first.

    Exact: we precompute, for every constraint, the bitmask of rotas it
    allows; a subset is UNSAT iff the AND of its masks is zero. We search
    subsets by increasing size and keep those with no UNSAT proper subset.
    With <= ~20 constraints and small MUSes this is fast.
    """
    rotas = enumerate_rotas(h)
    full = (1 << len(rotas)) - 1
    masks = []
    for c in constraints:
        m = 0
        for i, r in enumerate(rotas):
            if holds(h, r, c):
                m |= 1 << i
        masks.append(m)
    n = len(constraints)
    found: List[Tuple[int, ...]] = []
    # drop constraints that allow everything: they can never be in a MUS
    useful = [i for i in range(n) if masks[i] != full]
    for k in range(1, min(max_size, len(useful)) + 1):
        for combo in itertools.combinations(useful, k):
            if any(set(f) <= set(combo) for f in found):
                continue
            m = full
            for i in combo:
                m &= masks[i]
                if not m:
                    break
            if m == 0:
                found.append(combo)
                if len(found) >= limit:
                    return found
    return found
