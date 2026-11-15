"""Recalculate the Excel workbook and check its formulas agree with the Python metrics.

The workbook contains formulas only, so it is recalculated with LibreOffice
(headless). The test is skipped where LibreOffice is not installed.
"""
import shutil
import subprocess

import openpyxl
import pytest

from workforce import config as c
from workforce import excel_report

soffice = shutil.which("soffice") or shutil.which("libreoffice")
pytestmark = pytest.mark.skipif(soffice is None, reason="LibreOffice not installed")


@pytest.fixture(scope="module")
def workbook(tmp_path_factory, results):
    tmp = tmp_path_factory.mktemp("xlsx")
    src = excel_report.build(results["df"], results["scenario_inputs"], path=tmp / "report.xlsx")
    subprocess.run([soffice, "--headless", "--convert-to", "xlsx:Calc MS Excel 2007 XML",
                    "--outdir", str(tmp / "recalc"), str(src)], check=True, capture_output=True, timeout=300)
    return openpyxl.load_workbook(tmp / "recalc" / "report.xlsx", data_only=True)


def table(ws, header_row, key_col=1):
    """Read a block under a header row into {row label: {column header: value}}."""
    headers = [cell.value for cell in ws[header_row]]
    out = {}
    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        if row[key_col - 1] is None:
            break
        out[row[key_col - 1]] = dict(zip(headers, row))
    return out


def test_headcount_sheet(workbook, results):
    xl = table(workbook["Headcount"], 4)
    for division, row in results["by_division"].iterrows():
        assert xl[division]["Headcount"] == row["headcount"]
        assert xl[division]["FTE"] == pytest.approx(row["fte"], abs=0.06)
        for t in c.EMPLOYMENT_TYPES:
            assert xl[division][t] == row[t]
    assert xl["University"]["Headcount"] == results["headcount"]


def test_turnover_sheet(workbook, results):
    xl = table(workbook["Turnover"], 4)
    for year, row in results["turnover_trend"].iterrows():
        assert xl[year]["Opening headcount"] == row["opening"]
        assert xl[year]["Closing headcount"] == row["closing"]
        assert xl[year]["Separations"] == row["separations"]
        assert xl[year]["Total separation rate"] == pytest.approx(row["total_rate"])
        assert xl[year]["Resignation rate"] == pytest.approx(row["voluntary_rate"])


def find(ws, label):
    for row in ws.iter_rows(values_only=True):
        if row[0] == label:
            return [v for v in row[1:] if v is not None][0]
    raise KeyError(label)


def test_equity_sheet(workbook, results):
    ws = workbook["Equity"]
    gap, ind = results["pay_gap"], results["indigenous"].iloc[-1]
    assert find(ws, "Women in senior roles (Level D, E, HEW 10+)") == pytest.approx(results["senior"]["women_share_senior"])
    assert ws.cell(row=[r[0].row for r in ws.iter_rows() if r[0].value == "All classifications (overall gap)"][0],
                   column=6).value == pytest.approx(gap["overall"])
    assert find(ws, "Like-for-like gap (within-level gaps weighted by women's headcount)") == pytest.approx(gap["like_for_like"])
    assert find(ws, "Staff who identify as Aboriginal and/or Torres Strait Islander") == ind["identified"]
    assert find(ws, "Representation (share of headcount)") == pytest.approx(ind["share"])


def test_scenario_sheet_matches_python_model(workbook, results):
    xl = table(workbook["Scenario"], 13)
    for label, col in [("Current hiring mix", "Current hiring mix - %"), ("5% of hires", "Scenario A - %"),
                       ("8% of hires", "Scenario B - %")]:
        for _, row in results["scenarios"][label].iterrows():
            assert xl[int(row["year"])][col] == pytest.approx(row["share"], rel=1e-6)
