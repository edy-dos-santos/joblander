"""The loading rules do what the methodology says, on the committed extract."""
import pandas as pd

from benchmark import config as c
from benchmark import data


def test_subtotal_rows_are_removed_so_appointments_are_not_double_counted(results):
    raw = pd.read_csv(c.MOVEMENTS)
    assert raw["movement_type"].str.startswith("Total appointments").any()        # present in the source
    assert not results["move"]["movement_type"].str.startswith("Total appointments").any()
    assert results["notes"]["subtotal_rows_removed"] > 0


def test_only_universities_are_benchmarked(results):
    names = results["comp"]["university"].unique()
    assert 35 <= len(names) <= 42
    assert all("University" in n for n in names)
    assert not any(word in n for n in names for word in c.SUBSIDIARY_WORDS)
    assert results["focus"] in names


def test_one_name_per_employer_across_years(results):
    assert (results["comp"].groupby("employer_abn")["university"].nunique() == 1).all()


def test_categories_are_harmonised_across_years(results):
    assert set(results["comp"]["manager_category"]) == {"Manager", "Non-manager"}
    assert set(results["move"]["manager_category"]) == {"Manager", "Non-manager"}
    assert set(results["comp"]["gender"]) == {"Women", "Men"}
    assert set(results["comp"]["reporting_year"]) == set(c.YEARS)
    assert "Promtions from non-manager to manager" not in set(results["move"]["movement_type"])
    assert (results["comp"]["n_employees"] > 0).all()


def test_balanced_panel_reports_every_year(results):
    comp, panel = results["comp"], results["notes"]["balanced_panel"]
    counts = comp[comp["university"].isin(panel)].groupby("university")["reporting_year"].nunique()
    assert (counts == len(c.YEARS)).all()
    assert results["focus"] in panel


def test_tidy_name():
    assert data.tidy_name("The University Of Queensland") == "University of Queensland"
    assert data.tidy_name("Bond University Limited") == "Bond University"


def test_every_manager_falls_in_a_reported_tier(results):
    managers = results["comp"][results["comp"]["manager_category"] == "Manager"]
    assert set(managers["occupation"]) <= set(c.MANAGER_TIERS)
