import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

people = ["Daniel", "Rohan", "Nadia", "Priya", "Meera"]
blocks = ["07:00", "09:00", "11:00", "13:00", "15:00"]
stations = ["intake", "calibration", "packing", "no station"]
on_station = {"Daniel", "Rohan", "Meera"}
sol = {"Daniel": ("11:00", "intake"), "Rohan": ("09:00", "packing"), "Nadia": ("13:00", "no station"),
       "Priya": ("15:00", "no station"), "Meera": ("07:00", "calibration")}

shape = (len(people), len(blocks), len(stations))
possible = np.zeros(shape, bool); chosen = np.zeros(shape, bool)
for i, p in enumerate(people):
    for j, b in enumerate(blocks):
        for k, s in enumerate(stations):
            ok = (s != "no station") if p in on_station else (s == "no station")
            possible[i, j, k] = ok
            chosen[i, j, k] = sol[p] == (b, s)

BG = "#0F1420"
fig = plt.figure(figsize=(16, 8.6), dpi=150); fig.patch.set_facecolor(BG)

def setup(ax, title, sub):
    ax.set_facecolor(BG)
    ax.set_xticks(np.arange(len(people)) + 0.5); ax.set_xticklabels(people, color="#DDE6F2", fontsize=9)
    ax.set_yticks(np.arange(len(blocks)) + 0.5); ax.set_yticklabels(blocks, color="#DDE6F2", fontsize=9)
    ax.set_zticks(np.arange(len(stations)) + 0.5); ax.set_zticklabels(stations, color="#DDE6F2", fontsize=9)
    for a in (ax.xaxis, ax.yaxis, ax.zaxis):
        a.set_pane_color((0.09, 0.12, 0.18, 1)); a._axinfo["grid"]["color"] = (0.3, 0.35, 0.45, 0.5)
    ax.set_xlabel("person", color="#9FB0C8", labelpad=10); ax.set_ylabel("time block", color="#9FB0C8", labelpad=10)
    ax.set_zlabel("station", color="#9FB0C8", labelpad=10)
    ax.view_init(elev=24, azim=-58)
    ax.set_title(title + "\n", color="white", fontsize=15, weight="bold")
    ax.text2D(0.5, 0.97, sub, transform=ax.transAxes, ha="center", color="#9FB0C8", fontsize=10.5)

ax1 = fig.add_subplot(1, 2, 1, projection="3d")
c1 = np.empty(shape, object); c1[possible] = "#8EC5FF66"
ax1.voxels(possible, facecolors=c1, edgecolors="#8EC5FF55", linewidth=0.4)
setup(ax1, "1. Every possible placement", "55 cells, 720 candidate rotas (5! blocks x 3! stations) before any constraint")

ax2 = fig.add_subplot(1, 2, 2, projection="3d")
ghost = possible & ~chosen
c2 = np.empty(shape, object); c2[ghost] = "#FF6B6B14"; c2[chosen] = "#7FE0A0F0"
e2 = np.empty(shape, object); e2[ghost] = "#FF6B6B30"; e2[chosen] = "#0F1420"
ax2.voxels(ghost, facecolors="#FF6B6B12", edgecolors="#FF6B6B30", linewidth=0.4)
ax2.voxels(chosen, facecolors="#7FE0A0", edgecolors="#0F1420", linewidth=0.8)
setup(ax2, "2. After Granite's constraints", "solver prunes everything that breaks a rule: 1 rota left = unique")

fig.suptitle("How the solver finds the answer in 3D  (visible item B2-002)", color="white", fontsize=18, weight="bold", y=0.995)
rules = ("Constraints Granite extracted:   Rohan directly after Meera   |   Nadia then Priya, back to back   |   "
         "calibration earlier than Rohan   |  ...")
fig.text(0.5, 0.045, rules, ha="center", color="#FFC66B", fontsize=10.5)
fig.text(0.5, 0.012, "green = final rota   faint red = ruled out   0 left = inconsistent (cite minimal conflict)   2 to 4 left = ambiguous",
         ha="center", color="#DDE6F2", fontsize=10)
plt.subplots_adjust(left=0.0, right=1.0, top=0.9, bottom=0.08, wspace=0.02)
plt.savefig("solver-3d.png", facecolor=BG)
