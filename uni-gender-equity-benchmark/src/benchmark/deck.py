"""Build the briefing deck. Headline = the finding; one chart; a plain-English panel. Numbers come from the results dict."""
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from . import config as c

NAVY, INK, INK2, PALE = (RGBColor.from_string(x) for x in ("0D366B", "0B0B0B", "52514E", "EEF4FC"))
WHITE = RGBColor(255, 255, 255)
W, H = Inches(13.333), Inches(7.5)
FONT = "Calibri"
F = c.FOCUS_SHORT
FOOT = f"{F} gender equity benchmark  |  WGEA public data {c.LATEST} (CC BY 3.0 AU)  |  Independent analysis"


def _text(slide, x, y, w, h, text, size=14, bold=False, colour=INK, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    tf = slide.shapes.add_textbox(x, y, w, h).text_frame
    tf.word_wrap, tf.vertical_anchor = True, anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, line in enumerate(text if isinstance(text, list) else [text]):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment, p.space_after = align, Pt(size * 0.55)
        run = p.add_run()
        run.text = line
        run.font.name, run.font.size, run.font.bold, run.font.color.rgb = FONT, Pt(size), bold, colour
    return tf


def _rect(slide, x, y, w, h, fill):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    shp.line.fill.background()
    shp.shadow.inherit = False


def _slide(prs, headline, n):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    _rect(s, 0, 0, Inches(0.18), H, NAVY)
    _text(s, Inches(0.6), Inches(0.4), Inches(12.1), Inches(1.1), headline, size=26, bold=True, colour=NAVY,
          anchor=MSO_ANCHOR.MIDDLE)
    _text(s, Inches(0.6), Inches(7.02), Inches(10.5), Inches(0.3), FOOT, size=10, colour=INK2)
    _text(s, Inches(12.0), Inches(7.02), Inches(0.75), Inches(0.3), str(n), size=10, colour=INK2, align=PP_ALIGN.RIGHT)
    return s


def _chart_slide(prs, n, headline, image, bullets, source, panel_title="What it means"):
    s = _slide(prs, headline, n)
    pic = s.shapes.add_picture(str(image), Inches(0.6), Inches(1.75), width=Inches(7.8))
    if pic.height > Inches(4.75):
        ratio = Inches(4.75) / pic.height
        pic.height, pic.width = int(Inches(4.75)), int(pic.width * ratio)
    x, y, w, h = Inches(8.75), Inches(1.75), Inches(4.0), Inches(4.95)
    _rect(s, x, y, w, h, PALE)
    _text(s, x + Inches(0.25), y + Inches(0.22), w - Inches(0.5), Inches(0.4), panel_title, size=14, bold=True, colour=NAVY)
    _text(s, x + Inches(0.25), y + Inches(0.75), w - Inches(0.5), h - Inches(0.9), bullets, size=13)
    _text(s, Inches(0.6), Inches(6.62), Inches(7.8), Inches(0.3), source, size=10, colour=INK2)


def build(r, figs, path=None):
    path = path or c.OUT / "University_Benchmark_Briefing.pptx"
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H
    t, sc, ti, st = r["league"], r["scorecard"], r["tiers"], r["senior_test"]
    row = t.loc[r["focus"]]
    n_uni = len(t)
    tr = r["trend"].set_index(["metric", "year"])
    y0, y1 = c.YEARS[0], c.YEARS[-1]
    pp, py, par = r["promo_pooled"], r["promo_by_year"][y1], r["parity"]
    fun = r["funnel_senior"]
    z = fun.loc[r["focus"], "z"]
    beyond = int((fun["z"].abs() > 3.09).sum())
    ms = t["manager_share"]
    exec_t, sen_t, oth_t = (ti.loc[k] for k in ("Other Executives and General Managers", "Senior managers", "Other managers"))

    s = prs.slides.add_slide(prs.slide_layouts[6])
    _rect(s, 0, 0, W, H, NAVY)
    _text(s, Inches(0.9), Inches(2.2), Inches(11.5), Inches(1.2), "Women in university leadership", size=44, bold=True, colour=WHITE)
    _text(s, Inches(0.9), Inches(3.4), Inches(11.5), Inches(0.6),
          f"How {F} compares with {n_uni - 1} other Australian universities, {y1}", size=22, colour=WHITE)
    _text(s, Inches(0.9), Inches(5.7), Inches(11.5), Inches(1.0),
          ["Independent analysis of public data published by the Workplace Gender Equality Agency (data.gov.au, CC BY 3.0 AU).",
           "Not affiliated with or endorsed by QUT or WGEA."], size=13, colour=RGBColor.from_string("CDE2FB"))

    s = _slide(prs, f"Summary: {F} is at sector level for women in management, and below it at the top", 2)
    tiles = [(f"{row['women_share']:.0%}", "of employees are women"),
             (f"{row['women_mgr_share']:.0%}", f"of managers are women (sector {sc.loc['women_mgr_share', 'sector_pooled']:.0%})"),
             (f"{row['women_senior_share']:.0%}", f"of senior management are women (sector {sc.loc['women_senior_share', 'sector_pooled']:.0%})"),
             (f"{sc.loc['women_senior_share', 'rank']} of {sc.loc['women_senior_share', 'of']}", "rank on women in senior management")]
    for i, (num, label) in enumerate(tiles):
        x = Inches(0.6) + i * Inches(3.07)
        _rect(s, x, Inches(1.7), Inches(2.9), Inches(1.55), PALE)
        _text(s, x + Inches(0.2), Inches(1.8), Inches(2.5), Inches(0.8), num, size=34, bold=True, colour=NAVY)
        _text(s, x + Inches(0.2), Inches(2.62), Inches(2.5), Inches(0.5), label, size=12, colour=INK2)
    _text(s, Inches(0.6), Inches(3.6), Inches(12.1), Inches(3.3), [
        f"1.  Women's representation drops at the senior manager tier: {oth_t['focus_share']:.0%} of other managers, "
        f"{sen_t['focus_share']:.0%} of senior managers, {exec_t['focus_share']:.0%} of executives.",
        f"2.  Against other universities, {F} is {abs(st['diff']) * 100:.1f} points lower on women in senior management "
        f"(95% CI {abs(st['ci_high']) * 100:.1f} to {abs(st['ci_low']) * 100:.1f}). Suggestive, not conclusive.",
        f"3.  The gap has widened since {y0} because the sector improved while {F} held steady.",
        f"4.  Promotions are not the explanation on current evidence: over three years women received promotions "
        f"in line with their share of staff.",
        f"5.  One caveat governs every comparison: universities classify 'managers' very differently.",
    ], size=15)

    _chart_slide(prs, 3, f"Women are {oth_t['focus_share']:.0%} of {F}'s 'other managers' but {sen_t['focus_share']:.0%} of its senior managers",
                 figs["tiers"], [
                     f"Up to 'other manager' level, women are represented at or above their {row['women_share']:.0%} share of the workforce.",
                     f"The step down happens at senior manager level ({int(sen_t['focus_n'])} roles) and continues to executive level ({int(exec_t['focus_n'])} roles).",
                     f"The pattern is statistically clear within {F} (chi-square p < 0.001), though modest in size (Cramer's V = {r['tier_test']['cramers_v']:.2f}).",
                     "Key management personnel is only 9 people: the wide bar shows how little that percentage can tell us.",
                 ], f"Workplace profile {y1}. Bars are 95% Wilson intervals. Dashed line = 50%.")

    _chart_slide(prs, 4, f"On women in senior management, {F} is below the sector, but within the range chance could produce",
                 figs["funnel"], [
                     f"{F}: {st['focus']:.1%} of {st['n_focus']} senior roles. Other universities: {st['rest']:.1%}.",
                     f"The funnel shows how far a university of each size could sit from the sector average by chance. "
                     f"{F} is outside the inner (95%) limit and inside the outer (99.8%) limit (z = {z:.1f}).",
                     f"With {n_uni} universities, one or two will cross the inner limit by chance alone. "
                     f"{beyond} cross the outer limit.",
                     "A ranking alone would overstate this: most universities here cannot be told apart statistically.",
                 ], "Each dot is a university. Limits are binomial control limits around the pooled sector rate.",
                 panel_title="How to read this")

    _chart_slide(prs, 5, f"The gap has widened because the sector moved and {F} did not",
                 figs["trend"], [
                     f"{F}: {tr.loc[('women_senior_share', y0), 'focus']:.1%} in {y0}, {tr.loc[('women_senior_share', y1), 'focus']:.1%} in {y1}.",
                     f"Sector: {tr.loc[('women_senior_share', y0), 'sector']:.1%} to {tr.loc[('women_senior_share', y1), 'sector']:.1%}.",
                     f"Three points are a direction, not a trend. Worth re-checking when {int(y1[:4]) + 1}-{int(y1[-2:]) + 1} data is published.",
                     "Sector line uses the 36 universities that reported in all three years, so it is not distorted by universities entering or leaving the data.",
                 ], "Women's share of senior management. Balanced panel of universities reporting in all three years.")

    _chart_slide(prs, 6, f"A weak promotion year in {y1} is not a pattern: over three years promotions track women's share of staff",
                 figs["promotions"], [
                     f"In {y1} women received {py['share']:.0%} of {py['promotions']} promotions against {py['expected']:.0%} of non-casual staff. "
                     f"That ranks {sc.loc['promo_parity', 'rank']} of {sc.loc['promo_parity', 'of']} and looks alarming.",
                     f"But the interval is wide on {py['promotions']} promotions. Pooling three years ({pp['promotions']} promotions) gives "
                     f"{pp['share']:.0%}, consistent with parity (p = {pp['p']:.2f}).",
                     "The public data cannot show promotion into senior roles specifically, which is the question that matters here. "
                     "That needs the University's own HR data.",
                 ], "Non-casual staff. Vertical bars are 95% Wilson intervals; orange lines are the expected share.")

    _chart_slide(prs, 7, f"Caution: {F} classifies {row['manager_share']:.0%} of staff as managers, more than twice the median",
                 figs["manager_share"], [
                     "Each employer decides how its roles map to WGEA's manager categories.",
                     f"Universities report between {ms.min():.0%} and {ms.max():.0%} of employees as managers (median {ms.median():.0%}). "
                     f"{F} reports {int(row['senior'])} senior management roles"
                     + (", the most of any university." if row["senior"] == t["senior"].max() else "."),
                     "So 'senior management' is a broader group here than elsewhere, and likely includes roles that other universities report as professionals.",
                     f"The within-{F} step-down (slide 3) is unaffected. The sector comparison (slide 4) should be read with this in mind.",
                 ], f"Managers as a share of all employees reported, {y1}.", panel_title="Why this matters")

    s = _slide(prs, "What I would do next", 8)
    rows = [("Question", "Next step", "Data needed"),
            ("Is the senior-tier gap real or a classification effect?",
             "Re-cut by academic level (D/E) and HEW 10+ instead of WGEA categories",
             "Internal HR data; Department of Education staff statistics"),
            ("Where in the pipeline do women drop out?",
             "Track applications, shortlists and appointments to senior roles by gender",
             "Recruitment and promotion-round data"),
            ("Is it retention or appointment?", "Compare senior-level resignation and appointment rates by gender",
             "Internal movements data by level"),
            (f"What would closing the gap take?",
             f"{par.loc['Sector average', 'additional']} more women in senior management reaches the sector average; "
             f"{par.loc['50%', 'additional']} reaches 50%", "Vacancy and turnover forecasts for senior roles"),
            ("How does this intersect with other equity groups?",
             "Extend to Aboriginal and Torres Strait Islander staff and other groups, with small-number protections",
             "Internal data; not available in WGEA public files")]
    tbl = s.shapes.add_table(len(rows), 3, Inches(0.6), Inches(1.75), Inches(12.1), Inches(4.7)).table
    for j, w in enumerate([3.7, 4.9, 3.5]):
        tbl.columns[j].width = Inches(w)
    for i, rw in enumerate(rows):
        for j, val in enumerate(rw):
            cell = tbl.cell(i, j)
            cell.text = val
            cell.fill.solid()
            cell.fill.fore_color.rgb = NAVY if i == 0 else (PALE if i % 2 == 0 else WHITE)
            run = cell.text_frame.paragraphs[0].runs[0]
            run.font.size, run.font.name, run.font.bold = Pt(13), FONT, i == 0 or j == 0
            run.font.color.rgb = WHITE if i == 0 else INK
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE

    s = _slide(prs, "Appendix: data, method and limits", 9)
    nt = r["notes"]
    left = ["Data", f"WGEA public data files for {y0} to {y1} from data.gov.au. {nt['he_employers']} higher-education employers; "
                    f"{nt['universities']} are universities ({n_uni} reported in {y1}).",
            "Cleaning", f"{nt['subtotal_rows_removed']:,} subtotal rows removed from the {y0} movements file (they double-count "
                        f"{nt['subtotal_employees_removed']:,} appointments). Column names harmonised across years. Employer names fixed to one per ABN.",
            "Definitions", "Senior management = all WGEA manager tiers above 'other managers'. Promotion parity = women's share of "
                           "promotions / women's share of non-casual staff."]
    right = ["Statistical methods", "Two-proportion z-test with 95% CI; chi-square test with Cramer's V; exact binomial test; "
                                    "Wilson intervals; funnel plot with binomial control limits.",
             "Limits", "Manager categories are employer-defined. Gender is reported as women and men only. Headcount includes casuals "
                       "and depends on the snapshot date. Public data has no academic level, age, pay or Indigenous status.",
             "Reproducibility", "One command rebuilds the extract from source, the workbook, the charts and this deck. "
                                "Workbook formulas are reconciled to the Python results by automated tests."]
    for x, lines in ((0.6, left), (6.9, right)):
        tf = _text(s, Inches(x), Inches(1.75), Inches(5.8), Inches(5), lines, size=13)
        for p in tf.paragraphs[::2]:
            p.runs[0].font.bold, p.runs[0].font.color.rgb, p.space_after = True, NAVY, Pt(2)

    path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(path)
    return path
