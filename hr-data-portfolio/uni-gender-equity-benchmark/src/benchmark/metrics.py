"""Benchmark metric definitions. One function per table; see docs/methodology.md."""
import numpy as np
import pandas as pd
from scipy import stats as sps
from statsmodels.stats.proportion import confint_proportions_2indep, proportion_confint, proportions_ztest

from . import config as c


def _sum(df, mask=None):
    df = df if mask is None else df[mask]
    return df.groupby("university")["n_employees"].sum()


def league(comp, move, year=c.LATEST):
    """One row per university for one reporting year: counts first, then the rates built from them."""
    d = comp[comp["reporting_year"] == year]
    m = move[move["reporting_year"] == year]
    w = d["gender"] == "Women"
    mgr = d["manager_category"] == "Manager"
    senior = d["occupation"].isin(c.SENIOR_TIERS)
    casual = d["employment_type"] == "Casual"
    pt = d["employment_status"] == "Part-time"
    t = pd.DataFrame({
        "headcount": _sum(d), "women": _sum(d, w),
        "managers": _sum(d, mgr), "women_managers": _sum(d, mgr & w),
        "senior": _sum(d, senior), "women_senior": _sum(d, senior & w),
        "casual": _sum(d, casual), "contract": _sum(d, d["employment_type"] == "Contract"),
        "noncasual_women": _sum(d, ~casual & w), "noncasual_men": _sum(d, ~casual & ~w),
        "pt_women": _sum(d, pt & w), "pt_men": _sum(d, pt & ~w),
        "pt_managers": _sum(d, pt & mgr),
    })
    nc = m["employment_type"] != "Casual"
    mw = m["gender"] == "Women"
    for key, label in [("promotions", "Promotions"), ("resignations", "Resignations"),
                       ("carer", "Primary carers leave")]:
        is_type = m["movement_type"] == label
        t[key] = _sum(m, is_type & nc)
        t[f"{key}_women"] = _sum(m, is_type & nc & mw)
    ext_mgr = (m["movement_type"] == "External appointments") & (m["manager_category"] == "Manager")
    t["ext_mgr_appts"] = _sum(m, ext_mgr)
    t["ext_mgr_appts_women"] = _sum(m, ext_mgr & mw)
    t = t.fillna(0).astype(int)

    nc_total = t["noncasual_women"] + t["noncasual_men"]
    t["women_share"] = t["women"] / t["headcount"]
    t["women_mgr_share"] = t["women_managers"] / t["managers"]
    t["women_senior_share"] = t["women_senior"] / t["senior"]
    t["leadership_gap_pts"] = (t["women_mgr_share"] - t["women_share"]) * 100
    t["manager_share"] = t["managers"] / t["headcount"]
    t["casual_share"] = t["casual"] / t["headcount"]
    t["contract_share"] = t["contract"] / t["headcount"]
    t["pt_share_women"] = t["pt_women"] / t["noncasual_women"]
    t["pt_share_men"] = t["pt_men"] / t["noncasual_men"]
    t["pt_mgr_share"] = t["pt_managers"] / t["managers"]
    t["women_noncasual_share"] = t["noncasual_women"] / nc_total
    t["women_promo_share"] = t["promotions_women"] / t["promotions"].replace(0, np.nan)
    t["promo_parity"] = t["women_promo_share"] / t["women_noncasual_share"]
    t["resign_rate_women"] = t["resignations_women"] / t["noncasual_women"]
    t["resign_rate_men"] = (t["resignations"] - t["resignations_women"]) / t["noncasual_men"]
    t["men_carer_share"] = 1 - t["carer_women"] / t["carer"].replace(0, np.nan)
    t["women_ext_mgr_share"] = t["ext_mgr_appts_women"] / t["ext_mgr_appts"].replace(0, np.nan)
    return t


# (key, label, numerator, denominator, higher is better?)  None = neither direction is "better"
HEADLINE = [
    ("women_share", "Women as share of all employees", None),
    ("women_mgr_share", "Women as share of managers", True),
    ("women_senior_share", "Women as share of senior management", True),
    ("leadership_gap_pts", "Leadership gap (managers minus workforce, pts)", True),
    ("casual_share", "Casual share of headcount", None),
    ("contract_share", "Fixed-term contract share of headcount", None),
    ("promo_parity", "Promotion parity ratio", True),
    ("men_carer_share", "Men's share of primary carer's leave", True),
    ("pt_mgr_share", "Managers working part-time", True),
]
POOLED = {  # how the sector-wide (pooled) value of each rate is built from the summed counts
    "women_share": ("women", "headcount"), "women_mgr_share": ("women_managers", "managers"),
    "women_senior_share": ("women_senior", "senior"), "casual_share": ("casual", "headcount"),
    "contract_share": ("contract", "headcount"), "pt_mgr_share": ("pt_managers", "managers"),
}


def sector_pooled(t, exclude=None):
    """Sector values from pooled counts (every employee counts once), optionally leaving one university out."""
    s = (t.drop(index=exclude) if exclude else t).sum(numeric_only=True)
    out = {k: s[n] / s[d] for k, (n, d) in POOLED.items()}
    out["leadership_gap_pts"] = (out["women_mgr_share"] - out["women_share"]) * 100
    nc = s["noncasual_women"] + s["noncasual_men"]
    out["promo_parity"] = (s["promotions_women"] / s["promotions"]) / (s["noncasual_women"] / nc)
    out["men_carer_share"] = 1 - s["carer_women"] / s["carer"] if s["carer"] else np.nan
    return out


def scorecard(t, focus):
    """Focus university against the sector: value, pooled sector value, median, rank."""
    pooled = sector_pooled(t)
    rows = []
    for key, label, higher_better in HEADLINE:
        col = t[key].dropna()
        rows.append({"metric": label, "key": key, "focus": t.loc[focus, key], "sector_pooled": pooled[key],
                     "sector_median": col.median(),
                     "rank": int(col.rank(ascending=False, method="min")[focus]), "of": len(col),
                     "higher_is_better": higher_better})
    return pd.DataFrame(rows).set_index("key")


def tiers(comp, focus, year=c.LATEST):
    """Women's share at each management tier and among non-managers: focus university vs the rest."""
    d = comp[comp["reporting_year"] == year].copy()
    d["tier"] = np.where(d["manager_category"] == "Manager", d["occupation"], "Non-managers")
    d["group"] = np.where(d["university"] == focus, "focus", "rest")
    g = d.pivot_table(index="tier", columns=["group", "gender"], values="n_employees", aggfunc="sum", fill_value=0)
    out = pd.DataFrame(index=[x for x in c.MANAGER_TIERS + ["Non-managers"] if x in g.index])
    for grp in ("focus", "rest"):
        women, men = g[(grp, "Women")].reindex(out.index), g[(grp, "Men")].reindex(out.index)
        out[f"{grp}_n"] = women + men
        out[f"{grp}_women"] = women
        out[f"{grp}_share"] = women / (women + men)
        lo, hi = proportion_confint(women, women + men, method="wilson")
        out[f"{grp}_lo"], out[f"{grp}_hi"] = lo, hi
    return out


def trend(comp, move, focus, panel):
    """Three-year trend for the focus university and the balanced-panel sector (pooled)."""
    rows = []
    for year in c.YEARS:
        t = league(comp[comp["university"].isin(panel)], move[move["university"].isin(panel)], year)
        pooled = sector_pooled(t)
        for key in ("women_share", "women_mgr_share", "women_senior_share", "casual_share"):
            rows.append({"year": year, "metric": key, "focus": t.loc[focus, key], "sector": pooled[key]})
    return pd.DataFrame(rows)


# ---------- statistics ----------

def funnel(t, num="women_managers", den="managers"):
    """Funnel-plot data: each university's rate against binomial control limits around the sector rate.

    A university outside the 99.8% limits differs from the sector by more than chance
    alone would produce given its size; inside the limits, rank differences are noise.
    """
    p0 = t[num].sum() / t[den].sum()
    out = t[[num, den]].rename(columns={num: "k", den: "n"}).copy()
    out["rate"] = out["k"] / out["n"]
    se = np.sqrt(p0 * (1 - p0) / out["n"])
    out["z"] = (out["rate"] - p0) / se
    out["signal"] = np.select([out["z"] > 3.09, out["z"] < -3.09, out["z"].abs() > 1.96],
                              ["Above sector (99.8%)", "Below sector (99.8%)", "Outside 95% only"], "Consistent with sector")
    return out.sort_values("rate", ascending=False), p0


def focus_vs_rest(t, focus, num, den):
    """Two-proportion z-test: focus university against all other universities pooled."""
    k1, n1 = t.loc[focus, num], t.loc[focus, den]
    rest = t.drop(index=focus)
    k0, n0 = rest[num].sum(), rest[den].sum()
    z, p = proportions_ztest([k1, k0], [n1, n0])
    lo, hi = confint_proportions_2indep(k1, n1, k0, n0, method="wald")
    return {"focus": k1 / n1, "rest": k0 / n0, "diff": k1 / n1 - k0 / n0, "ci_low": lo, "ci_high": hi,
            "z": z, "p": p, "n_focus": int(n1), "n_rest": int(n0)}


def gender_by_tier_test(comp, focus, year=c.LATEST):
    """Chi-square test: is gender independent of level (non-manager / other manager / senior) at the focus university?"""
    d = comp[(comp["reporting_year"] == year) & (comp["university"] == focus)].copy()
    d["level"] = np.select([d["occupation"].isin(c.SENIOR_TIERS), d["manager_category"] == "Manager"],
                           ["Senior management", "Other managers"], "Non-managers")
    tab = d.pivot_table(index="level", columns="gender", values="n_employees", aggfunc="sum", fill_value=0)
    tab = tab.reindex(["Non-managers", "Other managers", "Senior management"])
    chi2, p, dof, _ = sps.chi2_contingency(tab)
    n = tab.to_numpy().sum()
    return {"table": tab, "chi2": chi2, "p": p, "dof": dof, "cramers_v": np.sqrt(chi2 / (n * (min(tab.shape) - 1)))}


def promotion_parity_test(comp, move, focus, years=c.YEARS):
    """Exact binomial test: do women receive promotions in proportion to their share of non-casual staff?

    Pools the available years because one university's annual promotion count is small.
    """
    d = comp[(comp["university"] == focus) & comp["reporting_year"].isin(years) & (comp["employment_type"] != "Casual")]
    m = move[(move["university"] == focus) & move["reporting_year"].isin(years)
             & (move["movement_type"] == "Promotions") & (move["employment_type"] != "Casual")]
    expected = d.loc[d["gender"] == "Women", "n_employees"].sum() / d["n_employees"].sum()
    k, n = int(m.loc[m["gender"] == "Women", "n_employees"].sum()), int(m["n_employees"].sum())
    res = sps.binomtest(k, n, expected)
    lo, hi = proportion_confint(k, n, method="wilson")
    return {"promotions": n, "to_women": k, "share": k / n, "expected": expected, "ci_low": lo, "ci_high": hi,
            "p": res.pvalue, "parity": (k / n) / expected}


def parity_arithmetic(t, focus):
    """How many senior roles would need to be held by women to reach each benchmark, at current size."""
    r = t.loc[focus]
    targets = {"Sector average": t["women_senior"].sum() / t["senior"].sum(), "50%": 0.5,
               "Own workforce share": r["women_share"]}
    return pd.DataFrame([{"benchmark": k, "target_share": v, "women_needed": int(np.ceil(v * r["senior"])),
                          "additional": max(0, int(np.ceil(v * r["senior"])) - int(r["women_senior"]))}
                         for k, v in targets.items()]).set_index("benchmark")
