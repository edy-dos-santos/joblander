"""Validate and clean the raw HR extract.

Every rule either fixes a record or flags it, and every action is written to
outputs/data_quality_log.csv so the cleaned dataset is fully auditable.
"""
import numpy as np
import pandas as pd

from . import config as c

GENDER_MAP = {"f": "Woman", "female": "Woman", "woman": "Woman", "m": "Man", "male": "Man", "man": "Man",
              "x": "Non-binary", "non-binary": "Non-binary"}
DATE_COLS = ["date_of_birth", "start_date", "end_date"]


def load_raw(path=c.RAW):
    return pd.read_csv(path, parse_dates=DATE_COLS)


def clean(raw):
    """Return (clean_df, log_df)."""
    df = raw.copy()
    log = []

    def record(rule, mask, action):
        n = int(mask.sum())
        log.append({"rule": rule, "records_affected": n, "action": action,
                    "example_ids": ", ".join(df.loc[mask, "employee_id"].head(3))})

    dup = df.duplicated(keep="first")
    record("Exact duplicate rows", dup, "Removed duplicates, kept first")
    df = df.loc[~dup].reset_index(drop=True)

    dup_id = df.duplicated("employee_id", keep=False)
    record("Employee ID appears on more than one distinct record", dup_id, "Flag only - none expected")

    canon = {d.lower(): d for d in c.DIVISIONS}
    tidy = df["division"].str.strip().str.lower().map(canon)
    record("Division name has stray whitespace or casing", tidy.ne(df["division"]) & tidy.notna(),
           "Standardised to reference list")
    record("Division not in reference list", tidy.isna(), "Flag only - none expected")
    df["division"] = tidy.fillna(df["division"])

    g = df["gender"].str.strip().str.lower().map(GENDER_MAP)
    record("Gender recorded with a non-standard label", g.ne(df["gender"]) & g.notna(),
           "Mapped to standard categories")
    df["gender"] = g.fillna(df["gender"])

    swapped = df["end_date"].notna() & (df["end_date"] < df["start_date"])
    record("End date earlier than start date", swapped, "Dates transposed at entry - swapped back")
    df.loc[swapped, ["start_date", "end_date"]] = df.loc[swapped, ["end_date", "start_date"]].to_numpy()

    # Salary outliers: more than 3x the classification median is implausible under an enterprise agreement.
    med = df.groupby("classification")["base_salary_fte"].transform("median")
    outlier = df["base_salary_fte"] > 3 * med
    record("Salary more than 3x classification median", outlier, "Extra digit keyed - divided by 10")
    df.loc[outlier, "base_salary_fte"] = (df.loc[outlier, "base_salary_fte"] / 10).round().astype(int)

    miss_fte = df["fte"].isna()
    record("Missing FTE", miss_fte, "Imputed with median FTE for the same employment type")
    df["fte"] = df["fte"].fillna(df.groupby("employment_type")["fte"].transform("median")).round(2)

    miss_reason = df["end_date"].notna() & df["separation_reason"].isna()
    record("Separated with no separation reason", miss_reason, "Set to 'Other' (not treated as voluntary)")
    df.loc[miss_reason, "separation_reason"] = "Other"

    bad_age = ((df["start_date"] - df["date_of_birth"]).dt.days / 365.25) < 16
    record("Aged under 16 at commencement", bad_age, "Flag only - none expected")
    record("FTE outside 0-1", ~df["fte"].between(0.01, 1.0), "Flag only - none expected")

    df = df.sort_values("employee_id").reset_index(drop=True)
    return df, pd.DataFrame(log)


def add_derived(df, as_at=c.SNAPSHOT):
    """Add reporting fields used by the workbook and analysis."""
    out = df.copy()
    out["active_at_snapshot"] = (out["start_date"] <= as_at) & (out["end_date"].isna() | (out["end_date"] > as_at))
    ref = out["end_date"].fillna(as_at).clip(upper=as_at)
    out["age"] = np.floor((ref - out["date_of_birth"]).dt.days / 365.25).astype(int)
    out["tenure_years"] = ((ref - out["start_date"]).dt.days / 365.25).round(1)
    out["age_band"] = pd.cut(out["age"], c.AGE_BINS, labels=c.AGE_LABELS).astype(str)
    out["tenure_band"] = pd.cut(out["tenure_years"], c.TENURE_BINS, labels=c.TENURE_LABELS).astype(str)
    out["senior"] = out["classification"].isin(c.SENIOR_LEVELS)
    out["separation_year"] = out["end_date"].dt.year.astype("Int64")
    return out


def load_clean(path=c.CLEAN):
    return pd.read_csv(path, parse_dates=DATE_COLS)


def main():
    df, log = clean(load_raw())
    df = add_derived(df)
    c.CLEAN.parent.mkdir(parents=True, exist_ok=True)
    c.OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(c.CLEAN, index=False, date_format="%Y-%m-%d")
    log.to_csv(c.OUT / "data_quality_log.csv", index=False)
    print(log[["rule", "records_affected"]].to_string(index=False))
    print(f"Wrote {len(df):,} clean rows to {c.CLEAN.relative_to(c.ROOT)}")


if __name__ == "__main__":
    main()
