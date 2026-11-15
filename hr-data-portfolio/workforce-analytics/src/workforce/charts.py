"""Chart builders. One function per figure; each returns the saved path.

House style: one message per chart, thin marks, direct labels in neutral ink,
recessive grid, colour used only to carry identity (fixed order) or emphasis.
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator, PercentFormatter

from . import config as c

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
BLUE_LIGHT = "#9ec5f4"
INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
TYPE_COLOURS = {"Ongoing": BLUE, "Fixed-term": ORANGE, "Casual": AQUA}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "text.color": INK, "axes.labelcolor": INK2,
    "axes.edgecolor": AXIS, "axes.spines.top": False, "axes.spines.right": False,
    "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK2, "ytick.labelcolor": INK2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "figure.facecolor": "white", "axes.facecolor": "white", "savefig.dpi": 200,
    "legend.frameon": False, "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlelocation": "left",
})


def _save(fig, name):
    c.FIGS.mkdir(parents=True, exist_ok=True)
    path = c.FIGS / f"{name}.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _hbar_axes(ax):
    ax.grid(axis="y", visible=False)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.invert_yaxis()


def headcount_by_division(summary):
    fig, ax = plt.subplots(figsize=(8, 4.4))
    left = 0
    for t in c.EMPLOYMENT_TYPES:
        ax.barh(summary.index, summary[t], left=left, height=0.6, color=TYPE_COLOURS[t], label=t,
                edgecolor="white", linewidth=1.2)
        left = left + summary[t]
    for y, total in enumerate(summary["headcount"]):
        ax.text(total + 6, y, f"{total:,}", va="center", color=INK2, fontsize=9)
    _hbar_axes(ax)
    ax.set_xlabel("Headcount")
    ax.set_xlim(0, summary["headcount"].max() * 1.1)
    ax.legend(ncols=3, loc="lower right", fontsize=9)
    return _save(fig, "headcount_by_division")


def turnover_trend(trend):
    fig, ax = plt.subplots(figsize=(6.2, 3.8))
    for col, colour, label in [("total_rate", BLUE, "All separations"), ("voluntary_rate", ORANGE, "Resignations")]:
        ax.plot(trend.index, trend[col], color=colour, linewidth=2, marker="o", markersize=6,
                markeredgecolor="white", markeredgewidth=1.5, label=label)
        for x, v in trend[col].items():
            ax.annotate(f"{v:.1%}", (x, v), textcoords="offset points", xytext=(0, 9), ha="center",
                        fontsize=9, color=INK2)
    ax.set_xticks(list(trend.index))
    ax.set_ylim(0, trend["total_rate"].max() * 1.25)
    ax.yaxis.set_major_locator(MultipleLocator(0.05))
    ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    ax.grid(axis="x", visible=False)
    ax.set_ylabel("Annual rate (non-casual staff)")
    ax.legend(loc="lower left", fontsize=9, ncols=2)
    return _save(fig, "turnover_trend")


def resignation_by_division(rates, overall):
    """rates: Series of pooled resignation rates indexed by division."""
    rates = rates.sort_values(ascending=False)
    fig, ax = plt.subplots(figsize=(6.2, 4.2))
    colours = [BLUE if v == rates.max() else BLUE_LIGHT for v in rates]
    ax.barh(rates.index, rates, height=0.6, color=colours, zorder=2)
    white = dict(facecolor="white", edgecolor="none", pad=1.5)
    for y, v in enumerate(rates):
        ax.text(v + 0.002, y, f"{v:.1%}", va="center", fontsize=9, color=INK2, bbox=white, zorder=4)
    ax.axvline(overall, color=INK2, linewidth=1, linestyle=(0, (4, 3)), zorder=3)
    ax.text(overall + 0.002, -0.75, f"University average {overall:.1%}", ha="left", va="center", fontsize=8.5, color=INK2)
    ax.set_ylim(-1.1, len(rates) - 0.5)
    _hbar_axes(ax)
    ax.set_xlim(0, rates.max() * 1.18)
    ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    ax.set_xlabel(f"Resignation rate, pooled {c.REPORT_YEARS[0]}-{c.REPORT_YEARS[-1]}")
    return _save(fig, "resignation_by_division")


def odds_ratios(tab):
    tab = tab.sort_values("odds_ratio")
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    y = range(len(tab))
    sig = tab["p_value"] < 0.05
    for i, (_, r) in enumerate(tab.iterrows()):
        colour = BLUE if sig.iloc[i] else MUTED
        ax.plot([r["ci_low"], r["ci_high"]], [i, i], color=colour, linewidth=2, solid_capstyle="round")
        ax.plot(r["odds_ratio"], i, "o", color=colour, markersize=8, markeredgecolor="white", markeredgewidth=1.5)
        ax.text(tab["ci_high"].max() * 1.04, i, f"{r['odds_ratio']:.2f}", va="center", fontsize=9, color=INK2)
    ax.axvline(1, color=INK2, linewidth=1)
    ax.set_yticks(list(y), tab.index)
    ax.grid(axis="y", visible=False)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_xlim(tab["ci_low"].min() * 0.9, tab["ci_high"].max() * 1.14)
    ax.set_xlabel("Odds ratio for resigning within the year (bar = 95% CI; blue = significant at 5%)")
    return _save(fig, "resignation_odds_ratios")


def women_by_level(tab):
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6), sharey=True, gridspec_kw={"width_ratios": [5, 8]})
    for ax, levels, title in [(axes[0], c.ACADEMIC_LEVELS, "Academic"), (axes[1], c.PROFESSIONAL_LEVELS, "Professional")]:
        share = tab.loc[levels, "women_share"]
        colours = [BLUE if lv in c.SENIOR_LEVELS else BLUE_LIGHT for lv in levels]
        ax.bar(levels, share, width=0.6, color=colours)
        for x, v in enumerate(share):
            ax.text(x, v + 0.015, f"{v:.0%}", ha="center", fontsize=9, color=INK2)
        ax.axhline(0.5, color=INK2, linewidth=1, linestyle=(0, (4, 3)))
        ax.set_title(title)
        ax.grid(axis="x", visible=False)
        ax.set_ylim(0, 0.9)
        ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
        ax.tick_params(axis="x", labelsize=8.5)
    axes[0].set_ylabel("Women as share of headcount")
    axes[1].text(len(c.PROFESSIONAL_LEVELS) - 0.55, 0.51, "50%", fontsize=8.5, color=INK2, va="bottom", ha="right")
    fig.tight_layout()
    return _save(fig, "women_by_level")


def indigenous_representation(history, scenarios, base_year):
    """history: metrics.indigenous_representation(); scenarios: {label: scenario DataFrame}."""
    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    ax.fill_between(history["year"], history["ci_low"], history["ci_high"], color=BLUE, alpha=0.15, linewidth=0)
    ax.plot(history["year"], history["share"], color=BLUE, linewidth=2, marker="o", markersize=6,
            markeredgecolor="white", markeredgewidth=1.5)
    last = history.iloc[-1]
    ax.annotate(f"{last['share']:.1%}", (last["year"], last["share"]), textcoords="offset points",
                xytext=(0, -15), ha="center", fontsize=9, color=INK2)
    for (label, sc), colour in zip(scenarios.items(), [MUTED, ORANGE, AQUA]):
        sc = sc[sc["year"] <= 5]
        ax.plot(base_year + sc["year"], sc["share"], color=colour, linewidth=2, linestyle=(0, (4, 2)))
        ax.text(base_year + sc["year"].iloc[-1] + 0.1, sc["share"].iloc[-1], label, va="center", fontsize=8.5, color=INK2)
    ax.axhline(c.INDIGENOUS_TARGET, color=INK2, linewidth=1)
    ax.text(history["year"].min(), c.INDIGENOUS_TARGET + 0.0008, f"Target {c.INDIGENOUS_TARGET:.0%}",
            fontsize=8.5, color=INK2)
    ax.set_xlim(history["year"].min() - 0.3, base_year + 7.2)
    ax.set_xticks(range(int(history["year"].min()), base_year + 6))
    ax.set_ylim(0, 0.056)
    ax.yaxis.set_major_locator(MultipleLocator(0.01))
    ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    ax.grid(axis="x", visible=False)
    ax.set_ylabel("Share of headcount")
    return _save(fig, "indigenous_representation")


def retirement_exposure(tab):
    tab = tab.sort_values("share", ascending=False)
    fig, ax = plt.subplots(figsize=(6.2, 4.2))
    colours = [BLUE if v == tab["share"].max() else BLUE_LIGHT for v in tab["share"]]
    ax.barh(tab.index, tab["share"], height=0.6, color=colours)
    for y, (v, n) in enumerate(zip(tab["share"], tab["reaching_65"])):
        label = f"{v:.0%}  ({n} staff)" if n >= c.SMALL_CELL_THRESHOLD else f"{v:.0%}  (<{c.SMALL_CELL_THRESHOLD} staff)"
        ax.text(v + 0.002, y, label, va="center", fontsize=9, color=INK2)
    _hbar_axes(ax)
    ax.set_xlim(0, tab["share"].max() * 1.35)
    ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    ax.set_xlabel("Ongoing staff reaching age 65 within five years")
    return _save(fig, "retirement_exposure")
