"""Recalculate the workbook with LibreOffice and check its formulas against the Python metrics."""
import shutil
import subprocess

import openpyxl
import pytest

from benchmark import config as c
from benchmark import excel_report

soffice = shutil.which("soffice") or shutil.which("libreoffice")
pytestmark = pytest.mark.skipif(soffice is None, reason="LibreOffice not installed")


@pytest.fixture(scope="module")
def wb(tmp_path_factory, results):
    tmp = tmp_path_factory.mktemp("xlsx")
    src = excel_report.build(results, path=tmp / "bench.xlsx")
    subprocess.run([soffice, "--headless", "--convert-to", "xlsx:Calc MS Excel 2007 XML", "--outdir",
                    str(tmp / "recalc"), str(src)], check=True, capture_output=True, timeout=300)
    return openpyxl.load_workbook(tmp / "recalc" / "bench.xlsx", data_only=True)


def rows(ws, header_row, first_col=1):
    headers = [cell.value for cell in ws[header_row]][first_col - 1:]
    out = {}
    for row in ws.iter_rows(min_row=header_row + 1, min_col=first_col, values_only=True):
        if row[0] is None:
            break
        out[row[0]] = dict(zip(headers, row))
    return out


def test_league_sheet_matches_python_for_every_university(wb, results):
    xl = rows(wb["League"], 4)
    t = results["league"]
    for uni, r in t.iterrows():
        assert xl[uni]["Headcount"] == r["headcount"]
        assert xl[uni]["Senior management"] == r["senior"]
        assert xl[uni]["Promotions"] == r["promotions"]
        assert xl[uni]["Women % of senior management"] == pytest.approx(r["women_senior_share"])
        assert xl[uni]["Leadership gap (pts)"] == pytest.approx(r["leadership_gap_pts"])
        assert xl[uni]["Promotion parity ratio"] == pytest.approx(r["promo_parity"])
        assert xl[uni]["z-score vs sector (senior)"] == pytest.approx(results["funnel_senior"].loc[uni, "z"])
    assert xl["All universities (pooled)"]["Headcount"] == t["headcount"].sum()


def test_scorecard_matches_python(wb, results):
    xl = rows(wb["Benchmark"], 8, first_col=2)
    sc = results["scorecard"]
    for label, key in [("Women % of employees", "women_share"), ("Women % of managers", "women_mgr_share"),
                       ("Women % of senior management", "women_senior_share"),
                       ("Leadership gap (pts)", "leadership_gap_pts"), ("Casual % of headcount", "casual_share"),
                       ("Promotion parity ratio", "promo_parity")]:
        assert xl[label]["Selected university"] == pytest.approx(sc.loc[key, "focus"])
        assert xl[label]["All universities (pooled)"] == pytest.approx(sc.loc[key, "sector_pooled"])
        assert xl[label]["Median university"] == pytest.approx(sc.loc[key, "sector_median"])
        assert xl[label]["Rank (1 = highest)"] == sc.loc[key, "rank"]
        assert xl[label]["Universities reporting"] == sc.loc[key, "of"]


def test_tier_and_parity_cells_match_python(wb, results):
    ws = wb["Benchmark"]
    xl = rows(ws, 27, first_col=2)
    for tier, r in results["tiers"].iterrows():
        row = xl[c.TIER_LABELS.get(tier, tier)]
        assert row["Selected: employees"] == r["focus_n"]
        assert row["Selected: women %"] == pytest.approx(r["focus_share"])
        assert row["All other universities: women %"] == pytest.approx(r["rest_share"])
    assert ws["C23"].value == results["parity"].loc["Sector average", "additional"]
    assert ws["C24"].value == results["parity"].loc["50%", "additional"]
