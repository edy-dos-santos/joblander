"""Generate a synthetic university HR extract.

No real people are represented. The generator simulates a stock of staff at
1 Jan 2021 and then steps month by month to 31 Dec 2025, applying separation
hazards and replacement hiring. A handful of realistic workforce patterns are
deliberately built in (documented in docs/methodology.md) so the analysis has
something genuine to find, and a small number of data-entry errors are injected
so the cleaning step has something genuine to fix.
"""
import numpy as np
import pandas as pd

from . import config as c

# division -> (opening headcount, academic share, hiring replacement ratio)
UNITS = {
    "Faculty of Health": (540, 0.62, 1.03),
    "Faculty of Science": (430, 0.62, 1.01),
    "Faculty of Engineering": (380, 0.60, 1.00),
    "Faculty of Business & Law": (400, 0.58, 1.01),
    "Faculty of Arts & Education": (360, 0.60, 0.90),
    "Student Services": (290, 0.0, 1.02),
    "Digital & Technology": (230, 0.0, 1.05),
    "Finance & Facilities": (250, 0.0, 1.00),
    "Research Office": (130, 0.0, 1.03),
    "People & Culture": (110, 0.0, 1.01),
}

ACAD_P = [0.18, 0.30, 0.25, 0.15, 0.12]
ACAD_HIRE_P = [0.42, 0.33, 0.15, 0.06, 0.04]
PROF_P = [0.04, 0.12, 0.20, 0.22, 0.18, 0.12, 0.07, 0.05]
PROF_HIRE_P = [0.07, 0.18, 0.25, 0.22, 0.14, 0.08, 0.04, 0.02]

P_WOMAN = {"Level A": 0.58, "Level B": 0.55, "Level C": 0.50, "Level D": 0.40, "Level E": 0.31,
           "HEW 3": 0.70, "HEW 4": 0.71, "HEW 5": 0.70, "HEW 6": 0.68, "HEW 7": 0.65,
           "HEW 8": 0.60, "HEW 9": 0.52, "HEW 10+": 0.44}
P_WOMAN_ADJ = {"Faculty of Engineering": -0.20, "Faculty of Health": 0.12,
               "Digital & Technology": -0.26, "Faculty of Science": -0.06,
               "People & Culture": 0.10, "Faculty of Arts & Education": 0.06}

MEAN_AGE = {"Level A": 33, "Level B": 39, "Level C": 46, "Level D": 51, "Level E": 55,
            "HEW 3": 33, "HEW 4": 35, "HEW 5": 38, "HEW 6": 41, "HEW 7": 43,
            "HEW 8": 45, "HEW 9": 47, "HEW 10+": 50}
BASE_SALARY = {"Level A": 86_000, "Level B": 116_000, "Level C": 141_000, "Level D": 166_000,
               "Level E": 206_000, "HEW 3": 62_000, "HEW 4": 68_500, "HEW 5": 76_500,
               "HEW 6": 86_500, "HEW 7": 96_500, "HEW 8": 110_000, "HEW 9": 124_500,
               "HEW 10+": 142_000}

ANNUAL_HAZARD = {"Ongoing": 0.065, "Fixed-term": 0.21, "Casual": 0.30}


def _employment_type(rng, level, division):
    if level == "Level A":
        p = [0.15, 0.55, 0.30]
    elif level == "Level B":
        p = [0.55, 0.35, 0.10]
    elif level.startswith("Level"):
        p = [0.86, 0.14, 0.0]
    elif level in ("HEW 3", "HEW 4", "HEW 5"):
        p = [0.60, 0.22, 0.18]
    else:
        p = [0.78, 0.20, 0.02]
    if division in ("Faculty of Health", "Research Office") and p[0] > 0.2:
        p = [p[0] - 0.15, p[1] + 0.15, p[2]]  # grant-funded roles
    return rng.choice(c.EMPLOYMENT_TYPES, p=p)


def make_people(rng, n, division, hire_dates=None, hire_year=None):
    """Create n staff records. hire_dates=None builds the opening (1 Jan 2021) stock."""
    _, acad_share, _ = UNITS[division]
    opening = hire_dates is None
    is_acad = rng.random(n) < acad_share
    acad = rng.choice(c.ACADEMIC_LEVELS, n, p=ACAD_P if opening else ACAD_HIRE_P)
    prof = rng.choice(c.PROFESSIONAL_LEVELS, n, p=PROF_P if opening else PROF_HIRE_P)
    level = np.where(is_acad, acad, prof)
    emp_type = np.array([_employment_type(rng, lv, division) for lv in level])

    p_w = np.clip(np.array([P_WOMAN[lv] for lv in level]) + P_WOMAN_ADJ.get(division, 0), 0.05, 0.95)
    u = rng.random(n)
    gender = np.where(u < 0.012, "Non-binary", np.where(rng.random(n) < p_w, "Woman", "Man"))

    mean_age = np.array([MEAN_AGE[lv] for lv in level], dtype=float)
    if division == "Faculty of Engineering":
        mean_age += np.where(is_acad, 6, 0)  # built-in pattern: older academic profile
    if division == "Finance & Facilities":
        mean_age += 3
    age = np.clip(rng.normal(mean_age - (0 if opening else 5), 8.5), 21, 71)

    if opening:
        mean_tenure = np.where(emp_type == "Ongoing", 7.0, np.where(emp_type == "Fixed-term", 1.6, 1.0))
        tenure = np.minimum(rng.exponential(mean_tenure), age - 20.5)
        start = c.SIM_START - pd.to_timedelta((tenure * 365.25).round(), unit="D")
        ref = c.SIM_START
    else:
        start = pd.DatetimeIndex(hire_dates)
        ref = start
    dob = ref - pd.to_timedelta((age * 365.25).round(), unit="D")

    part_time = rng.random(n) < np.where(gender == "Woman", 0.24, 0.09)
    fte = np.where(emp_type == "Casual", rng.uniform(0.15, 0.5, n),
                   np.where(part_time, rng.choice([0.4, 0.5, 0.6, 0.8], n), 1.0)).round(2)

    # Built-in pattern: self-identification is low in the opening stock and improving in new hires.
    p_ind = 0.010 if opening else 0.014 + 0.002 * (hire_year - 2021)
    if division in ("Student Services", "People & Culture"):
        p_ind *= 2.0
    u = rng.random(n)
    indigenous = np.where(u < p_ind, c.INDIGENOUS_YES, np.where(u < p_ind + 0.06, "Not disclosed", "Neither"))

    return pd.DataFrame({
        "division": division,
        "staff_group": np.where(is_acad, "Academic", "Professional"),
        "classification": level,
        "employment_type": emp_type,
        "fte": fte,
        "gender": gender,
        "date_of_birth": pd.DatetimeIndex(dob).normalize(),
        "indigenous_status": indigenous,
        "start_date": pd.DatetimeIndex(start).normalize(),
        "end_date": pd.NaT,
        "separation_reason": None,
        "_step": rng.uniform(0, 0.03, n),
    })


def simulate(seed=c.SEED):
    rng = np.random.default_rng(seed)
    df = pd.concat([make_people(rng, n, d) for d, (n, _, _) in UNITS.items()], ignore_index=True)
    df["end_date"] = pd.to_datetime(df["end_date"])

    for month in pd.date_range(c.SIM_START, c.SNAPSHOT, freq="MS"):
        active = df["end_date"].isna().to_numpy()
        age = ((month - df["date_of_birth"]).dt.days / 365.25).to_numpy()
        tenure = ((month - df["start_date"]).dt.days / 365.25).to_numpy()
        et = df["employment_type"].to_numpy()
        div = df["division"].to_numpy()

        h = np.array([ANNUAL_HAZARD[e] for e in et])
        h = h * np.where((et == "Ongoing") & (tenure < 2), 1.7, 1.0)          # early-tenure attrition
        h = h * np.where((et == "Ongoing") & (age >= 62), 2.6, 1.0)           # retirement
        h = h * np.where(div == "Digital & Technology", 1.6, 1.0)             # external market pull
        h = h * np.where((div == "Faculty of Health") & (et == "Fixed-term"), 1.3, 1.0)
        h = h * (1.25 if month.year == 2022 else 1.0)                         # post-pandemic spike
        p_month = 1 - (1 - np.clip(h, 0, 0.9)) ** (1 / 12)
        leave = active & (rng.random(len(df)) < p_month)
        idx = np.flatnonzero(leave)

        reasons = []
        for i in idx:
            if et[i] == "Ongoing":
                if age[i] >= 58 and rng.random() < 0.75:
                    reasons.append("Retirement")
                else:
                    reasons.append(rng.choice(["Resignation", "Redundancy", "Other"], p=[0.84, 0.07, 0.09]))
            elif et[i] == "Fixed-term":
                reasons.append(rng.choice(["End of contract", "Resignation", "Other"], p=[0.52, 0.43, 0.05]))
            else:
                reasons.append(rng.choice(["End of contract", "Resignation"], p=[0.7, 0.3]))
        days = rng.integers(0, month.days_in_month, len(idx))
        df.loc[idx, "end_date"] = (month + pd.to_timedelta(days, unit="D")).to_numpy()
        df.loc[idx, "separation_reason"] = reasons

        hires = []
        for d, (_, _, ratio) in UNITS.items():
            n_new = rng.poisson((div[idx] == d).sum() * ratio)
            if n_new:
                dates = month + pd.to_timedelta(rng.integers(0, month.days_in_month, n_new), unit="D")
                hires.append(make_people(rng, n_new, d, hire_dates=dates, hire_year=month.year))
        if hires:
            df = pd.concat([df, *hires], ignore_index=True)

    # Salary: classification base + increments for service + a small unexplained loading
    # for men (built-in pattern: a small like-for-like gap alongside a larger structural one).
    last_day = df["end_date"].fillna(c.SNAPSHOT)
    service = ((last_day - df["start_date"]).dt.days / 365.25).clip(0, 8)
    base = df["classification"].map(BASE_SALARY)
    loading = np.where(df["gender"] == "Man", 1.012, 1.0)
    df["base_salary_fte"] = (base * (1 + 0.01 * service + df["_step"]) * loading).round(-1).astype(int)

    df = df.drop(columns="_step").sample(frac=1, random_state=seed).reset_index(drop=True)
    df.insert(0, "employee_id", [f"E{100000 + i}" for i in range(len(df))])
    return df


def inject_issues(df, seed=c.SEED):
    """Add the sort of defects a real HRIS extract contains. Each is fixed (and logged) in clean.py."""
    rng = np.random.default_rng(seed + 1)
    raw = df.copy()
    raw["gender"] = raw["gender"].astype(object)
    raw["division"] = raw["division"].astype(object)

    def pick(n, mask=None):
        pool = raw.index if mask is None else raw.index[mask]
        return rng.choice(pool, n, replace=False)

    for i in pick(40):  # inconsistent category labels
        raw.loc[i, "gender"] = {"Woman": rng.choice(["F", "female"]), "Man": rng.choice(["M", "male"]),
                                "Non-binary": "X"}[raw.loc[i, "gender"]]
    for i in pick(25):  # stray whitespace / case
        raw.loc[i, "division"] = rng.choice(["  " + raw.loc[i, "division"], raw.loc[i, "division"].upper()])
    for i in pick(9, raw["end_date"].notna()):  # start and end dates transposed
        raw.loc[i, ["start_date", "end_date"]] = raw.loc[i, ["end_date", "start_date"]].to_numpy()
    for i in pick(4):  # salary keyed with an extra zero
        raw.loc[i, "base_salary_fte"] = raw.loc[i, "base_salary_fte"] * 10
    raw["fte"] = raw["fte"].astype(float)
    raw.loc[pick(15, raw["employment_type"] == "Casual"), "fte"] = np.nan  # missing casual FTE
    raw.loc[pick(6, raw["end_date"].notna()), "separation_reason"] = None   # missing reason
    raw = pd.concat([raw, raw.loc[pick(12)]], ignore_index=True)            # duplicated rows
    return raw.sample(frac=1, random_state=seed).reset_index(drop=True)


def main():
    c.RAW.parent.mkdir(parents=True, exist_ok=True)
    raw = inject_issues(simulate())
    raw.to_csv(c.RAW, index=False, date_format="%Y-%m-%d")
    print(f"Wrote {len(raw):,} rows to {c.RAW.relative_to(c.ROOT)}")


if __name__ == "__main__":
    main()
