import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

fig, ax = plt.subplots(figsize=(10, 15), dpi=160)
ax.set_xlim(0, 10); ax.set_ylim(0, 15); ax.axis("off")
fig.patch.set_facecolor("white")

MODEL = "#FFE7C2"; SYM = "#D6E8FF"; IO = "#E9E9EE"; OUT = "#D9F2DF"

def box(x, y, w, h, title, sub, color):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.18",
                                fc=color, ec="#333333", lw=1.4))
    ax.text(x + w/2, y + h - 0.32, title, ha="center", va="top", fontsize=12.5, weight="bold", color="#111")
    ax.text(x + w/2, y + h - 0.78, sub, ha="center", va="top", fontsize=9.6, color="#333", linespacing=1.35)

def arrow(x1, y1, x2, y2, label=None):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", lw=1.6, color="#333"))
    if label:
        ax.text((x1+x2)/2 + 0.12, (y1+y2)/2, label, fontsize=9, color="#555", va="center")

ax.text(5, 14.65, "Weak Model + Solver Harness", ha="center", fontsize=17, weight="bold")
ax.text(5, 14.2, "Auric AI R1: granite-4.2-8b does the reading, code does the logic",
        ha="center", fontsize=10.5, color="#555")

box(1.5, 12.45, 7, 1.35, "1. Shift notes (items.json)",
    "Messy text: header + hedged constraints + filler lines", IO)
arrow(5, 12.45, 5, 12.0)

box(1.5, 10.35, 7, 1.6, "2. Header parser (symbolic)",
    "Pulls names, time blocks, stations, who is on a station\nSplits the body into numbered lines, verbatim", SYM)
arrow(5, 10.35, 5, 9.9)

box(1.5, 7.75, 7, 2.1, "3. Constraint extractor (granite-4.2-8b)",
    "One call per item, all lines at once\nEach line -> small typed DSL or IRRELEVANT\ne.g. AFTER(Meera, Samuel, 1)   NOT_STATION(Ayesha, calibration)\nBETWEEN(Meera, Tomas, Rohan)   Hedges = full facts", MODEL)
arrow(5, 7.75, 5, 7.3)

box(1.5, 5.7, 7, 1.55, "4. Validator + voting",
    "Parse check, drop malformed output, map names verbatim\n3x/10x: extra calls, keep per-line majority vote", SYM)
arrow(5, 5.7, 5, 5.25)

box(1.5, 3.55, 7, 1.65, "5. Exact solver (symbolic)",
    "Enumerates every block + station permutation\nCounts the rotas that satisfy all constraints", SYM)

# branches
arrow(3.0, 3.55, 1.6, 2.6, "")
arrow(5.0, 3.55, 5.0, 2.6, "")
arrow(7.0, 3.55, 8.4, 2.6, "")

box(0.2, 0.9, 3.0, 1.65, "1 rota", "case: unique\nreturn the assignment", OUT)
box(3.5, 0.9, 3.0, 1.65, "2 to 4 rotas", "case: ambiguous\nreturn every one", OUT)
box(6.8, 0.9, 3.0, 1.65, "0 rotas", "case: inconsistent\nminimal conflict search\ncite those lines verbatim", OUT)

ax.text(1.7, 2.95, "exactly 1", fontsize=9, color="#555")
ax.text(5.1, 2.95, "2 to 4", fontsize=9, color="#555")
ax.text(7.95, 2.95, "none", fontsize=9, color="#555")

# legend
lx, ly = 1.5, 0.25
for i, (c, t) in enumerate([(MODEL, "model call"), (SYM, "plain code"), (OUT, "answer")]):
    ax.add_patch(FancyBboxPatch((lx + i*2.5, ly), 0.35, 0.3, boxstyle="round,pad=0.01", fc=c, ec="#333"))
    ax.text(lx + i*2.5 + 0.5, ly + 0.15, t, va="center", fontsize=9.5)

plt.savefig("/workspace/files/auric/how-it-works.png", bbox_inches="tight", facecolor="white")
