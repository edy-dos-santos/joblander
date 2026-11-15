"""Build the executive briefing deck (PowerPoint) from the analysis results.

Each content slide follows the same pattern: a headline that states the finding,
one chart as evidence, and a short "what it means / what to do" panel written
for a non-technical audience. Numbers are pulled from the results dict, never typed.
"""
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from . import config as c
from .analysis import years_to_target

NAVY, BLUE, INK, INK2, PALE, RULE = (RGBColor.from_string(x) for x in
                                     ("0D366B", "2A78D6", "0B0B0B", "52514E", "EEF4FC", "C3C2B7"))
WHITE = RGBColor(255, 255, 255)
W, H = Inches(13.333), Inches(7.5)
FONT = "Calibri"


def _text(slide, x, y, w, h, text, size=14, bold=False, colour=INK, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap, tf.vertical_anchor = True, anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    lines = text if isinstance(text, list) else [text]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(size * 0.55)
        run = p.add_run()
        run.text = line
        run.font.name, run.font.size, run.font.bold, run.font.color.rgb = FONT, Pt(size), bold, colour
    return box


def _rect(slide, x, y, w, h, fill):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def _slide(prs, headline, n):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    _rect(s, 0, 0, Inches(0.18), H, NAVY)
    _text(s, Inches(0.6), Inches(0.4), Inches(12.1), Inches(1.1), headline, size=26, bold=True, colour=NAVY,
          anchor=MSO_ANCHOR.MIDDLE)
    _text(s, Inches(0.6), Inches(7.02), Inches(9), Inches(0.3),
          f"{c.UNIVERSITY} (fictional)  |  Workforce briefing as at {c.SNAPSHOT:%d %B %Y}  |  Synthetic data", size=10, colour=INK2)
    _text(s, Inches(12.0), Inches(7.02), Inches(0.75), Inches(0.3), str(n), size=10, colour=INK2, align=PP_ALIGN.RIGHT)
    return s


def _panel(slide, title, bullets, x=Inches(8.75), y=Inches(1.75), w=Inches(4.0), h=Inches(4.95)):
    _rect(slide, x, y, w, h, PALE)
    _text(slide, x + Inches(0.25), y + Inches(0.22), w - Inches(0.5), Inches(0.4), title, size=14, bold=True, colour=NAVY)
    _text(slide, x + Inches(0.25), y + Inches(0.75), w - Inches(0.5), h - Inches(0.9), bullets, size=13, colour=INK)


def _chart_slide(prs, n, headline, image, panel_title, bullets, source):
    s = _slide(prs, headline, n)
    pic = s.shapes.add_picture(str(image), Inches(0.6), Inches(1.75), width=Inches(7.8))
    max_h = Inches(4.75)
    if pic.height > max_h:  # keep aspect ratio, fit to height
        ratio = max_h / pic.height
        pic.height, pic.width = int(max_h), int(pic.width * ratio)
    _panel(s, panel_title, bullets)
    _text(s, Inches(0.6), Inches(6.62), Inches(7.8), Inches(0.3), source, size=10, colour=INK2)
    return s


def build(r, figs, path=None):
    path = path or c.OUT / "Workforce_Briefing.pptx"
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H
    y0, y1 = c.REPORT_YEARS[0], c.REPORT_YEARS[-1]
    t, pg, sen = r["turnover_trend"], r["pay_gap"], r["senior"]
    ind, d, orr, ret = r["indigenous"].iloc[-1], r["digital_vs_rest"], r["odds_ratios"], r["retirement"]
    sc = {k: years_to_target(v) for k, v in r["scenarios"].items()}
    top_ret = ret.index[0]
    uni_ret = ret["reaching_65"].sum() / ret["ongoing_headcount"].sum()
    by_div = r["by_division"]
    insecure = (by_div["Fixed-term"].sum() + by_div["Casual"].sum()) / by_div["headcount"].sum()
    early = r["resignation_by_tenure"]
    insecure_by = (by_div["Fixed-term"] + by_div["Casual"]) / by_div["headcount"]
    insecure_top = insecure_by.idxmax()

    # 1 Title
    s = prs.slides.add_slide(prs.slide_layouts[6])
    _rect(s, 0, 0, W, H, NAVY)
    _text(s, Inches(0.9), Inches(2.3), Inches(11.5), Inches(1.2), "Workforce insights briefing", size=44, bold=True, colour=WHITE)
    _text(s, Inches(0.9), Inches(3.5), Inches(11.5), Inches(0.6),
          f"{c.UNIVERSITY}  |  Workforce as at {c.SNAPSHOT:%d %B %Y}", size=22, colour=WHITE)
    _text(s, Inches(0.9), Inches(5.9), Inches(11.5), Inches(0.8),
          ["Portfolio project. Riverbend University is fictional and all data is synthetic - no real people are represented."],
          size=13, colour=RGBColor.from_string("CDE2FB"))

    # 2 Executive summary
    s = _slide(prs, "Four things leaders should know about the workforce", 2)
    tiles = [(f"{r['headcount']:,}", f"staff ({r['fte']:,.0f} FTE)"),
             (f"{t.loc[y1, 'voluntary_rate']:.1%}", f"resignation rate, {y1}"),
             (f"{sen['women_share_senior']:.0%}", "of senior roles held by women"),
             (f"{ind['share']:.1%}", f"Indigenous representation (target {c.INDIGENOUS_TARGET:.0%})")]
    for i, (num, label) in enumerate(tiles):
        x = Inches(0.6) + i * Inches(3.07)
        _rect(s, x, Inches(1.7), Inches(2.9), Inches(1.55), PALE)
        _text(s, x + Inches(0.2), Inches(1.8), Inches(2.5), Inches(0.8), num, size=34, bold=True, colour=NAVY)
        _text(s, x + Inches(0.2), Inches(2.62), Inches(2.5), Inches(0.5), label, size=12, colour=INK2)
    msgs = [
        f"1.  Turnover has settled after the {y0} spike, but resignations are concentrated: fixed-term staff, people in "
        f"their first two years, and Digital & Technology ({d['rate_group']:.1%} a year vs {d['rate_rest']:.1%} elsewhere).",
        f"2.  The {pg['overall']:.1%} gender pay gap is almost entirely structural. At the same classification the gap is "
        f"{pg['like_for_like']:.1%}; the rest reflects who holds senior roles.",
        f"3.  Indigenous representation is {ind['share']:.1%} against a {c.INDIGENOUS_TARGET:.0%} target. "
        f"At the current hiring mix the target is not reached within ten years.",
        f"4.  {ret.loc[top_ret, 'share']:.0%} of ongoing staff in the {top_ret} reach 65 within five years - "
        f"about double the university rate ({uni_ret:.0%}).",
    ]
    _text(s, Inches(0.6), Inches(3.6), Inches(12.1), Inches(3.2), msgs, size=15)

    # 3 Shape
    _chart_slide(prs, 3, f"The workforce has grown modestly to {r['headcount']:,}; about one in four staff are not ongoing",
                 figs["headcount"], "What it means", [
                     f"Headcount is up {r['headcount'] / r['headcount_trend']['headcount'].iloc[0] - 1:.1%} since the end of {y0 - 1}.",
                     f"{insecure:.0%} of staff are fixed-term or casual, highest in the {insecure_top} ({insecure_by.max():.0%}).",
                     "Fixed-term reliance matters for the next slides: it is the strongest structural driver of resignations.",
                 ], f"Headcount at {c.SNAPSHOT:%d %b %Y}. See 'Headcount' sheet in the workbook.")

    # 4 Turnover trend
    _chart_slide(prs, 4, f"Turnover has eased since {y0}, with a small rise in {y1} worth watching",
                 figs["turnover_trend"], "What it means", [
                     f"Total separations fell from {t.loc[y0, 'total_rate']:.1%} to {t.loc[y1, 'total_rate']:.1%}; "
                     f"resignations from {t.loc[y0, 'voluntary_rate']:.1%} to {t.loc[y1, 'voluntary_rate']:.1%}.",
                     f"{y1} is up on {y1 - 1}. One year is not a trend - monitor quarterly before acting.",
                     "Casual staff are excluded: their engagements end by design and would overstate turnover.",
                 ], "Rate = separations / average of opening and closing headcount, non-casual staff.")

    # 5 Hotspots
    _chart_slide(prs, 5, "Digital & Technology loses staff to resignation faster than any other area",
                 figs["resignation_division"], "What it means", [
                     f"{d['rate_group']:.1%} of Digital & Technology staff resign each year, against {d['rate_rest']:.1%} elsewhere.",
                     f"The gap is {d['diff'] * 100:.1f} points (95% CI {d['ci_low'] * 100:.1f} to {d['ci_high'] * 100:.1f}), "
                     "so it is very unlikely to be chance.",
                     f"Four years are pooled ({y0}-{y1}) because single-year rates for small areas bounce around.",
                     "Suggested action: exit-interview review and a market pay check for hard-to-fill technology roles.",
                 ], f"Resignations per person-year, non-casual staff, {y0}-{y1} (n = {len(r['person_years']):,} person-years).")

    # 6 Drivers
    _chart_slide(prs, 6, "Contract type and early tenure - not gender or staff group - drive resignations",
                 figs["odds"], "What it means", [
                     f"Fixed-term staff have {orr.loc['Fixed-term (vs ongoing)', 'odds_ratio']:.1f}x the odds of resigning, after "
                     "allowing for age, tenure and area.",
                     f"Staff in their first two years resign at {early.loc['Under 2 yrs', 'mean']:.1%} a year, against "
                     f"{early.loc['5+ yrs', 'mean']:.1%} after five years.",
                     "Women and men, and academic and professional staff, resign at statistically similar rates.",
                     "Suggested action: target onboarding and 12-month check-ins; review conversion pathways for long-serving fixed-term staff.",
                 ], "Logistic regression on person-years; standard errors clustered by employee. Associations, not proof of cause.")

    # 7 Gender
    _chart_slide(prs, 7, f"Women are {sen['women_share_all']:.0%} of staff but only {sen['women_share_senior']:.0%} of senior roles",
                 figs["women"], "What it means", [
                     "Representation falls away at Level D and E and at HEW 10+ (dark bars).",
                     f"This explains the pay gap: {pg['overall']:.1%} overall, but {pg['like_for_like']:.1%} between women and men "
                     "at the same classification.",
                     f"Roughly {pg['structural'] / pg['overall']:.0%} of the gap is about progression, not unequal pay for the same level.",
                     "Suggested action: focus on promotion and senior recruitment pipelines; audit the residual like-for-like gap (loadings).",
                 ], "Pay gap on FTE-annualised base salary, non-casual staff. Dashed line = 50%.")

    # 8 Indigenous representation
    def phrase(v):
        return f"reached in about {v} years" if v else "not reached within 10 years"
    _chart_slide(prs, 8, "Indigenous representation is rising slowly; current hiring will not reach the target",
                 figs["indigenous"], "What it means", [
                     f"{ind['share']:.1%} of staff identify as Aboriginal and/or Torres Strait Islander "
                     f"(95% CI {ind['ci_low']:.1%} to {ind['ci_high']:.1%}), up from {r['indigenous']['share'].iloc[0]:.1%} in {y0 - 1}.",
                     f"Target of {c.INDIGENOUS_TARGET:.0%}: {phrase(sc['Current hiring mix'])} at the current hiring mix; "
                     f"{phrase(sc['5% of hires'])} at 5% of hires; {phrase(sc['8% of hires'])} at 8%.",
                     f"{ind['not_disclosed_share']:.0%} of staff have not disclosed, so true representation may be higher.",
                     "Any action here should be designed with Indigenous staff and the University's Indigenous leadership. "
                     "Results are reported at university level only, to protect privacy.",
                 ], "Shaded band = 95% Wilson interval. Dashed lines = scenarios from the workbook's 'Scenario' sheet.")

    # 9 Retirement
    _chart_slide(prs, 9, f"The {top_ret} faces a retirement wave within five years",
                 figs["retirement"], "What it means", [
                     f"{int(ret.loc[top_ret, 'reaching_65'])} ongoing staff ({ret.loc[top_ret, 'share']:.0%}) reach 65 by "
                     f"{c.SNAPSHOT.year + 5}, about double the university rate of {uni_ret:.0%}.",
                     f"The next most exposed area is the {ret.index[1]} at {ret['share'].iloc[1]:.0%}.",
                     "Reaching 65 is not the same as retiring: this is an upper bound for planning, not a prediction about individuals.",
                     "Suggested action: succession planning and phased-retirement conversations with the faculty.",
                 ], "Ongoing staff only. Age is used in aggregate for planning and never for decisions about individuals.")

    # 10 Recommendations
    s = _slide(prs, "Recommended next steps", 10)
    rows = [("Finding", "Recommended action", "How we will know it worked"),
            ("Digital & Technology resignations", "Exit-interview themes and market pay check for technology roles",
             "Resignation rate within 2 points of university average"),
            ("Early-tenure and fixed-term attrition", "Structured onboarding; 12-month check-in; review conversion pathways",
             "First-two-year resignation rate falling year on year"),
            ("Women under-represented in senior roles", "Promotion-round and senior-recruitment pipeline analysis by gender",
             "Women's share of Level D/E and HEW 10+ appointments"),
            ("Indigenous representation below target", "Co-design a hiring and retention plan; encourage self-identification",
             "Share of new hires; representation tracked quarterly"),
            (f"Retirement exposure in {top_ret.replace('Faculty of ', '')}", "Succession plans for roles held by staff aged 60+",
             "Critical roles with an identified successor")]
    tbl = s.shapes.add_table(len(rows), 3, Inches(0.6), Inches(1.75), Inches(12.1), Inches(4.6)).table
    for j, w in enumerate([3.5, 4.8, 3.8]):
        tbl.columns[j].width = Inches(w)
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = tbl.cell(i, j)
            cell.text = val
            cell.fill.solid()
            cell.fill.fore_color.rgb = NAVY if i == 0 else (PALE if i % 2 == 0 else WHITE)
            p = cell.text_frame.paragraphs[0]
            p.runs[0].font.size, p.runs[0].font.name = Pt(13), FONT
            p.runs[0].font.bold = i == 0 or j == 0
            p.runs[0].font.color.rgb = WHITE if i == 0 else INK
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE

    # 11 Method
    s = _slide(prs, "Appendix: how these numbers were produced", 11)
    _text(s, Inches(0.6), Inches(1.75), Inches(5.8), Inches(5), [
        "Data",
        f"Synthetic HR extract of {len(r['df']):,} employment records, {c.SIM_START.year}-{y1}. Eleven validation rules; "
        "every correction is logged in data_quality_log.csv.",
        "Definitions",
        "Turnover excludes casual staff and uses average headcount. Resignation = employee-initiated separation. "
        "Pay gap uses FTE-annualised base salary. Senior = Level D, E and HEW 10+.",
        "Privacy",
        f"Counts under {c.SMALL_CELL_THRESHOLD} are suppressed. Indigenous and non-binary results are reported at university level only.",
    ], size=13)
    _text(s, Inches(6.9), Inches(1.75), Inches(5.8), Inches(5), [
        "Statistical methods",
        "Chi-square test of independence; two-proportion z-test with 95% confidence interval; Wilson interval for small "
        "proportions; logistic regression with employee-clustered standard errors.",
        "Limits",
        "The model shows association, not cause. Single-year rates for small areas are volatile. The scenario model "
        "assumes constant separation and identification rates.",
        "Reproducibility",
        "Workbook figures are live Excel formulas, reconciled to the Python results by automated tests. "
        "One command rebuilds the data, workbook, charts and this deck.",
    ], size=13)
    for sh in s.shapes:  # bold the sub-headings
        if sh.has_text_frame:
            for p in sh.text_frame.paragraphs:
                if p.runs and p.runs[0].text in ("Data", "Definitions", "Privacy", "Statistical methods", "Limits", "Reproducibility"):
                    p.runs[0].font.bold, p.runs[0].font.color.rgb = True, NAVY
                    p.space_after = Pt(2)

    path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(path)
    return path
