import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
import colorsys

fig, ax = plt.subplots(figsize=(11, 15), dpi=170)
ax.set_xlim(0, 11); ax.set_ylim(-0.7, 15.4); ax.axis("off")
BG = "#0F1420"; fig.patch.set_facecolor(BG)
DX, DY = 0.55, 0.45   # depth offset (cabinet projection)

def shade(c, f):
    r, g, b = [int(c[i:i+2], 16)/255 for i in (1, 3, 5)]
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return colorsys.hls_to_rgb(h, max(0, min(1, l*f)), s)

def block(x, y, w, h, c, title, sub, ts=13, ss=9.6):
    ax.add_patch(Polygon([(x+0.15, y-0.15), (x+w+0.15, y-0.15), (x+w+DX+0.15, y+DY-0.15), (x+w+DX+0.15, y+h+DY-0.15), (x+0.15, y+h-0.15)], closed=True, fc="black", alpha=0.4, ec="none"))
    ax.add_patch(Polygon([(x, y+h), (x+w, y+h), (x+w+DX, y+h+DY), (x+DX, y+h+DY)], closed=True, fc=shade(c, 1.12), ec=BG, lw=1.3))
    ax.add_patch(Polygon([(x+w, y), (x+w+DX, y+DY), (x+w+DX, y+h+DY), (x+w, y+h)], closed=True, fc=shade(c, 0.62), ec=BG, lw=1.3))
    ax.add_patch(Polygon([(x, y), (x+w, y), (x+w, y+h), (x, y+h)], closed=True, fc=c, ec=BG, lw=1.3))
    ax.text(x+w/2, y+h*0.66, title, ha="center", va="center", fontsize=ts, weight="bold", color="#10131A")
    ax.text(x+w/2, y+h*0.3, sub, ha="center", va="center", fontsize=ss, color="#222A38", linespacing=1.3)

def arrow(x1, y1, x2, y2):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>,head_width=0.4,head_length=0.7", lw=2.4, color="#7FD3FF"))

GREY, BLUE, AMBER, GREEN = "#C9CED8", "#8EC5FF", "#FFC66B", "#7FE0A0"
ax.text(5.5, 14.95, "Weak Model + Solver Harness", ha="center", fontsize=20, weight="bold", color="white")
ax.text(5.5, 14.45, "granite-4.2-8b reads.  Code reasons.", ha="center", fontsize=11.5, color="#9FB0C8")

W, H, X = 7.0, 1.45, 1.75
rows = [
    (12.3, GREY,  "1. Shift notes", "header + hedged constraints + filler lines"),
    (10.0, BLUE,  "2. Header parser", "names, blocks, stations\nbody split into verbatim lines"),
    (7.7,  AMBER, "3. Granite extractor  (model call)", "each line -> typed constraint or IRRELEVANT\nAFTER(Meera, Samuel)   NOT_STATION(Ayesha, calibration)"),
    (5.4,  BLUE,  "4. Validate + vote", "drop malformed output, keep names verbatim\n3x / 10x budget: majority vote per line"),
    (3.1,  BLUE,  "5. Exact solver", "enumerate every block + station permutation\ncount the rotas that satisfy all constraints"),
]
for y, c, t, s in rows:
    block(X, y, W, H, c, t, s)
for i in range(len(rows)-1):
    arrow(X+W/2, rows[i][0]-0.05, X+W/2, rows[i+1][0]+H+DY+0.08)

oW, oH = 2.75, 1.35
outs = [(0.35, "unique", "1 rota\nreturn it"), (4.1, "ambiguous", "2 to 4 rotas\nreturn every one"), (7.85, "inconsistent", "0 rotas\ncite minimal conflict")]
for ox, t, s in outs:
    block(ox, 0.55, oW, oH, GREEN, t, s, ts=12, ss=9.2)
    arrow(X+W/2, rows[-1][0]-0.05, ox+oW/2, 0.55+oH+DY+0.08)

for i, (c, t) in enumerate([(AMBER, "model call"), (BLUE, "plain code"), (GREEN, "answer")]):
    lx = 2.6 + i*2.3
    ax.add_patch(Polygon([(lx, -0.5), (lx+0.35, -0.5), (lx+0.35, -0.2), (lx, -0.2)], closed=True, fc=c, ec="none"))
    ax.text(lx+0.5, -0.35, t, va="center", fontsize=10.5, color="#DDE6F2")

plt.savefig("how-it-works-3d.png", bbox_inches="tight", facecolor=BG)
