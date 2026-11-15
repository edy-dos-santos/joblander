"""Metric definitions checked against a tiny hand-calculated workforce."""
import pandas as pd
import pytest

from workforce import config as c
from workforce import metrics as m
from workforce import stats as s


def staff(rows):
    cols = ["employee_id", "employment_type", "start_date", "end_date", "separation_reason", "gender",
            "classification", "base_salary_fte"]
    df = pd.DataFrame(rows, columns=cols)
    df["start_date"] = pd.to_datetime(df["start_date"])
    df["end_date"] = pd.to_datetime(df["end_date"])
    df["fte"] = 1.0
    return df


@pytest.fixture
def small():
    return staff([
        ("E1", "Ongoing", "2020-01-01", None, None, "Woman", "HEW 5", 80_000),
        ("E2", "Ongoing", "2020-01-01", "2024-06-30", "Resignation", "Man", "HEW 5", 80_000),
        ("E3", "Fixed-term", "2023-03-01", "2024-09-30", "End of contract", "Woman", "HEW 5", 80_000),
        ("E4", "Ongoing", "2024-02-01", None, None, "Man", "Level E", 200_000),
        ("E5", "Casual", "2023-01-01", "2024-03-31", "End of contract", "Woman", "HEW 5", 80_000),
        ("E6", "Ongoing", "2019-01-01", "2024-12-31", "Retirement", "Man", "Level E", 200_000),
    ])


def test_active_on_excludes_people_whose_last_day_is_the_snapshot(small):
    ids = set(m.active_on(small, "2024-12-31")["employee_id"])
    assert ids == {"E1", "E4"}  # E6's last day was 31 Dec, so they are not in the closing headcount


def test_turnover_uses_average_headcount_and_excludes_casuals(small):
    t = m.turnover(small, 2024).iloc[0]
    assert t["opening"] == 4            # E1, E2, E3, E6 (E5 is casual)
    assert t["closing"] == 2            # E1, E4
    assert t["separations"] == 3        # E2, E3, E6
    assert t["voluntary"] == 1          # only E2 resigned
    assert t["total_rate"] == pytest.approx(3 / 3)
    assert t["voluntary_rate"] == pytest.approx(1 / 3)


def test_pay_gap_separates_structural_from_like_for_like():
    df = staff([
        ("A", "Ongoing", "2020-01-01", None, None, "Woman", "HEW 5", 80_000),
        ("B", "Ongoing", "2020-01-01", None, None, "Woman", "HEW 5", 80_000),
        ("C", "Ongoing", "2020-01-01", None, None, "Man", "HEW 5", 80_000),
        ("D", "Ongoing", "2020-01-01", None, None, "Woman", "Level E", 200_000),
        ("E", "Ongoing", "2020-01-01", None, None, "Man", "Level E", 200_000),
        ("F", "Ongoing", "2020-01-01", None, None, "Man", "Level E", 200_000),
    ])
    gap = m.gender_pay_gap(df, "2024-12-31")
    assert gap["like_for_like"] == pytest.approx(0)            # equal pay at every level
    assert gap["overall"] == pytest.approx(1 - 120_000 / 160_000)  # gap comes entirely from who is senior
    assert gap["structural"] == pytest.approx(gap["overall"])


def test_small_cells_are_suppressed_but_zero_is_kept():
    table = pd.DataFrame({"n": [0, 1, 4, 5, 120]})
    assert m.suppress_small_cells(table)["n"].tolist() == [0, "<5", "<5", 5, 120]


def test_scenario_model_matches_hand_calculation():
    sc = s.representation_scenario(1000, 10, separation_rate=0.10, growth_rate=0.0, hire_share=0.05, years=2)
    assert sc["identified"].tolist() == pytest.approx([10, 10 * 0.9 + 100 * 0.05, 14 * 0.9 + 5])
    assert sc["share"].iloc[-1] == pytest.approx(17.6 / 1000)


def test_headline_results_are_internally_consistent(results):
    by_div = results["by_division"]
    assert by_div["headcount"].sum() == results["headcount"]
    assert (by_div[c.EMPLOYMENT_TYPES].sum(axis=1) == by_div["headcount"]).all()
    t = results["turnover_trend"]
    assert (t["voluntary"] <= t["separations"]).all()
    assert t["total_rate"].between(0, 1).all()
    # closing headcount of one year is the opening headcount of the next
    assert (t["closing"].iloc[:-1].to_numpy() == t["opening"].iloc[1:].to_numpy()).all()
