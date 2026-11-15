"""Rebuild everything from the committed extract: analysis -> charts -> Excel workbook -> slide deck.

Usage:
    python run_pipeline.py            # uses data/extract/ (committed)
    python run_pipeline.py --fetch    # first re-download the WGEA files from data.gov.au (about 170 MB)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from benchmark import analysis, charts, config as c, deck, excel_report, fetch  # noqa: E402


def main():
    if "--fetch" in sys.argv:
        sys.argv.remove("--fetch")
        print("0/4  Downloading WGEA public data and cutting the higher-education extract")
        fetch.main()
    print("1/4  Running analysis")
    r = analysis.run()
    c.OUT.mkdir(exist_ok=True)
    (c.OUT / "key_findings.md").write_text(analysis.findings_markdown(r), encoding="utf-8")
    cols = ["headcount", "women_share", "managers", "women_mgr_share", "senior", "women_senior_share",
            "leadership_gap_pts", "manager_share", "casual_share", "contract_share", "promotions", "promo_parity"]
    league = r["league"][cols].join(r["funnel_senior"][["z", "signal"]]).sort_values("women_senior_share", ascending=False)
    league.round(4).to_csv(c.OUT / "league_table.csv")
    print("2/4  Drawing charts")
    figs = charts.build_all(r)
    print("3/4  Building Excel workbook")
    xlsx = excel_report.build(r)
    print("4/4  Building PowerPoint briefing")
    pptx = deck.build(r, figs)
    print(f"\nDone.\n  {xlsx.relative_to(c.ROOT)}\n  {pptx.relative_to(c.ROOT)}\n  outputs/key_findings.md")


if __name__ == "__main__":
    main()
