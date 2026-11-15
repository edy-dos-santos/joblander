"""Statistical analysis: tests, a resignation model and two simple forward-looking models."""
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats as sps
from statsmodels.stats.proportion import confint_proportions_2indep, proportions_ztest

from . import config as c
from .metrics import active_on


def person_years(df, years=c.REPORT_YEARS):
    """One row per non-casual staff member per year they started the year employed.

    Outcome `resigned` = 1 if they resigned during that year. Characteristics are
    measured at 1 January so the model only uses information available in advance.
    """
    frames = []
    for y in years:
        start = pd.Timestamp(f"{y - 1}-12-31")
        pop = active_on(df, start)
        pop = pop[pop["employment_type"] != "Casual"].copy()
        pop["year"] = y
        pop["resigned"] = ((pop["end_date"].dt.year == y) & (pop["separation_reason"] == "Resignation")).astype(int)
        pop["age"] = (start - pop["date_of_birth"]).dt.days / 365.25
        pop["tenure"] = (start - pop["start_date"]).dt.days / 365.25
        frames.append(pop)
    py = pd.concat(frames, ignore_index=True)
    py["tenure_band"] = pd.cut(py["tenure"], [-0.01, 2, 5, 100], labels=["Under 2 yrs", "2-5 yrs", "5+ yrs"])
    py["age_band"] = pd.cut(py["age"], [0, 34, 49, 120], labels=["Under 35", "35-49", "50+"])
    py["is_digital"] = (py["division"] == "Digital & Technology").astype(int)
    return py


def chi_square_employment_type(py):
    """Is resignation independent of employment type?"""
    tab = pd.crosstab(py["employment_type"], py["resigned"])
    chi2, p, dof, _ = sps.chi2_contingency(tab)
    n = tab.to_numpy().sum()
    return {"table": tab, "chi2": chi2, "p": p, "dof": dof, "cramers_v": np.sqrt(chi2 / (n * (min(tab.shape) - 1)))}


def two_proportion(py, flag="is_digital"):
    """Difference in resignation rate between a flagged group and everyone else, with a 95% CI."""
    g = py.groupby(flag)["resigned"].agg(["sum", "count"])
    k1, n1, k0, n0 = g.loc[1, "sum"], g.loc[1, "count"], g.loc[0, "sum"], g.loc[0, "count"]
    z, p = proportions_ztest([k1, k0], [n1, n0])
    lo, hi = confint_proportions_2indep(k1, n1, k0, n0, method="wald")
    return {"rate_group": k1 / n1, "rate_rest": k0 / n0, "diff": k1 / n1 - k0 / n0,
            "ci_low": lo, "ci_high": hi, "z": z, "p": p, "n_group": int(n1), "n_rest": int(n0)}


def resignation_model(py):
    """Logistic regression of resignation on tenure, employment type, age, division group and gender.

    Returns (fitted model, odds-ratio table). Standard errors are clustered by employee
    because the same person contributes several person-years.
    """
    data = py[py["gender"].isin(["Woman", "Man"])].copy()
    formula = ("resigned ~ C(tenure_band, Treatment('5+ yrs')) + C(employment_type, Treatment('Ongoing'))"
               " + C(age_band, Treatment('35-49')) + is_digital + C(gender, Treatment('Man'))"
               " + C(staff_group, Treatment('Professional')) + C(year)")
    model = smf.logit(formula, data).fit(disp=False, cov_type="cluster", cov_kwds={"groups": data["employee_id"]})
    ci = model.conf_int()
    tab = pd.DataFrame({"odds_ratio": np.exp(model.params), "ci_low": np.exp(ci[0]), "ci_high": np.exp(ci[1]),
                        "p_value": model.pvalues}).drop(index="Intercept")
    labels = {
        "C(tenure_band, Treatment('5+ yrs'))[T.Under 2 yrs]": "Tenure under 2 yrs (vs 5+ yrs)",
        "C(tenure_band, Treatment('5+ yrs'))[T.2-5 yrs]": "Tenure 2-5 yrs (vs 5+ yrs)",
        "C(employment_type, Treatment('Ongoing'))[T.Fixed-term]": "Fixed-term (vs ongoing)",
        "C(age_band, Treatment('35-49'))[T.Under 35]": "Aged under 35 (vs 35-49)",
        "C(age_band, Treatment('35-49'))[T.50+]": "Aged 50+ (vs 35-49)",
        "is_digital": "Digital & Technology (vs other areas)",
        "C(gender, Treatment('Man'))[T.Woman]": "Woman (vs man)",
        "C(staff_group, Treatment('Professional'))[T.Academic]": "Academic (vs professional)",
    }
    tab = tab.rename(index=labels)
    tab = tab[~tab.index.str.startswith("C(year)")]
    return model, tab


def retirement_exposure(df, date=c.SNAPSHOT, horizon=5, age=65):
    """Ongoing staff who will reach `age` within `horizon` years, by division."""
    snap = active_on(df, date)
    snap = snap[snap["employment_type"] == "Ongoing"]
    age_at_horizon = (pd.Timestamp(date) + pd.DateOffset(years=horizon) - snap["date_of_birth"]).dt.days / 365.25
    out = pd.DataFrame({"ongoing_headcount": snap.groupby("division").size(),
                        "reaching_65": snap[age_at_horizon >= age].groupby("division").size()}).fillna(0)
    out["reaching_65"] = out["reaching_65"].astype(int)
    out["share"] = out["reaching_65"] / out["ongoing_headcount"]
    return out.sort_values("share", ascending=False)


def representation_scenario(headcount, identified, separation_rate, growth_rate, hire_share, years=10):
    """Project Indigenous workforce representation under a constant share of new hires.

    Each year: separations = headcount x separation_rate (assumed equal for all staff);
    hires = separations + growth; identified staff = survivors + hires x hire_share.
    The same arithmetic is rebuilt with live formulas on the 'Scenario' sheet of the workbook.
    """
    rows = [{"year": 0, "headcount": headcount, "identified": identified, "share": identified / headcount}]
    for t in range(1, years + 1):
        hires = headcount * (separation_rate + growth_rate)
        identified = identified * (1 - separation_rate) + hires * hire_share
        headcount = headcount * (1 + growth_rate)
        rows.append({"year": t, "headcount": headcount, "identified": identified, "share": identified / headcount})
    return pd.DataFrame(rows)
