"""Workforce metric definitions.

Each function implements one definition from docs/methodology.md. They take the
clean employee table and return tidy DataFrames, so the same numbers feed the
charts, the slide deck and the reconciliation tests for the Excel workbook.
"""
import numpy as np
import pandas as pd
from statsmodels.stats.proportion import proportion_confint

from . import config as c


def active_on(df, date):
    """Staff employed at close of business on `date` (end_date is the last day worked)."""
    date = pd.Timestamp(date)
    return df[(df["start_date"] <= date) & (df["end_date"].isna() | (df["end_date"] > date))]


def headcount_summary(df, date=c.SNAPSHOT, by="division"):
    snap = active_on(df, date)
    out = snap.groupby(by).agg(headcount=("employee_id", "size"), fte=("fte", "sum"))
    types = snap.pivot_table(index=by, columns="employment_type", values="employee_id",
                             aggfunc="size", fill_value=0).reindex(columns=c.EMPLOYMENT_TYPES, fill_value=0)
    out = out.join(types)
    out["fte"] = out["fte"].round(1)
    return out.sort_values("headcount", ascending=False)


def headcount_trend(df, years=None):
    years = years or [min(c.REPORT_YEARS) - 1] + c.REPORT_YEARS
    rows = []
    for y in years:
        snap = active_on(df, f"{y}-12-31")
        rows.append({"as_at": f"31 Dec {y}", "year": y, "headcount": len(snap), "fte": round(snap["fte"].sum(), 1)})
    return pd.DataFrame(rows)


def turnover(df, year, by=None, include_casual=False):
    """Annual separation rates = separations in year / average of opening and closing headcount.

    Casual staff are excluded by default (standard practice: casual engagements end by design).
    `voluntary_rate` counts resignations only.
    """
    pop = df if include_casual else df[df["employment_type"] != "Casual"]
    opening = active_on(pop, f"{year - 1}-12-31")
    closing = active_on(pop, f"{year}-12-31")
    seps = pop[pop["end_date"].dt.year == year]
    vol = seps[seps["separation_reason"].isin(c.VOLUNTARY_REASONS)]

    def count(frame):
        return frame.groupby(by).size() if by else pd.Series({"All staff": len(frame)})

    out = pd.DataFrame({"opening": count(opening), "closing": count(closing),
                        "separations": count(seps), "voluntary": count(vol)}).fillna(0)
    out["avg_headcount"] = (out["opening"] + out["closing"]) / 2
    out["total_rate"] = out["separations"] / out["avg_headcount"]
    out["voluntary_rate"] = out["voluntary"] / out["avg_headcount"]
    out.insert(0, "year", year)
    return out


def turnover_trend(df, years=c.REPORT_YEARS):
    return pd.concat([turnover(df, y) for y in years]).set_index("year")


def gender_by_level(df, date=c.SNAPSHOT):
    snap = active_on(df, date)
    tab = snap.pivot_table(index="classification", columns="gender", values="employee_id",
                           aggfunc="size", fill_value=0).reindex(index=c.LEVELS, columns=c.GENDERS, fill_value=0)
    tab["total"] = tab.sum(axis=1)
    tab["women_share"] = tab["Woman"] / tab["total"]
    return tab


def women_in_senior_roles(df, date=c.SNAPSHOT):
    snap = active_on(df, date)
    senior = snap[snap["classification"].isin(c.SENIOR_LEVELS)]
    return {"women_share_all": (snap["gender"] == "Woman").mean(),
            "women_share_senior": (senior["gender"] == "Woman").mean(),
            "senior_headcount": len(senior)}


def gender_pay_gap(df, date=c.SNAPSHOT):
    """Gender pay gap on FTE-annualised base salary, non-casual staff.

    gap = (mean men - mean women) / mean men.
    `like_for_like` re-weights the within-classification gaps by women's headcount,
    which removes the effect of men and women being distributed differently across levels.
    """
    snap = active_on(df, date)
    snap = snap[(snap["employment_type"] != "Casual") & snap["gender"].isin(["Woman", "Man"])]
    mean = snap.groupby("gender")["base_salary_fte"].mean()
    overall = (mean["Man"] - mean["Woman"]) / mean["Man"]

    by_level = snap.pivot_table(index="classification", columns="gender", values="base_salary_fte",
                                aggfunc=["mean", "size"]).reindex(c.LEVELS)
    lv = pd.DataFrame({"men_mean": by_level[("mean", "Man")], "women_mean": by_level[("mean", "Woman")],
                       "men_n": by_level[("size", "Man")], "women_n": by_level[("size", "Woman")]})
    lv["gap"] = (lv["men_mean"] - lv["women_mean"]) / lv["men_mean"]
    comparable = lv.dropna(subset=["gap"])  # levels where both women and men are employed
    like_for_like = np.average(comparable["gap"], weights=comparable["women_n"])
    return {"overall": overall, "like_for_like": like_for_like, "structural": overall - like_for_like,
            "men_mean": mean["Man"], "women_mean": mean["Woman"], "by_level": lv}


def indigenous_representation(df, dates=None):
    """Share of headcount identifying as Aboriginal and/or Torres Strait Islander, with a 95% Wilson interval.

    Staff who have not disclosed stay in the denominator (the conservative convention).
    """
    dates = dates or [f"{y}-12-31" for y in [min(c.REPORT_YEARS) - 1] + c.REPORT_YEARS]
    rows = []
    for d in dates:
        snap = active_on(df, d)
        k, n = int((snap["indigenous_status"] == c.INDIGENOUS_YES).sum()), len(snap)
        lo, hi = proportion_confint(k, n, method="wilson")
        rows.append({"year": pd.Timestamp(d).year, "identified": k, "headcount": n, "share": k / n,
                     "ci_low": lo, "ci_high": hi,
                     "not_disclosed_share": (snap["indigenous_status"] == "Not disclosed").mean()})
    return pd.DataFrame(rows)


def age_profile(df, date=c.SNAPSHOT, by="division"):
    snap = active_on(df, date)
    snap = snap[snap["employment_type"] != "Casual"].copy()
    snap["age_now"] = np.floor((pd.Timestamp(date) - snap["date_of_birth"]).dt.days / 365.25)
    out = snap.groupby(by).agg(headcount=("employee_id", "size"), median_age=("age_now", "median"),
                               aged_55_plus=("age_now", lambda s: (s >= c.RETIREMENT_AGE_FLAG).sum()),
                               aged_60_plus=("age_now", lambda s: (s >= 60).sum()))
    out["share_55_plus"] = out["aged_55_plus"] / out["headcount"]
    out["share_60_plus"] = out["aged_60_plus"] / out["headcount"]
    return out.sort_values("share_55_plus", ascending=False)


def suppress_small_cells(table, threshold=c.SMALL_CELL_THRESHOLD):
    """Replace counts of 1 to threshold-1 with '<threshold>' before a table is published.

    Zero is retained; only small non-zero counts can identify individuals.
    """
    def fix(v):
        if isinstance(v, (int, np.integer)) and 0 < v < threshold:
            return f"<{threshold}"
        return v
    return table.map(fix)
