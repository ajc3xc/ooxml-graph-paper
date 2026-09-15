#!/usr/bin/env python3
"""Generate the two result figures for paper/main.tex from the exact numbers
already reported in Table 1-4 (paper/main.tex) -- not a re-analysis, a
visualization of already-verified numbers. Regenerate by hand if those
numbers ever change; nothing here reads run data live, so it will silently
go stale if main.tex's tables are edited without re-running this."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "paper" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "font.family": "serif",
    "font.size": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
})

CONTROL_COLOR = "#4a4a4a"
TREATMENT_COLOR = "#1f5fa8"

# ---------- Figure 1: single-edit + repeated-cycling forest plot ----------
# (family_label, control_rate, control_lo, control_hi, treatment_rate, treatment_lo, treatment_hi, p_label)
ROWS_1 = [
    ("Bibliography entry",            100.0, 100.0, 100.0, 100.0, 100.0, 100.0, "p=1.0"),
    ("Inline citation",               100.0, 100.0, 100.0, 100.0, 100.0, 100.0, "p=1.0"),
    ("Section reorder (K=1)",          83.6,  74.5,  92.7,  92.9,  85.7,  98.2, "p=0.271"),
    ("Section reorder (K=4)",          67.3,  54.5,  78.2,  92.9,  85.7,  98.2, "p=0.0015"),
]

fig, ax = plt.subplots(figsize=(6.5, 2.6))
y = list(range(len(ROWS_1)))[::-1]
for yi, (label, c, clo, chi, t, tlo, thi, p) in zip(y, ROWS_1):
    ax.plot([clo, chi], [yi + 0.12, yi + 0.12], color=CONTROL_COLOR, lw=1.4, solid_capstyle="butt")
    ax.plot(c, yi + 0.12, "o", color=CONTROL_COLOR, ms=5, zorder=3)
    ax.plot([tlo, thi], [yi - 0.12, yi - 0.12], color=TREATMENT_COLOR, lw=1.4, solid_capstyle="butt")
    ax.plot(t, yi - 0.12, "s", color=TREATMENT_COLOR, ms=5, zorder=3)
    weight = "bold" if p == "p=0.0015" else "normal"
    ax.text(102, yi, p, va="center", ha="left", fontsize=9, fontweight=weight)

ax.set_yticks(y)
ax.set_yticklabels([r[0] for r in ROWS_1])
ax.set_xlim(0, 124)
ax.set_xticks([0, 25, 50, 75, 100])
ax.set_xlabel("Pass rate (%), 95% CI")
ax.axvline(100, color="#dddddd", lw=0.8, zorder=0)
handles = [
    plt.Line2D([0], [0], marker="o", color=CONTROL_COLOR, linestyle="", label="Control (generic tools)"),
    plt.Line2D([0], [0], marker="s", color=TREATMENT_COLOR, linestyle="", label="Treatment (Meridian Docs)"),
]
ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0, -0.62), ncol=2, frameon=False, fontsize=9)
fig.tight_layout()
fig.savefig(OUT / "fig-single-edit-forest.pdf", bbox_inches="tight")
plt.close(fig)
print("wrote fig-single-edit-forest.pdf")

# ---------- Figure 2: render-gate before/after dumbbell ----------
# (family, orig_control, orig_treatment, clean_control, clean_treatment)
ROWS_2 = [
    ("Equation",           90.9, 46.2, 100.0, 100.0),
    ("Table (structural)",  92.3, 96.2, 100.0, 100.0),
    ("Caption",            100.0,  7.7, 100.0, 100.0),
]

fig, axes = plt.subplots(1, 2, figsize=(7.5, 2.6), sharey=True)
y = list(range(len(ROWS_2)))[::-1]

for ax, title, ci, ti in [
    (axes[0], "Original (contended host)", 1, 2),
    (axes[1], "Confirmatory (dedicated host)", 3, 4),
]:
    for yi, row in zip(y, ROWS_2):
        c, t = row[ci], row[ti]
        ax.plot([c, t], [yi, yi], color="#bbbbbb", lw=1.6, zorder=1)
        ax.plot(c, yi, "o", color=CONTROL_COLOR, ms=7, zorder=3)
        ax.plot(t, yi, "s", color=TREATMENT_COLOR, ms=7, zorder=3)
    ax.set_title(title, fontsize=10)
    ax.set_xlim(-4, 108)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xlabel("Pass rate (%)")

axes[0].set_yticks(y)
axes[0].set_yticklabels([r[0] for r in ROWS_2])
handles = [
    plt.Line2D([0], [0], marker="o", color=CONTROL_COLOR, linestyle="", label="Control"),
    plt.Line2D([0], [0], marker="s", color=TREATMENT_COLOR, linestyle="", label="Treatment"),
]
fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.08), ncol=2, frameon=False, fontsize=9)
fig.tight_layout()
fig.savefig(OUT / "fig-rendergate-dumbbell.pdf", bbox_inches="tight")
plt.close(fig)
print("wrote fig-rendergate-dumbbell.pdf")
