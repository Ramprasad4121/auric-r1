"""Summarise results/final/*.score.txt (+ call/cost from the run logs) as a markdown table."""
import glob, json, re, statistics as st, sys, collections
R = sys.argv[1] if len(sys.argv) > 1 else "results/final"
groups = collections.defaultdict(list)
for f in sorted(glob.glob(f"{R}/*.score.txt")):
    name = f.split("/")[-1][:-10]
    s = json.load(open(f))
    log = open(f[:-10] + ".log").read().strip().splitlines()[-1]
    L = json.loads(log)
    g = re.sub(r"_r\d+$", "", name)
    groups[g].append((s, L))
print("| config | budget | runs | macro mean (min-max) | unique | ambiguous | inconsistent | calls/item | $/run |")
print("|---|---|---|---|---|---|---|---|---|")
for g, rs in groups.items():
    cfg, b = g.rsplit("_", 1)
    m = [s["macro_exact_match"] for s, _ in rs]
    pc = {k: st.mean(s["per_case_rate"][k] for s, _ in rs) for k in ("unique", "ambiguous", "inconsistent")}
    calls = st.mean(L["calls_total"] / L["items"] for _, L in rs)
    cost = st.mean(L["usage"]["cost_micro_usd"] for _, L in rs) / 1e6
    print(f"| {cfg} | {b} | {len(rs)} | {st.mean(m):.3f} ({min(m):.3f}-{max(m):.3f}) | {pc['unique']:.2f} | {pc['ambiguous']:.2f} | {pc['inconsistent']:.2f} | {calls:.2f} | {cost:.3f} |")
