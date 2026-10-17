"""Hand-written regex extractor over the VISIBLE phrasing pool.

This is NOT used by the submitted system. It exists for two reasons:
  1. as a development oracle, to check solver semantics against the key;
  2. as an ablation arm ("symbolic extraction"), which shows the ceiling of
     the solver pipeline on known phrasings and how badly a template parser
     generalises to unseen phrasings (the held-out set uses a disjoint pool).
It uses no model calls, so it is never a valid submission on its own.
"""
from __future__ import annotations

import re
from typing import Optional

from .solver import Header

HEDGE = re.compile(
    r"^(?:[^:]{0,80}:\s+)?(?:(?:As far as I know|Speaking from memory|Going off the roster|"
    r"My recollection is that|I'm fairly sure)[, ]\s*)*", re.I)

P = r"(?P<{}>[A-Z][a-z]+)"
T = r"(?P<{}>\d\d:\d\d)"
S = r"(?P<{}>[a-z]+)"


def _p(n): return P.format(n)
def _t(n): return T.format(n)
def _s(n): return S.format(n)


PATTERNS = [
    # block facts
    (rf"^{_p('x')} is on the {_t('t')} block\.$", "at"),
    (rf"^{_p('x')} is the one who opens up at {_t('t')}\.$", "at"),
    (rf"^{_p('x')} takes {_t('t')}, as things stand\.$", "at"),
    (rf"^Whoever drew the {_t('t')} block, it was {_p('x')}\.$", "at"),
    (rf"^{_t('t')} is when {_p('x')} is scheduled\.$", "at"),
    (rf"^The {_t('t')} block is {_p('x')}'s\.$", "at"),
    (rf"^{_p('x')} is not on the {_t('t')} block\.$", "not_at"),
    (rf"^{_p('x')} is unavailable at {_t('t')}\.$", "not_at"),
    (rf"^{_t('t')} is the one block {_p('x')} is definitely not on\.$", "not_at"),
    (rf"^You will not find {_p('x')} on the {_t('t')} block\.$", "not_at"),
    (rf"^The {_t('t')} block is not {_p('x')}'s\.$", "not_at"),
    (rf"^{_p('x')} has a standing commitment that rules out the {_t('t')} block entirely\.$", "not_at"),
    (rf"^{_p('x')} wanted {_t('t')} and did not get it\.$", "not_at?"),
    (rf"^{_p('x')} lobbied for {_t('t')} without success\.$", "not_at?"),
    (rf"^{_p('x')} asked to move to the {_t('t')} block; the request was declined\.$", "not_at?"),
    (rf"^{_p('x')} put in for the {_t('t')} block and was turned down\.$", "not_at?"),
    (rf"^If {_p('x')} had taken the {_t('t')} block the handover would have been smoother\.$", "not_at??"),
    (rf"^Had the rota gone the other way, {_p('x')} would be on {_t('t')}\.$", "not_at??"),
    # station facts
    (rf"^{_p('x')} (?:is on|is assigned to|has) {_s('s')}(?: this week)?\.$", "on"),
    (rf"^(?:The )?{_s('s')} (?:station )?is (?:covered by|down to) {_p('x')}\.$", "on"),
    (rf"^{_s('s')} is {_p('x')}'s station\.$", "on"),
    (rf"^{_p('x')} (?:is not on|is not assigned to|has not been put on) {_s('s')}\.$", "not_on"),
    (rf"^{_s('s')} is covered by someone other than {_p('x')}\.$", "not_on"),
    (rf"^{_s('s')} is not {_p('x')}'s station\.$", "not_on"),
    (rf"^You can rule {_p('x')} out for {_s('s')}\.$", "not_on"),
    # ordering
    (rf"^{_p('b')} comes later in the day than {_p('a')}\.$", "before"),
    (rf"^{_p('a')} works earlier in the day than {_p('b')}\.$", "before"),
    (rf"^{_p('a')} is done before {_p('b')} starts\.$", "before"),
    (rf"^By the time {_p('b')} starts, {_p('a')} has already been on\.$", "before"),
    (rf"^{_p('a')}'s block falls somewhere earlier than {_p('b')}'s\.$", "before"),
    (rf"^{_p('b')} is on later than whoever has {_s('sa')}\.$", "before"),
    (rf"^Whoever (?:has|is on) {_s('sa')} (?:is done before|works earlier in the day than) {_p('b')}(?: starts)?\.$", "before"),
    (rf"^The {_s('sa')} station is covered earlier in the day than {_p('b')}'s block\.$", "before"),
    (rf"^{_s('sa')} is covered before {_p('b')} comes on\.$", "before"),
    (rf"^The person on {_s('sa')} precedes {_p('b')}\.$", "before"),
    (rf"^{_p('b')} is on the block directly after {_p('a')}\.$", "next"),
    (rf"^{_p('a')} is on the block immediately before {_p('b')}\.$", "next"),
    (rf"^{_p('a')} hands straight over to {_p('b')}\.$", "next"),
    (rf"^{_p('b')} relieves {_p('a')} directly, with no block in between\.$", "next"),
    (rf"^{_p('a')} then {_p('b')}, back to back\.$", "next"),
    (rf"^There is no block between {_p('a')}'s and {_p('b')}'s, in that order\.$", "next"),
    (rf"^{_p('b')} takes over from {_p('a')} later in the day\.$", "before?"),
    (rf"^{_p('m')} is on after one of {_p('e1')} and {_p('e2')} and before the other\.$", "between"),
    (rf"^{_p('m')} sits between {_p('e1')} and {_p('e2')} on the rota\.$", "between"),
    (rf"^{_p('m')} works at some point between {_p('e1')} and {_p('e2')}, not necessarily adjacent to either\.$", "between"),
    (rf"^{_p('m')}'s block falls between {_p('e1')}'s and {_p('e2')}'s, in one order or the other\.$", "between"),
    (rf"^Put {_p('m')} between {_p('e1')} and {_p('e2')}, though not necessarily next to either\.$", "between"),
    (rf"^Whichever way round {_p('e1')} and {_p('e2')} are, {_p('m')} is between them\.$", "between"),
]
_COMPILED = [(re.compile(p, re.I), k) for p, k in PATTERNS]


def extract(h: Header, line: str, mode: str = "strict") -> Optional[dict]:
    """mode: which uncertain readings to include ('strict' = only '?'-free)."""
    body = HEDGE.sub("", line).strip()
    body = body[0].upper() + body[1:] if body else body
    for rx, kind in _COMPILED:
        m = rx.match(body)
        if not m:
            continue
        q = kind.count("?")
        base = kind.rstrip("?")
        if q and q > {"strict": 0, "declined": 1, "all": 2}[mode]:
            return None
        g = m.groupdict()

        def term(n):
            if n in g and g[n]:
                return g[n] if g[n] in h.people else None
            sn = "s" + n
            if sn in g and g[sn]:
                st = g[sn].lower()
                return "@" + st if st in h.stations else None
            return None

        if base in ("at", "not_at"):
            return {"type": base, "who": g["x"], "block": g["t"]}
        if base in ("on", "not_on"):
            st = g["s"].lower()
            if st not in h.stations:
                return None
            return {"type": base, "who": g["x"], "station": st}
        if base in ("before", "next"):
            a, b = term("a"), term("b")
            return {"type": base, "a": a, "b": b} if a and b else None
        if base == "between":
            return {"type": "between", "mid": g["m"], "ends": [g["e1"], g["e2"]]}
    return None
