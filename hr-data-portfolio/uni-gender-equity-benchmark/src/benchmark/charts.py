"""Chart builders: one message per chart, thin marks, neutral labels, colour only for identity or emphasis."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MultipleLocator, PercentFormatter

from . import config as c

BLUE, ORANGE, AQUA, BLUE_LIGHT = "#2a78d6", "#eb6834", "#1baf7a", "#9ec5f4"
INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
TYPE_COLOURS = {"Permanent": BLUE, "Contract": ORANGE, "Casual": AQUA}
F = c.FOCUS_SHORT

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "text.color": INK, "axes.labelcolor": INK2,
    "axes.edgecolor": AXIS, "axes.spines.top": False, "axes.spines.right": False,
    "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK2, "ytick.labelcolor": INK2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "figure.facecolor": "white", "axes.facecolor": "white", "savefig.dpi": 200, "legend.frameon": False,
})
PCT0 = PercentFormatter(1, decimals=0)
WHITE = dict(facecolor="white", edgecolor="none", pad=1.5)


def _save(fig, name):
    c.FIGS.mkdir(parents=True, exist_ok=True)
    path = c.FIGS / f"{name}.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def tiers(tab):
    """Women's share at each level, focus university vs the rest, with 95% intervals."""
    tab = tab.drop(index="CEOs", errors="ignore")
    fig, ax = plt.subplots(figsize=(7.4, 3.9))
    y = np.arange(len(tab))
    for grp, colour, label, off in [("focus", BLUE, F, -0.14), ("rest", ORANGE, "All other universities", 0.14)]:
        ax.hlines(y + off, tab[f"{grp}_lo"], tab[f"{grp}_hi"], color=colour, linewidth=2)
        ax.plot(tab[f"{grp}_share"], y + off, "o", color=colour, markersize=8, markeredgecolor="white",
                markeredgewidth=1.5, label=label)
    for i, (_, r) in enumerate(tab.iterrows()):
        ax.text(0.91, i - 0.14, f"{r['focus_share']:.0%}  (n = {int(r['focus_n']):,})", va="center", fontsize=9, color=INK2,
                clip_on=False)
    ax.axvline(0.5, color=INK2, linewidth=1, linestyle=(0, (4, 3)))
    ax.set_yticks(y, [c.TIER_LABELS.get(i, i) for i in tab.index])
    ax.invert_yaxis()
    ax.set_xlim(0.2, 0.9)
    ax.xaxis.set_major_locator(MultipleLocator(0.1))
    ax.xaxis.set_major_formatter(PCT0)
    ax.grid(axis="y", visible=False)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_xlabel(f"Women as share of employees at each level (bar = 95% interval; label = {F})")
    ax.legend(loc="upper center", bbox_to_anchor=(0.4, 1.12), ncols=2, fontsize=9)
    return _save(fig, "women_by_tier")


def funnel(fun, p0, focus, xlabel, name):
    fig, ax = plt.subplots(figsize=(7.4, 4.1))
    n = np.geomspace(max(20, fun["n"].min() * 0.8), fun["n"].max() * 1.9, 300)
    for z, style in [(1.96, (0, (4, 3))), (3.09, "solid")]:
        se = np.sqrt(p0 * (1 - p0) / n)
        ax.plot(n, p0 + z * se, color=MUTED, linewidth=1, linestyle=style)
        ax.plot(n, p0 - z * se, color=MUTED, linewidth=1, linestyle=style)
    ax.axhline(p0, color=INK2, linewidth=1)
    others = fun.drop(index=focus)
    ax.scatter(others["n"], others["rate"], s=42, color=BLUE_LIGHT, edgecolor="white", linewidth=1, zorder=3)
    r = fun.loc[focus]
    ax.scatter([r["n"]], [r["rate"]], s=90, color=BLUE, edgecolor="white", linewidth=1.5, zorder=4)
    ax.annotate(f"{F}  {r['rate']:.1%}", (r["n"], r["rate"]), textcoords="offset points", xytext=(-10, 9), ha="right",
                fontsize=9.5, color=INK, fontweight="bold", bbox=WHITE, zorder=5)
    ax.text(n[-1], p0 + 0.006, f"Sector {p0:.1%}", ha="right", fontsize=8.5, color=INK2)
    for zlim, label in [(1.96, "95% limit"), (3.09, "99.8% limit")]:
        ax.text(n[0] * 1.04, p0 + zlim * np.sqrt(p0 * (1 - p0) / n[0]) + 0.008, label, fontsize=8, color=MUTED)
    ax.set_xscale("log")
    ax.set_xticks([50, 100, 200, 500, 1000], ["50", "100", "200", "500", "1,000"])
    ax.set_xlim(n[0], n[-1] * 1.03)
    ax.minorticks_off()
    ax.set_ylim(0.25, 0.78)
    ax.yaxis.set_major_formatter(PCT0)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Women's share")
    return _save(fig, name)


def trend(tr, metric="women_senior_share"):
    d = tr[tr["metric"] == metric]
    fig, ax = plt.subplots(figsize=(6.2, 3.8))
    for col, colour, label, dy in [("focus", BLUE, F, -15), ("sector", ORANGE, "Sector (36 universities)", 9)]:
        ax.plot(d["year"], d[col], color=colour, linewidth=2, marker="o", markersize=7, markeredgecolor="white",
                markeredgewidth=1.5, label=label)
        for x, v in zip(d["year"], d[col]):
            ax.annotate(f"{v:.1%}", (x, v), textcoords="offset points", xytext=(0, dy), ha="center", fontsize=9, color=INK2)
    ax.set_ylim(0.40, 0.54)
    ax.yaxis.set_major_locator(MultipleLocator(0.02))
    ax.yaxis.set_major_formatter(PCT0)
    ax.grid(axis="x", visible=False)
    ax.set_ylabel("Women's share of senior management")
    ax.legend(loc="lower right", fontsize=9)
    ax.margins(x=0.12)
    return _save(fig, "senior_share_trend")


def manager_share(league, focus):
    s = league["manager_share"].sort_values()
    fig, ax = plt.subplots(figsize=(7.4, 3.6))
    colours = [BLUE if u == focus else BLUE_LIGHT for u in s.index]
    ax.bar(range(len(s)), s, width=0.72, color=colours)
    i = list(s.index).index(focus)
    ax.annotate(f"{F}  {s[focus]:.0%}", (i, s[focus]), textcoords="offset points", xytext=(0, 6), ha="center",
                fontsize=9.5, fontweight="bold")
    ax.axhline(s.median(), color=INK2, linewidth=1, linestyle=(0, (4, 3)))
    ax.text(0, s.median() + 0.006, f"Median {s.median():.0%}", fontsize=8.5, color=INK2)
    ax.set_xticks([])
    ax.set_ylim(0, s.max() * 1.15)
    ax.set_xlabel(f"{len(s)} universities, lowest to highest")
    ax.set_ylabel("Employees reported as managers")
    ax.yaxis.set_major_formatter(PCT0)
    ax.grid(axis="x", visible=False)
    return _save(fig, "manager_share_by_university")


def promotions(by_year, pooled):
    labels = list(by_year) + ["3 years\npooled"]
    rows = list(by_year.values()) + [pooled]
    fig, ax = plt.subplots(figsize=(6.2, 3.8))
    x = np.arange(len(rows))
    for i, r in enumerate(rows):
        colour = BLUE if i == len(rows) - 1 else BLUE_LIGHT
        ax.vlines(i, r["ci_low"], r["ci_high"], color=colour, linewidth=2.5)
        ax.plot(i, r["share"], "o", color=BLUE, markersize=9, markeredgecolor="white", markeredgewidth=1.5, zorder=3)
        ax.text(i + 0.1, r["share"] - 0.012, f"{r['share']:.0%}\nn = {r['promotions']}", va="top", fontsize=9, color=INK2)
        ax.hlines(r["expected"], i - 0.3, i + 0.3, color=ORANGE, linewidth=2)
    ax.plot([], [], "o", color=BLUE, label="Women's share of promotions (95% interval)")
    ax.plot([], [], color=ORANGE, linewidth=2, label="Women's share of non-casual staff")
    ax.set_xticks(x, labels)
    ax.set_xlim(-0.5, len(rows) - 0.3)
    ax.set_ylim(0.38, 0.74)
    ax.yaxis.set_major_formatter(PCT0)
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper left", fontsize=8.5)
    return _save(fig, "promotion_parity")


def employment_mix(mix):
    fig, ax = plt.subplots(figsize=(7.4, 2.2))
    left = np.zeros(len(mix))
    for t in c.EMPLOYMENT_TYPES:
        ax.barh(mix.index, mix[t], left=left, height=0.55, color=TYPE_COLOURS[t], edgecolor="white", linewidth=1.5, label=t)
        for i, v in enumerate(mix[t]):
            ax.text(left[i] + v / 2, i, f"{v:.0%}", ha="center", va="center", fontsize=9.5,
                    color="white", fontweight="bold")
        left = left + mix[t].to_numpy()
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(PCT0)
    ax.grid(visible=False)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.legend(ncols=3, loc="upper center", bbox_to_anchor=(0.5, 1.3), fontsize=9)
    return _save(fig, "employment_mix")


def build_all(r):
    return {
        "tiers": tiers(r["tiers"]),
        "funnel": funnel(r["funnel_senior"], r["sector_senior"], r["focus"],
                         "Number of senior management roles (log scale)", "funnel_senior_management"),
        "trend": trend(r["trend"]),
        "manager_share": manager_share(r["league"], r["focus"]),
        "promotions": promotions(r["promo_by_year"], r["promo_pooled"]),
        "mix": employment_mix(r["mix"]),
    }
