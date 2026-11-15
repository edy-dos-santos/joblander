"""Metric definitions against a tiny hand-calculated example, plus consistency checks on the real results."""
import pandas as pd
import pytest

from benchmark import config as c
from benchmark import metrics as m

Y = c.LATEST


def comp_rows(rows):
    cols = ["university", "manager_category", "occupation", "employment_status", "employment_type", "gender", "n_employees"]
    return pd.DataFrame(rows, columns=cols).assign(reporting_year=Y)


def move_rows(rows):
    cols = ["university", "movement_type", "manager_category", "employment_type", "gender", "n_employees"]
    return pd.DataFrame(rows, columns=cols).assign(reporting_year=Y)


@pytest.fixture
def toy():
    comp = comp_rows([
        ("A", "Manager", "Senior managers", "Full-time", "Permanent", "Women", 2),
        ("A", "Manager", "Senior managers", "Full-time", "Permanent", "Men", 8),
        ("A", "Manager", "Other managers", "Full-time", "Permanent", "Women", 12),
        ("A", "Manager", "Other managers", "Part-time", "Permanent", "Men", 8),
        ("A", "Non-manager", "Professionals", "Full-time", "Permanent", "Women", 26),
        ("A", "Non-manager", "Professionals", "Full-time", "Contract", "Men", 4),
        ("A", "Non-manager", "Professionals", "Casual", "Casual", "Women", 20),
        ("A", "Non-manager", "Professionals", "Casual", "Casual", "Men", 20),
        ("B", "Manager", "Senior managers", "Full-time", "Permanent", "Women", 5),
        ("B", "Manager", "Senior managers", "Full-time", "Permanent", "Men", 5),
        ("B", "Non-manager", "Professionals", "Full-time", "Permanent", "Women", 45),
        ("B", "Non-manager", "Professionals", "Full-time", "Permanent", "Men", 45),
    ])
    move = move_rows([
        ("A", "Promotions", "Non-manager", "Permanent", "Women", 3),
        ("A", "Promotions", "Non-manager", "Permanent", "Men", 3),
        ("A", "Promotions", "Non-manager", "Casual", "Women", 50),   # casual: must be ignored
        ("B", "Promotions", "Non-manager", "Permanent", "Women", 5),
        ("B", "Promotions", "Non-manager", "Permanent", "Men", 5),
    ])
    return comp, move


def test_league_rates(toy):
    t = m.league(*toy, Y)
    a = t.loc["A"]
    assert a["headcount"] == 100 and a["women"] == 60
    assert a["women_share"] == pytest.approx(0.60)
    assert a["women_mgr_share"] == pytest.approx(14 / 30)
    assert a["women_senior_share"] == pytest.approx(2 / 10)
    assert a["leadership_gap_pts"] == pytest.approx((14 / 30 - 0.60) * 100)
    assert a["casual_share"] == pytest.approx(0.40)
    assert a["pt_mgr_share"] == pytest.approx(8 / 30)


def test_promotion_parity_excludes_casuals(toy):
    a = m.league(*toy, Y).loc["A"]
    assert a["promotions"] == 6                        # the 50 casual 'promotions' are not counted
    # women are 40 of 60 non-casual staff and got 3 of 6 promotions
    assert a["promo_parity"] == pytest.approx(0.5 / (40 / 60))


def test_sector_value_is_pooled_not_an_average_of_rates(toy):
    t = m.league(*toy, Y)
    pooled = m.sector_pooled(t)
    assert pooled["women_senior_share"] == pytest.approx(7 / 20)                       # (2+5)/(10+10)
    assert pooled["women_share"] == pytest.approx(110 / 200)
    assert m.sector_pooled(t, exclude="A")["women_senior_share"] == pytest.approx(0.5)


def test_parity_arithmetic(toy):
    par = m.parity_arithmetic(m.league(*toy, Y), "A")
    assert par.loc["50%", "additional"] == 3            # 2 of 10 now; 5 needed
    assert par.loc["Own workforce share", "additional"] == 4


def test_funnel_flags_only_large_departures():
    t = pd.DataFrame({"k": [50, 500, 80], "n": [100, 1000, 100]}, index=["small", "big", "outlier"])
    fun, p0 = m.funnel(t, "k", "n")
    assert p0 == pytest.approx(630 / 1200)
    assert fun.loc["small", "signal"] == "Consistent with sector"
    assert fun.loc["outlier", "signal"] == "Above sector (99.8%)"


def test_real_results_are_internally_consistent(results):
    t = results["league"]
    assert (t["women"] <= t["headcount"]).all()
    assert (t["women_senior"] <= t["senior"]).all() and (t["senior"] <= t["managers"]).all()
    assert (t["managers"] <= t["headcount"]).all()
    assert t["women_share"].between(0.4, 0.8).all()
    tiers = results["tiers"]
    assert tiers["focus_n"].sum() == t.loc[results["focus"], "headcount"]
    assert tiers["rest_n"].sum() == t["headcount"].sum() - t.loc[results["focus"], "headcount"]
    by_year = results["promo_by_year"]
    assert sum(v["promotions"] for v in by_year.values()) == results["promo_pooled"]["promotions"]
