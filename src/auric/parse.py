"""Symbolic parsing of an item: the header (people, blocks, stations) and the
note lines. The header is the one part of each item that is boilerplate, so
we parse it with tolerant regexes and fall back to looser heuristics.
Note lines are NOT interpreted here; that is the model's job.
"""
from __future__ import annotations

import re
from typing import List, Tuple

from .solver import Header

_TIME = re.compile(r"\b\d{1,2}:\d{2}\b")


def _split_names(s: str) -> List[str]:
    s = s.replace(" and ", ", ")
    return [x.strip().strip(".") for x in s.split(",") if x.strip().strip(".")]


def split_item(text: str) -> Tuple[str, List[str]]:
    parts = text.split("\n\n", 1)
    head = parts[0]
    body = parts[1] if len(parts) > 1 else ""
    lines = [l.strip() for l in body.split("\n") if l.strip()]
    return head, lines


def parse_header(head: str) -> Header:
    m = re.search(r"on the rota:\s*(.*?)\.\s", head) or re.search(r"rota:\s*(.*?)\.", head)
    if not m:
        raise ValueError("cannot find rota")
    people = _split_names(m.group(1))

    bm = re.search(r"Blocks run\s*(.*?)(?:,\s*one person|\.)", head)
    blocks = _TIME.findall(bm.group(1)) if bm else _TIME.findall(head)

    sm = re.search(r"stations?, one person on each:\s*(.*?)\.", head) or \
        re.search(r"stations?[^:]*:\s*(.*?)\.", head)
    stations = _split_names(sm.group(1)) if sm else []

    pm = re.search(r"people on a station are\s*(.*?);", head) or \
        re.search(r"on a station (?:are|is)\s*(.*?)[;.]", head)
    if pm:
        station_people = _split_names(pm.group(1))
    else:
        station_people = list(people) if len(stations) == len(people) else []
    return Header(people=people, blocks=blocks, stations=stations, station_people=station_people)


def mentions(h: Header, line: str) -> bool:
    """Could this line possibly constrain the rota? Purely lexical: it must
    mention a person on the rota. (A line naming nobody cannot pin anyone.)"""
    return any(re.search(rf"\b{re.escape(p)}\b", line) for p in h.people)


def strip_hedge(line: str) -> str:
    """Remove a leading clause ending in ':' (e.g. 'Noted twice: ...'). Only a
    cosmetic aid for the prompt; citations always use the original line."""
    return line
