"""Load the higher-education extract and apply the rules that make it safe to compare.

Five things in the published files would silently distort a benchmark if left alone:

1. The 2022-23 movements file contains subtotal rows ("Total appointments ...")
   alongside their components. Summing the file double-counts appointments.
2. "Promotions from non-manager to manager" exists only in 2024-25. It is kept as
   its own category and left out of promotion counts so the three years stay comparable.
3. The Higher Education industry class includes pathway colleges, medical colleges
   and university subsidiaries. Only universities are benchmarked.
4. Not every university appears in every year. Trends use the balanced panel only.
5. A few managers are reported as 'Heads of Business', a tier most universities do not use.
"""
import pandas as pd

from . import config as c

SUBTOTAL_PREFIX = "Total appointments"
PROMO_NEW = "Promotions from non-manager to manager"


def tidy_name(name):
    """'The University Of Queensland' -> 'University of Queensland'."""
    name = name.replace(" Limited", "").replace(" Of ", " of ").replace(" The ", " the ").replace(" And ", " and ")
    return name[4:] if name.startswith("The ") else name


def _universities(comp):
    """ABNs treated as universities, judged on the most recent year each one reports."""
    last = comp.sort_values("reporting_year").groupby("employer_abn").agg(
        name=("employer_name", "last"), year=("reporting_year", "last"))
    size = comp.groupby(["employer_abn", "reporting_year"])["n_employees"].sum()
    last["headcount"] = [size[(abn, yr)] for abn, yr in zip(last.index, last["year"])]
    is_uni = (last["name"].str.contains("University")
              & ~last["name"].str.contains("|".join(c.SUBSIDIARY_WORDS))
              & (last["headcount"] >= c.MIN_UNIVERSITY_HEADCOUNT))
    return last[is_uni]


def load():
    """Return (composition, movements, notes). Both tables are restricted to universities."""
    comp = pd.read_csv(c.COMPOSITION)
    move = pd.read_csv(c.MOVEMENTS)
    notes = {"he_employers": comp["employer_abn"].nunique()}

    subtotal = move["movement_type"].str.startswith(SUBTOTAL_PREFIX)
    notes["subtotal_rows_removed"] = int(subtotal.sum())
    notes["subtotal_employees_removed"] = int(move.loc[subtotal, "n_employees"].sum())
    move = move[~subtotal]

    # 'Heads of Business' (the most senior manager of a business unit) is reported by a handful of
    # universities. It is folded into the CEO tier so no manager falls outside the tier tables.
    hob = comp["occupation"] == "Heads of Business"
    notes["heads_of_business_recoded"] = int(comp.loc[hob, "n_employees"].sum())
    comp.loc[hob, "occupation"] = "CEOs"

    unis = _universities(comp)
    names = unis["name"].map(tidy_name)
    notes["universities"] = len(unis)
    out = []
    for df in (comp, move):
        df = df[df["employer_abn"].isin(unis.index)].copy()
        df["university"] = df["employer_abn"].map(names)   # one stable name per ABN across years
        out.append(df.drop(columns=["employer_name"]))
    comp, move = out

    years_present = comp.groupby("university")["reporting_year"].nunique()
    notes["balanced_panel"] = sorted(years_present[years_present == len(c.YEARS)].index)
    notes["partial"] = {u: sorted(comp.loc[comp["university"] == u, "reporting_year"].unique())
                        for u in years_present[years_present < len(c.YEARS)].index}
    notes["focus"] = tidy_name(c.FOCUS)
    return comp, move, notes
