"""The cleaning rules fix what they claim to fix, and the committed clean data is valid."""
import pandas as pd

from workforce import config as c
from workforce.clean import clean, load_clean, load_raw


def test_clean_dataset_passes_every_integrity_rule():
    df = load_clean()
    assert df["employee_id"].is_unique
    assert set(df["division"]) == set(c.DIVISIONS)
    assert set(df["gender"]) <= set(c.GENDERS)
    assert set(df["classification"]) <= set(c.LEVELS)
    assert set(df["employment_type"]) == set(c.EMPLOYMENT_TYPES)
    assert set(df["indigenous_status"]) <= set(c.INDIGENOUS_VALUES)
    assert df["fte"].between(0.01, 1).all()
    left = df["end_date"].notna()
    assert (df.loc[left, "end_date"] >= df.loc[left, "start_date"]).all()
    assert df.loc[left, "separation_reason"].isin(c.SEPARATION_REASONS).all()
    assert df.loc[~left, "separation_reason"].isna().all()
    assert df["base_salary_fte"].between(50_000, 300_000).all()


def test_every_injected_defect_is_caught_and_logged():
    cleaned, log = clean(load_raw())
    found = log.set_index("rule")["records_affected"]
    assert found["Exact duplicate rows"] == 12
    assert found["End date earlier than start date"] == 9
    assert found["Salary more than 3x classification median"] == 4
    assert found["Missing FTE"] == 15
    assert found["Gender recorded with a non-standard label"] == 40
    assert len(cleaned) == len(load_raw()) - 12


def test_cleaning_is_idempotent():
    once, _ = clean(load_raw())
    twice, log = clean(once)
    pd.testing.assert_frame_equal(once, twice)
    assert log["records_affected"].sum() == 0
