"""./run <items.json> --budget <1x|3x|10x> --out <answers.json> [--ablate comp,...]"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import sys
import time

from .client import GraniteClient
from .decide import strip
from .pipeline import BUDGETS, Config, run_item

COMPONENTS = ("prefilter", "vote", "prior_pick", "adaptive")
# adaptive early stopping is built and tested but OFF by default: on the
# offline replay it saved calls and cost accuracy at 10x (see README write-up).
DEFAULT_OFF = {"adaptive"}


def fallback_answer(item: dict) -> dict:
    # Only used if every model call for an item failed at the transport
    # level (no reply at all). Still well-formed.
    from .parse import parse_header, split_item
    from .solver import enumerate_rotas
    h = parse_header(split_item(item["text"])[0])
    return {"case": "unique", "assignment": enumerate_rotas(h)[0].to_answer(h)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="run")
    ap.add_argument("items")
    ap.add_argument("--budget", required=True, choices=list(BUDGETS))
    ap.add_argument("--out", required=True)
    ap.add_argument("--ablate", default="", help=f"comma list of components to disable: {COMPONENTS}")
    ap.add_argument("--enable", default="", help="comma list of default-off components to enable (adaptive)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--trace", default=None, help="optional path for per-item traces (jsonl)")
    ap.add_argument("--log", default=None, help="optional path for raw model replies (jsonl)")
    a = ap.parse_args(argv)

    on = {x.strip() for x in a.enable.split(",") if x.strip()}
    off = (DEFAULT_OFF - on) | {x.strip() for x in a.ablate.split(",") if x.strip()}
    bad = (off | on) - set(COMPONENTS)
    if bad:
        ap.error(f"unknown components: {bad}")
    cfg = Config(**{c: (c not in off) for c in COMPONENTS}, calls=BUDGETS[a.budget])

    items = json.load(open(a.items))
    client = GraniteClient(log_path=a.log)
    answers, traces = {}, []
    t0 = time.time()

    def work(it):
        try:
            ans, tr = run_item(client, it, cfg)
            return it["id"], strip(ans), tr
        except Exception as e:  # never let one item sink the run
            return it["id"], fallback_answer(it), {"error": repr(e)}

    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        for iid, ans, tr in ex.map(work, items):
            answers[iid] = ans
            tr["id"] = iid
            traces.append(tr)

    with open(a.out, "w") as f:
        json.dump(answers, f, indent=1)
    calls = dict(client.calls)
    stats = {
        "budget": a.budget, "ablate": sorted(off), "items": len(items),
        "calls_total": sum(calls.values()),
        "calls_min": min(calls.get(i["id"], 0) for i in items),
        "calls_max": max(calls.get(i["id"], 0) for i in items),
        "usage": dict(client.usage), "seconds": round(time.time() - t0, 1),
    }
    if a.trace:
        with open(a.trace, "w") as f:
            for t in traces:
                f.write(json.dumps(t) + "\n")
            f.write(json.dumps({"_stats": stats}) + "\n")
    print(json.dumps(stats), file=sys.stderr)
    if stats["calls_min"] < 1 or stats["calls_max"] > BUDGETS[a.budget]:
        print("WARNING: budget accounting outside [1, cap]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
