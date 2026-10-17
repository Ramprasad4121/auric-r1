"""Model-based constraint extraction.

The model never solves anything. It only translates numbered note lines into
a tiny line-oriented constraint language. We chose a terse DSL over JSON
after characterising Granite 8B: it breaks JSON brackets/quoting on long
outputs, but reliably copies short "N: OP args" lines.

All few-shot examples use names, stations and phrasings that do NOT occur in
the visible items, so the visible set behaves like held-out data for the
extractor.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .solver import ConstraintError, Header, validate

SYSTEM = """You convert workplace shift notes into formal facts. You do not solve the rota.

Each staff member works exactly one time block. Some staff also hold one station.
For every numbered note line write exactly one output line:

  N | short plain rewrite | FACT

FACT is one of:
  X AT 09:00            X works that block
  X NOT_AT 09:00        X does not work that block
  P ON intake           person P holds that station
  P NOT_ON intake       person P does not hold that station
  X BEFORE Y            X works earlier in the day than Y (any gap)
  X JUST_BEFORE Y       Y works the block straight after X (no gap)
  M BETWEEN A AND B     M works later than one of A, B and earlier than the other
  NONE                  nothing certain about the CURRENT rota

X, Y, M, A, B are a staff name, or [station] meaning whoever holds that station, e.g. [intake].

Rules:
- Hedges (I think, as far as I know, from memory, fairly sure, noted twice, it bears repeating) do NOT weaken a statement. It is a plain fact.
- "between ... in either order" or "not necessarily next to" is still a certain fact: use BETWEEN.
- Only the current rota counts. Past arrangements, earlier cycles, last month, how things used to be: NONE.
- Hypotheticals and wishes (if ... had, would have, would be, would be a better fit): NONE.
- Open questions (nobody is sure whether, it was discussed, left open, disagreement about): NONE.
- A request for a block that was refused, declined, turned down or not granted means NOT_AT that block.
- Something that rules a block out for someone, or someone unavailable at a block: NOT_AT.
- Social facts (car-sharing, training, keys, surveys, notes, contact sheets): NONE.
- "Y is later than X", "Y comes after X", "X precedes Y" all mean X BEFORE Y. The earlier one goes first.
- Use names, blocks and stations exactly as in the header. One line out per line in. No other text.
"""

EXAMPLE_USER = """Header: Staff: Oskar, Lina, Bea, Femi, Jun. Blocks: 06:00, 08:00, 10:00, 12:00, 14:00. Stations: loading, triage, dispatch (held by Oskar, Bea, Jun).

Lines:
1. Lina keeps the first-aid kit in her locker.
2. I believe Oskar does not hold triage.
3. Femi is rostered for 10:00.
4. Jun hoped to get 06:00 but was refused.
5. In the old system Bea ran loading.
6. If Femi had worked 14:00 we would have saved overtime.
7. From what I recall, Bea starts later than whoever is on dispatch.
8. Femi comes on straight after Lina finishes.
9. Lina's slot is somewhere between Jun's and Oskar's, order unknown.
10. It was never settled whether Oskar was on 08:00.
11. Dispatch belongs to Jun.
12. Oskar has finished before Femi begins.
13. Bea and Femi share a lift to work.
14. 12:00 cannot be Lina's block.
15. The loading station is not Bea's.
16. Repeating it: whatever order Femi and Bea come in, Jun works in the middle of them.
17. Bea's shift is the one right before Oskar's.
18. The triage holder starts after Lina.
19. Lina, Bea and Jun signed the safety form."""

EXAMPLE_ASSISTANT = """1 | first-aid kit | NONE
2 | Oskar not triage | Oskar NOT_ON triage
3 | Femi works 10:00 | Femi AT 10:00
4 | Jun refused 06:00 | Jun NOT_AT 06:00
5 | old system | NONE
6 | hypothetical | NONE
7 | dispatch holder earlier than Bea | [dispatch] BEFORE Bea
8 | Lina then Femi, no gap | Lina JUST_BEFORE Femi
9 | Lina between Jun and Oskar | Lina BETWEEN Jun AND Oskar
10 | unsettled | NONE
11 | Jun holds dispatch | Jun ON dispatch
12 | Oskar earlier than Femi | Oskar BEFORE Femi
13 | social | NONE
14 | Lina not 12:00 | Lina NOT_AT 12:00
15 | Bea not loading | Bea NOT_ON loading
16 | Jun between Femi and Bea | Jun BETWEEN Femi AND Bea
17 | Bea then Oskar, no gap | Bea JUST_BEFORE Oskar
18 | Lina earlier than triage holder | Lina BEFORE [triage]
19 | social | NONE"""


def header_text(h: Header) -> str:
    return (f"Header: Staff: {', '.join(h.people)}. Blocks: {', '.join(h.blocks)}. "
            f"Stations: {', '.join(h.stations)} (held by {', '.join(h.station_people)}).")


def build_messages(h: Header, lines: List[str]) -> List[dict]:
    numbered = "\n".join(f"{i + 1}. {l}" for i, l in enumerate(lines))
    user = f"{header_text(h)}\n\nLines:\n{numbered}"
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": EXAMPLE_USER},
        {"role": "assistant", "content": EXAMPLE_ASSISTANT},
        {"role": "user", "content": user},
    ]




def _term(h: Header, tok: str) -> Optional[str]:
    tok = tok.strip().strip(",.;'\"()[]")
    low = tok.lower()
    for pre in ("station:", "station=", "@"):
        if low.startswith(pre):
            st = low[len(pre):].strip()
            return "@" + st if st in h.stations else None
    if low in h.stations:          # bare station name used as a term
        return "@" + low
    for p in h.people:
        if tok == p or low == p.lower():
            return p
    return None


def _block(h: Header, tok: str) -> Optional[str]:
    tok = tok.strip().strip(",.;")
    m = re.match(r"^(\d{1,2}):(\d{2})$", tok)
    if not m:
        return None
    cand = f"{int(m.group(1)):02d}:{m.group(2)}"
    return cand if cand in h.blocks else (tok if tok in h.blocks else None)


def parse_op(h: Header, op_text: str) -> Tuple[str, Optional[dict]]:
    """Parse one FACT string. Returns (status, constraint): status is 'none'
    (model said NONE), 'ok', or 'bad' (unparseable / invalid for header)."""
    t = op_text.strip().strip("`*").strip()
    if "|" in t:
        t = t.rsplit("|", 1)[1].strip()
    t = re.sub(r"\[\s*([A-Za-z]+)\s*\]", r"station:\1", t)
    toks = t.replace(",", " ").split()
    if not toks:
        return "bad", None
    up = [x.upper() for x in toks]
    try:
        if up[0] in ("NONE", "IRRELEVANT", "N/A"):
            return "none", None
        if len(toks) == 3 and up[1] in ("AT", "NOT_AT"):
            who, blk = _term(h, toks[0]), _block(h, toks[2])
            if who and blk:
                return "ok", validate(h, {"type": up[1].lower(), "who": who, "block": blk})
        if len(toks) == 3 and up[1] in ("ON", "NOT_ON"):
            who = _term(h, toks[0]); st = toks[2].lower().strip(".,;").split(":")[-1]
            if who and not who.startswith("@") and st in h.stations:
                return "ok", validate(h, {"type": up[1].lower(), "who": who, "station": st})
        if len(toks) == 3 and up[1] in ("BEFORE", "JUST_BEFORE", "AFTER", "JUST_AFTER"):
            a, b = _term(h, toks[0]), _term(h, toks[2])
            if a and b:
                if up[1] in ("AFTER", "JUST_AFTER"):
                    a, b = b, a
                ty = "next" if "JUST" in up[1] else "before"
                return "ok", validate(h, {"type": ty, "a": a, "b": b})
        if len(toks) == 5 and up[1] == "BETWEEN" and up[3] in ("AND", "&"):
            m, a, b = _term(h, toks[0]), _term(h, toks[2]), _term(h, toks[4])
            if m and a and b:
                return "ok", validate(h, {"type": "between", "mid": m, "ends": [a, b]})
    except ConstraintError:
        return "bad", None
    return "bad", None


_START = re.compile(r"^\s*[`*#]*\s*(?:line\s*)?(\d+)\s*[|:.)\-]\s*", re.I | re.M)
_NAME = r"(?:\[\s*[A-Za-z]+\s*\]|[A-Za-z]+(?::[a-z]+)?)"
_FACT = re.compile(
    rf"(?<![A-Za-z\]])({_NAME})\s+(BETWEEN)\s+({_NAME})\s+(?:AND|&)\s+({_NAME})(?![A-Za-z])"
    rf"|(?<![A-Za-z\]])({_NAME})\s+(NOT_AT|AT|NOT_ON|ON|JUST_BEFORE|BEFORE|JUST_AFTER|AFTER)\s+"
    rf"(\d{{1,2}}:\d{{2}}|{_NAME})(?![A-Za-z:])")


def parse_block(h: Header, block: str) -> Tuple[str, Optional[dict]]:
    """Interpret the text the model wrote for one line. Prefer the strict
    'rewrite | FACT' tail; if the model rambled, take the LAST well-formed
    fact it wrote (Granite tends to correct itself late, not early)."""
    first = block.strip().splitlines()[0] if block.strip() else ""
    st, c = parse_op(h, first)
    if st != "bad":
        return st, c
    last: Tuple[str, Optional[dict]] = ("bad", None)
    for m in _FACT.finditer(block):
        g = m.groups()
        frag = f"{g[0]} BETWEEN {g[2]} AND {g[3]}" if g[0] else f"{g[4]} {g[5]} {g[6]}"
        r = parse_op(h, frag)
        if r[0] == "ok":
            last = r
    if last[0] == "bad" and re.search(r"\bNONE\b", block):
        return "none", None
    return last


def parse_reply(h: Header, reply: str, n_lines: int) -> Dict[int, Tuple[str, Optional[dict]]]:
    """Map 0-based line index -> (status, constraint). Missing lines are absent."""
    out: Dict[int, Tuple[str, Optional[dict]]] = {}
    starts = list(_START.finditer(reply))
    for j, m in enumerate(starts):
        end = starts[j + 1].start() if j + 1 < len(starts) else len(reply)
        i = int(m.group(1)) - 1
        if 0 <= i < n_lines and i not in out:
            out[i] = parse_block(h, reply[m.end():end])
    return out


def canon(c: Optional[dict]) -> str:
    """Hashable canonical form for voting."""
    if c is None:
        return "NONE"
    if c["type"] == "between":
        a, b = sorted(c["ends"])
        return f"between|{c['mid']}|{a}|{b}"
    return "|".join(str(c[k]) for k in sorted(c) if k != "type") + "|" + c["type"]
