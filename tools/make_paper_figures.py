#!/usr/bin/env python3
"""Generate the two result figures for paper/main.tex from paper/numbers.json,
the same source main.tex reads its numbers from -- a visualization of the
reported values, not a re-analysis. Writes paper/figures/figures.stamp.json
recording every value drawn, so preflight fails if a value changes and the
figures are not regenerated.

Run: pixi run python tools/make_paper_figures.py"""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

PAPER = Path(__file__).resolve().parent.parent / "paper"
OUT = PAPER / "figures"
OUT.mkdir(parents=True, exist_ok=True)
VALUES = json.loads((PAPER / "numbers.json").read_text(encoding="utf-8"))["values"]
USED: dict[str, str] = {}


def val(key: str) -> str:
    USED[key] = VALUES[key]["value"]
    return VALUES[key]["value"]


def num(key: str) -> float:
    return float(val(key).replace("{,}", ""))


def row(label: str, prefix: str) -> tuple:
    return (label,
            num(f"{prefix}.control.rate"), num(f"{prefix}.control.ci_lo"), num(f"{prefix}.control.ci_hi"),
            num(f"{prefix}.treatment.rate"), num(f"{prefix}.treatment.ci_lo"), num(f"{prefix}.treatment.ci_hi"),
            f"p={val(prefix + '.p')}")

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
    row("Bibliography entry", "single.bib"),
    row("Inline citation", "single.cite"),
    row("Section reorder (K=1)", "single.secreorder_comb"),
    row("Section reorder (K=4)", "k4.secreorder"),
]
SIGNIFICANT = ROWS_1[3][7]

fig, ax = plt.subplots(figsize=(6.5, 2.6))
y = list(range(len(ROWS_1)))[::-1]
for yi, (label, c, clo, chi, t, tlo, thi, p) in zip(y, ROWS_1):
    ax.plot([clo, chi], [yi + 0.12, yi + 0.12], color=CONTROL_COLOR, lw=1.4, solid_capstyle="butt")
    ax.plot(c, yi + 0.12, "o", color=CONTROL_COLOR, ms=5, zorder=3)
    ax.plot([tlo, thi], [yi - 0.12, yi - 0.12], color=TREATMENT_COLOR, lw=1.4, solid_capstyle="butt")
    ax.plot(t, yi - 0.12, "s", color=TREATMENT_COLOR, ms=5, zorder=3)
    weight = "bold" if p == SIGNIFICANT else "normal"
    ax.text(102, yi, p, va="center", ha="left", fontsize=9, fontweight=weight)

ax.set_yticks(y)
ax.set_yticklabels([r[0] for r in ROWS_1])
ax.set_xlim(0, 124)
ax.set_xticks([0, 25, 50, 75, 100])
ax.set_xlabel("Pass rate (%), 95% CI")
ax.axvline(100, color="#dddddd", lw=0.8, zorder=0)
handles = [
    plt.Line2D([0], [0], marker="o", color=CONTROL_COLOR, linestyle="", label="Control (generic tools)"),
    plt.Line2D([0], [0], marker="s", color=TREATMENT_COLOR, linestyle="", label="Treatment (AnchorEdit)"),
]
ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0, -0.62), ncol=2, frameon=False, fontsize=9)
fig.tight_layout()
fig.savefig(OUT / "fig-single-edit-forest.pdf", bbox_inches="tight")
plt.close(fig)
print("wrote fig-single-edit-forest.pdf")

# ---------- Figure 2: render-gate before/after dumbbell ----------
# (family, orig_control, orig_treatment, clean_control, clean_treatment)
ROWS_2 = [
    (label, num(f"rg.{fam}.control.rate"), num(f"rg.{fam}.treatment.rate"),
     num(f"rgclean.{fam}.control.rate"), num(f"rgclean.{fam}.treatment.rate"))
    for label, fam in (("Equation", "equation"), ("Table (structural)", "table"), ("Caption", "caption"))
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

(OUT / "figures.stamp.json").write_text(
    json.dumps({"about": "Values each figure was drawn from; paper/consistency.py flags stale figures.",
                "values": dict(sorted(USED.items()))}, indent=1) + "\n", encoding="utf-8")
print(f"wrote figures.stamp.json ({len(USED)} values)")
