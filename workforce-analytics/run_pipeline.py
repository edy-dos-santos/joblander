"""Rebuild everything: data -> cleaning -> analysis -> charts -> Excel workbook -> slide deck.

Usage:  python run_pipeline.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from workforce import analysis, charts, clean, config as c, deck, excel_report, generate  # noqa: E402


def main():
    print("1/5  Generating synthetic HR extract")
    generate.main()
    print("2/5  Validating and cleaning")
    clean.main()
    print("3/5  Running analysis")
    r = analysis.run()
    analysis.write_tables(r)
    (c.OUT / "key_findings.md").write_text(analysis.findings_markdown(r), encoding="utf-8")
    print("4/5  Drawing charts")
    figs = {
        "headcount": charts.headcount_by_division(r["by_division"]),
        "turnover_trend": charts.turnover_trend(r["turnover_trend"]),
        "resignation_division": charts.resignation_by_division(r["resignation_by_division"], r["resignation_rate_pooled"]),
        "odds": charts.odds_ratios(r["odds_ratios"]),
        "women": charts.women_by_level(r["gender_by_level"]),
        "indigenous": charts.indigenous_representation(r["indigenous"], r["scenarios"], c.SNAPSHOT.year),
        "retirement": charts.retirement_exposure(r["retirement"]),
    }
    print("5/5  Building Excel workbook and PowerPoint briefing")
    xlsx = excel_report.build(r["df"], r["scenario_inputs"])
    pptx = deck.build(r, figs)
    print(f"\nDone.\n  {xlsx.relative_to(c.ROOT)}\n  {pptx.relative_to(c.ROOT)}\n  outputs/key_findings.md")


if __name__ == "__main__":
    main()
