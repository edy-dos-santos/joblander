"""Build the Excel workforce report.

Every figure in the workbook is a live Excel formula (COUNTIFS / SUMIFS /
AVERAGEIFS / SUMPRODUCT) over the 'Data' sheet, not a pasted value, so a reader
can trace any number back to the records behind it and the report refreshes
when the data is replaced. tests/test_excel_reconciliation.py recalculates the
workbook and checks the formulas agree with the Python metrics.
"""
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from . import config as c
from .clean import load_clean

NAVY, BLUE, PALE, INPUT = "0D366B", "2A78D6", "EEF4FC", "FFF6D6"
H1 = Font(name="Calibri", size=16, bold=True, color=NAVY)
H2 = Font(name="Calibri", size=12, bold=True, color=NAVY)
NOTE = Font(name="Calibri", size=9, italic=True, color="52514E")
HEAD = Font(name="Calibri", bold=True, color="FFFFFF")
BOLD = Font(name="Calibri", bold=True)
THIN = Side(style="thin", color="C3C2B7")
PCT, INT, DEC, MONEY, DATE = "0.0%", "#,##0", "#,##0.0", "$#,##0", "d mmm yyyy"

DATA_COLS = ["employee_id", "division", "staff_group", "classification", "employment_type", "fte", "gender",
             "date_of_birth", "indigenous_status", "start_date", "end_date", "separation_reason",
             "base_salary_fte", "active", "age", "age_band", "tenure_years", "senior", "separation_year"]
SNAP = "Dashboard!$C$4"   # the as-at date every snapshot formula points to


class Book:
    def __init__(self, df):
        self.df = df
        self.n = len(df)
        self.wb = Workbook()
        self.col = {name: get_column_letter(i + 1) for i, name in enumerate(DATA_COLS)}

    def rng(self, name):
        L = self.col[name]
        return f"Data!${L}$2:${L}${self.n + 1}"

    def countifs(self, *pairs):
        """COUNTIFS over Data columns. pairs = (column, criterion-expression) ..."""
        return "COUNTIFS(" + ",".join(f"{self.rng(col)},{crit}" for col, crit in pairs) + ")"

    def header(self, ws, row, labels, start_col=1):
        for i, label in enumerate(labels):
            cell = ws.cell(row=row, column=start_col + i, value=label)
            cell.font, cell.fill = HEAD, PatternFill("solid", fgColor=NAVY)
            cell.alignment = Alignment(horizontal="center" if i else "left", vertical="center", wrap_text=True)
        ws.row_dimensions[row].height = 32

    @staticmethod
    def widths(ws, widths):
        for i, w in enumerate(widths):
            ws.column_dimensions[get_column_letter(i + 1)].width = w

    @staticmethod
    def title(ws, text, sub=None):
        ws["A1"].value, ws["A1"].font = text, H1
        if sub:
            ws["A2"].value, ws["A2"].font = sub, NOTE
        ws.sheet_view.showGridLines = False

    @staticmethod
    def total_row(ws, row, ncols):
        for col in range(1, ncols + 1):
            cell = ws.cell(row=row, column=col)
            cell.font, cell.border = BOLD, Border(top=THIN)


def build_data(b):
    ws = b.wb.create_sheet("Data")
    b.header(ws, 1, DATA_COLS)
    df = b.df
    L = b.col
    for i, rec in enumerate(df.itertuples(index=False), start=2):
        row = [rec.employee_id, rec.division, rec.staff_group, rec.classification, rec.employment_type,
               float(rec.fte), rec.gender, rec.date_of_birth.to_pydatetime(), rec.indigenous_status,
               rec.start_date.to_pydatetime(),
               None if rec.end_date != rec.end_date else rec.end_date.to_pydatetime(),
               None if rec.separation_reason != rec.separation_reason else rec.separation_reason,
               int(rec.base_salary_fte),
               f'=IF(AND({L["start_date"]}{i}<={SNAP},OR({L["end_date"]}{i}="",{L["end_date"]}{i}>{SNAP})),1,0)',
               int(rec.age), rec.age_band, float(rec.tenure_years), int(rec.senior),
               f'=IF({L["end_date"]}{i}="","",YEAR({L["end_date"]}{i}))']
        ws.append(row)
    for name in ("date_of_birth", "start_date", "end_date"):
        for cell in ws[L[name]][1:]:
            cell.number_format = DATE
    for cell in ws[L["base_salary_fte"]][1:]:
        cell.number_format = MONEY
    b.widths(ws, [12, 28, 13, 14, 16, 6, 12, 13, 38, 12, 12, 18, 14, 8, 6, 10, 12, 8, 14])
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(DATA_COLS))}{b.n + 1}"


def build_headcount(b):
    ws = b.wb.create_sheet("Headcount")
    b.title(ws, "Headcount and FTE by organisational area",
            "Staff employed at the as-at date on the Dashboard. All cells are formulas over the Data sheet.")
    b.header(ws, 4, ["Organisational area", *c.EMPLOYMENT_TYPES, "Headcount", "FTE", "% of headcount",
                     "Fixed-term + casual %", "Women %"])
    first = 5
    for i, d in enumerate(c.DIVISIONS):
        r = first + i
        ws.cell(row=r, column=1, value=d)
        for j, t in enumerate(c.EMPLOYMENT_TYPES):
            ws.cell(row=r, column=2 + j, value="=" + b.countifs(("active", 1), ("division", f"$A{r}"),
                                                              ("employment_type", f"{get_column_letter(2 + j)}$4")))
        ws.cell(row=r, column=5, value=f"=SUM(B{r}:D{r})")
        ws.cell(row=r, column=6, value=f'=SUMIFS({b.rng("fte")},{b.rng("active")},1,{b.rng("division")},$A{r})')
        ws.cell(row=r, column=7, value=f"=E{r}/E${first + len(c.DIVISIONS)}")
        ws.cell(row=r, column=8, value=f"=(C{r}+D{r})/E{r}")
        ws.cell(row=r, column=9, value="=" + b.countifs(("active", 1), ("division", f"$A{r}"),
                                                        ("gender", '"Woman"')) + f"/E{r}")
    last = first + len(c.DIVISIONS) - 1
    tot = last + 1
    ws.cell(row=tot, column=1, value="University")
    for col in range(2, 7):
        L = get_column_letter(col)
        ws.cell(row=tot, column=col, value=f"=SUM({L}{first}:{L}{last})")
    ws.cell(row=tot, column=7, value=f"=E{tot}/E{tot}")
    ws.cell(row=tot, column=8, value=f"=(C{tot}+D{tot})/E{tot}")
    ws.cell(row=tot, column=9, value="=" + b.countifs(("active", 1), ("gender", '"Woman"')) + f"/E{tot}")
    b.total_row(ws, tot, 9)
    for r in range(first, tot + 1):
        for col, fmt in zip(range(2, 10), [INT, INT, INT, INT, DEC, PCT, PCT, PCT]):
            ws.cell(row=r, column=col).number_format = fmt
    b.widths(ws, [30, 11, 11, 11, 12, 11, 14, 14, 11])
    ws.freeze_panes = "B5"
    b.cells["headcount_total"] = f"Headcount!$E${tot}"
    b.cells["fte_total"] = f"Headcount!$F${tot}"
    b.pos["headcount"] = (first, last)


def _stock(b, date_expr, extra=()):
    """Non-casual headcount at a date = started on/before it, minus those who had left by it."""
    base = [("employment_type", '"<>Casual"'), *extra]
    return (b.countifs(("start_date", f'"<="&{date_expr}'), *base) + "-"
            + b.countifs(("end_date", f'"<="&{date_expr}'), *base))


def build_turnover(b):
    ws = b.wb.create_sheet("Turnover")
    b.title(ws, "Separation and resignation rates",
            "Non-casual staff. Rate = separations in the year / average of opening and closing headcount.")
    cols = ["Year", "Opening headcount", "Closing headcount", "Separations", "Resignations",
            "Average headcount", "Total separation rate", "Resignation rate"]
    b.header(ws, 4, cols)
    first = 5
    for i, y in enumerate(c.REPORT_YEARS):
        r = first + i
        ws.cell(row=r, column=1, value=y)
        ws.cell(row=r, column=2, value="=" + _stock(b, f"DATE($A{r}-1,12,31)"))
        ws.cell(row=r, column=3, value="=" + _stock(b, f"DATE($A{r},12,31)"))
        ws.cell(row=r, column=4, value="=" + b.countifs(("separation_year", f"$A{r}"),
                                                        ("employment_type", '"<>Casual"')))
        ws.cell(row=r, column=5, value="=" + b.countifs(("separation_year", f"$A{r}"),
                                                        ("employment_type", '"<>Casual"'),
                                                        ("separation_reason", '"Resignation"')))
        ws.cell(row=r, column=6, value=f"=AVERAGE(B{r}:C{r})")
        ws.cell(row=r, column=7, value=f"=D{r}/F{r}")
        ws.cell(row=r, column=8, value=f"=E{r}/F{r}")
        for col, fmt in zip(range(2, 9), [INT, INT, INT, INT, DEC, PCT, PCT]):
            ws.cell(row=r, column=col).number_format = fmt
    last = first + len(c.REPORT_YEARS) - 1
    b.pos["turnover"] = (first, last)
    b.cells["total_rate"] = f"Turnover!$G${last}"
    b.cells["resign_rate"] = f"Turnover!$H${last}"

    # By area for a user-selected year
    top = last + 3
    ws.cell(row=top, column=1, value="By organisational area").font = H2
    ws.cell(row=top + 1, column=1, value="Select year:").font = BOLD
    sel = ws.cell(row=top + 1, column=2, value=c.REPORT_YEARS[-1])
    sel.fill, sel.font = PatternFill("solid", fgColor=INPUT), BOLD
    dv = DataValidation(type="list", formula1='"' + ",".join(map(str, c.REPORT_YEARS)) + '"', allow_blank=False)
    ws.add_data_validation(dv)
    dv.add(sel)
    ws.cell(row=top + 1, column=3, value="(yellow cells are inputs - use the drop-down)").font = NOTE
    Y = f"$B${top + 1}"
    b.header(ws, top + 3, ["Organisational area", *cols[1:], "vs university (pts)"])
    f2 = top + 4
    for i, d in enumerate(c.DIVISIONS):
        r = f2 + i
        div = ("division", f"$A{r}")
        ws.cell(row=r, column=1, value=d)
        ws.cell(row=r, column=2, value="=" + _stock(b, f"DATE({Y}-1,12,31)", [div]))
        ws.cell(row=r, column=3, value="=" + _stock(b, f"DATE({Y},12,31)", [div]))
        ws.cell(row=r, column=4, value="=" + b.countifs(("separation_year", Y), ("employment_type", '"<>Casual"'), div))
        ws.cell(row=r, column=5, value="=" + b.countifs(("separation_year", Y), ("employment_type", '"<>Casual"'),
                                                        ("separation_reason", '"Resignation"'), div))
        ws.cell(row=r, column=6, value=f"=AVERAGE(B{r}:C{r})")
        ws.cell(row=r, column=7, value=f"=IFERROR(D{r}/F{r},0)")
        ws.cell(row=r, column=8, value=f"=IFERROR(E{r}/F{r},0)")
        ws.cell(row=r, column=9, value=f"=(H{r}-INDEX($H${first}:$H${last},MATCH({Y},$A${first}:$A${last},0)))*100")
        for col, fmt in zip(range(2, 10), [INT, INT, INT, INT, DEC, PCT, PCT, '+0.0;-0.0;0.0']):
            ws.cell(row=r, column=col).number_format = fmt
    ws.cell(row=f2 + len(c.DIVISIONS) + 1, column=1,
            value="Single-year rates for small areas are volatile: treat differences of a few points with caution.").font = NOTE
    b.widths(ws, [30, 12, 12, 12, 13, 12, 13, 13, 13])


def build_equity(b):
    ws = b.wb.create_sheet("Equity")
    b.title(ws, "Equity and diversity indicators",
            "Staff employed at the as-at date. Small counts are deliberately not broken down (see Definitions).")

    ws["A4"].value, ws["A4"].font = "Gender representation by classification", H2
    b.header(ws, 5, ["Classification", "Women", "Men", "All staff", "Women %", "Senior level?"])
    first = 6
    for i, lv in enumerate(c.LEVELS):
        r = first + i
        ws.cell(row=r, column=1, value=lv)
        ws.cell(row=r, column=2, value="=" + b.countifs(("active", 1), ("classification", f"$A{r}"), ("gender", '"Woman"')))
        ws.cell(row=r, column=3, value="=" + b.countifs(("active", 1), ("classification", f"$A{r}"), ("gender", '"Man"')))
        ws.cell(row=r, column=4, value="=" + b.countifs(("active", 1), ("classification", f"$A{r}")))
        ws.cell(row=r, column=5, value=f"=B{r}/D{r}")
        ws.cell(row=r, column=6, value="Yes" if lv in c.SENIOR_LEVELS else "")
    last = first + len(c.LEVELS) - 1
    tot = last + 1
    ws.cell(row=tot, column=1, value="University")
    for col in (2, 3, 4):
        L = get_column_letter(col)
        ws.cell(row=tot, column=col, value=f"=SUM({L}{first}:{L}{last})")
    ws.cell(row=tot, column=5, value=f"=B{tot}/D{tot}")
    b.total_row(ws, tot, 6)
    ws.cell(row=tot + 1, column=1, value="Women in senior roles (Level D, E, HEW 10+)")
    ws.cell(row=tot + 1, column=5, value=f'=SUMIFS(B{first}:B{last},F{first}:F{last},"Yes")/SUMIFS(D{first}:D{last},F{first}:F{last},"Yes")')
    ws.cell(row=tot + 2, column=1, value="Non-binary staff (university total only)")
    ws.cell(row=tot + 2, column=4, value=f"=D{tot}-B{tot}-C{tot}")
    for r in range(first, tot + 3):
        for col in (2, 3, 4):
            ws.cell(row=r, column=col).number_format = INT
        ws.cell(row=r, column=5).number_format = PCT
    b.cells["women_senior"] = f"Equity!$E${tot + 1}"
    b.cells["women_all"] = f"Equity!$E${tot}"

    # Pay gap
    p0 = tot + 5
    ws.cell(row=p0, column=1, value="Gender pay gap - FTE-annualised base salary, non-casual staff").font = H2
    b.header(ws, p0 + 1, ["Classification", "Women (n)", "Men (n)", "Women mean salary", "Men mean salary", "Gap %"])
    pf = p0 + 2
    nc = ("employment_type", '"<>Casual"')
    for i, lv in enumerate(c.LEVELS):
        r = pf + i
        ws.cell(row=r, column=1, value=lv)
        for col, g in ((2, "Woman"), (3, "Man")):
            ws.cell(row=r, column=col, value="=" + b.countifs(("active", 1), nc, ("classification", f"$A{r}"),
                                                              ("gender", f'"{g}"')))
        for col, g in ((4, "Woman"), (5, "Man")):
            ws.cell(row=r, column=col, value=(
                f'=AVERAGEIFS({b.rng("base_salary_fte")},{b.rng("active")},1,{b.rng("employment_type")},"<>Casual",'
                f'{b.rng("classification")},$A{r},{b.rng("gender")},"{g}")'))
        ws.cell(row=r, column=6, value=f"=(E{r}-D{r})/E{r}")
    pl = pf + len(c.LEVELS) - 1
    pt = pl + 1
    ws.cell(row=pt, column=1, value="All classifications (overall gap)")
    ws.cell(row=pt, column=2, value=f"=SUM(B{pf}:B{pl})")
    ws.cell(row=pt, column=3, value=f"=SUM(C{pf}:C{pl})")
    for col, g in ((4, "Woman"), (5, "Man")):
        ws.cell(row=pt, column=col, value=(
            f'=AVERAGEIFS({b.rng("base_salary_fte")},{b.rng("active")},1,{b.rng("employment_type")},"<>Casual",'
            f'{b.rng("gender")},"{g}")'))
    ws.cell(row=pt, column=6, value=f"=(E{pt}-D{pt})/E{pt}")
    b.total_row(ws, pt, 6)
    ws.cell(row=pt + 1, column=1, value="Like-for-like gap (within-level gaps weighted by women's headcount)")
    ws.cell(row=pt + 1, column=6, value=f"=SUMPRODUCT(F{pf}:F{pl},B{pf}:B{pl})/SUM(B{pf}:B{pl})")
    ws.cell(row=pt + 2, column=1, value="Structural component (overall minus like-for-like)")
    ws.cell(row=pt + 2, column=6, value=f"=F{pt}-F{pt + 1}")
    for r in range(pf, pt + 3):
        for col, fmt in zip(range(2, 7), [INT, INT, MONEY, MONEY, PCT]):
            ws.cell(row=r, column=col).number_format = fmt
    b.cells["pay_gap"] = f"Equity!$F${pt}"
    b.cells["pay_gap_lfl"] = f"Equity!$F${pt + 1}"

    # Indigenous representation
    i0 = pt + 5
    ws.cell(row=i0, column=1, value="Aboriginal and Torres Strait Islander workforce representation").font = H2
    rows = [
        ("Staff who identify as Aboriginal and/or Torres Strait Islander",
         "=" + b.countifs(("active", 1), ("indigenous_status", f'"{c.INDIGENOUS_YES}"')), INT),
        ("Total headcount", f"={b.cells['headcount_total']}", INT),
        ("Representation (share of headcount)", f"=B{i0 + 1}/B{i0 + 2}", "0.00%"),
        ("Target", c.INDIGENOUS_TARGET, "0.00%"),
        ("Additional staff needed to meet target at current headcount", f"=MAX(0,ROUNDUP(B{i0 + 4}*B{i0 + 2}-B{i0 + 1},0))", INT),
        ("Status not disclosed (share of headcount)",
         "=" + b.countifs(("active", 1), ("indigenous_status", '"Not disclosed"')) + f"/B{i0 + 2}", "0.00%"),
    ]
    for k, (label, value, fmt) in enumerate(rows, start=1):
        ws.cell(row=i0 + k, column=1, value=label)
        cell = ws.cell(row=i0 + k, column=2, value=value)
        cell.number_format = fmt
    ws.cell(row=i0 + 4, column=2).fill = PatternFill("solid", fgColor=INPUT)
    ws.cell(row=i0 + 8, column=1, value=(
        f"Not broken down by area: most cells would be below {c.SMALL_CELL_THRESHOLD} and could identify individuals.")).font = NOTE
    b.cells["indigenous_n"] = f"Equity!$B${i0 + 1}"
    b.cells["indigenous_share"] = f"Equity!$B${i0 + 3}"
    b.cells["indigenous_target"] = f"Equity!$B${i0 + 4}"
    b.widths(ws, [58, 13, 13, 18, 16, 13])


def build_scenario(b, inputs):
    ws = b.wb.create_sheet("Scenario")
    b.title(ws, "What-if: path to the Aboriginal and Torres Strait Islander representation target",
            "Change the yellow cells. Each year: identified staff = survivors + new hires x share of hires who identify.")
    rows = [
        ("Current headcount", f"={b.cells['headcount_total']}", INT, False),
        ("Staff who currently identify", f"={b.cells['indigenous_n']}", INT, False),
        ("Annual separation rate", f"=ROUND({b.cells['total_rate']},3)", PCT, True),
        ("Annual headcount growth", inputs["growth_rate"], PCT, True),
        ("Target representation", f"={b.cells['indigenous_target']}", PCT, False),
    ]
    for k, (label, value, fmt, is_input) in enumerate(rows):
        ws.cell(row=4 + k, column=1, value=label)
        cell = ws.cell(row=4 + k, column=2, value=value)
        cell.number_format = fmt
        if is_input:
            cell.fill = PatternFill("solid", fgColor=INPUT)
    ws.cell(row=10, column=1, value="Share of new hires who identify").font = BOLD
    shares = [inputs["current_hire_share"], 0.05, 0.08]
    labels = ["Current hiring mix", "Scenario A", "Scenario B"]
    for j, (lab, sh) in enumerate(zip(labels, shares)):
        ws.cell(row=9, column=2 + j, value=lab).font = BOLD
        cell = ws.cell(row=10, column=2 + j, value=sh)
        cell.number_format, cell.fill = PCT, PatternFill("solid", fgColor=INPUT)

    b.header(ws, 13, ["Year", "Headcount", *[f"{lab} - identified" for lab in labels],
                      *[f"{lab} - %" for lab in labels], "Target"])
    for t in range(0, 11):
        r = 14 + t
        ws.cell(row=r, column=1, value=t)
        ws.cell(row=r, column=2, value="=$B$4" if t == 0 else f"=B{r - 1}*(1+$B$7)").number_format = INT
        for j in range(3):
            idc, pc, sh = get_column_letter(3 + j), get_column_letter(6 + j), get_column_letter(2 + j)
            ws.cell(row=r, column=3 + j, value="=$B$5" if t == 0 else
                    f"={idc}{r - 1}*(1-$B$6)+$B{r - 1}*($B$6+$B$7)*${sh}$10").number_format = DEC
            ws.cell(row=r, column=6 + j, value=f"={idc}{r}/$B{r}").number_format = "0.00%"
        ws.cell(row=r, column=9, value="=$B$8").number_format = "0.00%"
    ws.cell(row=26, column=1, value="First year at or above target").font = BOLD
    for j in range(3):
        pc = get_column_letter(6 + j)
        ws.cell(row=26, column=6 + j,
                value=f'=IFERROR(INDEX($A$14:$A$24,MATCH(TRUE,INDEX({pc}14:{pc}24>=$B$8,0),0)),"Not within 10 yrs")')
    ws.cell(row=28, column=1, value=(
        "Simplifying assumptions: separation rate is the same for all staff and constant over time; "
        "self-identification rates do not change. A planning aid, not a forecast.")).font = NOTE

    ch = LineChart()
    ch.title, ch.height, ch.width = "Projected representation", 8.5, 17
    ch.y_axis.number_format, ch.y_axis.title, ch.x_axis.title = "0.0%", "Share of headcount", "Years from now"
    ch.add_data(Reference(ws, min_col=6, max_col=9, min_row=13, max_row=24), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=1, min_row=14, max_row=24))
    for s, colour in zip(ch.series, ["898781", "EB6834", "1BAF7A", "0B0B0B"]):
        s.graphicalProperties.line.solidFill = colour
        s.graphicalProperties.line.width = 22000
        s.smooth = False
    ch.series[3].graphicalProperties.line.dashStyle = "dash"
    ch.x_axis.delete = ch.y_axis.delete = False
    ws.add_chart(ch, "K4")
    b.widths(ws, [34, 13, 14, 14, 14, 14, 14, 14, 9])


def build_dashboard(b):
    ws = b.wb["Dashboard"]
    b.title(ws, f"{c.UNIVERSITY} - Workforce Dashboard")
    ws["A2"].value = "Synthetic data for demonstration only. Every figure is a live formula over the Data sheet."
    ws["A2"].font = NOTE
    ws["B4"].value, ws["B4"].font = "As at:", BOLD
    ws["C4"].value, ws["C4"].number_format = c.SNAPSHOT.to_pydatetime(), DATE
    ws["C4"].fill, ws["C4"].font = PatternFill("solid", fgColor=INPUT), BOLD
    ws["D4"].value, ws["D4"].font = "(input: change to re-run every snapshot measure)", NOTE

    y = c.REPORT_YEARS[-1]
    kpis = [
        ("Headcount", f"={b.cells['headcount_total']}", INT),
        ("FTE", f"={b.cells['fte_total']}", DEC),
        (f"Separation rate {y}", f"={b.cells['total_rate']}", PCT),
        (f"Resignation rate {y}", f"={b.cells['resign_rate']}", PCT),
        ("Women in senior roles", f"={b.cells['women_senior']}", PCT),
        ("Gender pay gap", f"={b.cells['pay_gap']}", PCT),
        ("Indigenous representation", f"={b.cells['indigenous_share']}", "0.00%"),
    ]
    for i, (label, formula, fmt) in enumerate(kpis):
        col = 2 + i * 2
        ws.merge_cells(start_row=6, start_column=col, end_row=6, end_column=col + 1)
        ws.merge_cells(start_row=7, start_column=col, end_row=7, end_column=col + 1)
        top, val = ws.cell(row=6, column=col, value=label), ws.cell(row=7, column=col, value=formula)
        top.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        top.fill = PatternFill("solid", fgColor=NAVY)
        val.font = Font(name="Calibri", size=20, bold=True, color=NAVY)
        val.fill, val.number_format = PatternFill("solid", fgColor=PALE), fmt
        ws.cell(row=7, column=col + 1).fill = PatternFill("solid", fgColor=PALE)
        ws.cell(row=6, column=col + 1).fill = PatternFill("solid", fgColor=NAVY)
        top.alignment = val.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[6].height, ws.row_dimensions[7].height = 30, 42
    ws.column_dimensions["A"].width = 2
    for col in range(2, 16):
        ws.column_dimensions[get_column_letter(col)].width = 12.5

    ws["B9"].value, ws["B9"].font = "Context", H2
    ws["B10"].value = (f'="Women are "&TEXT({b.cells["women_all"]},"0%")&" of all staff but "&TEXT({b.cells["women_senior"]},"0%")'
                       f'&" of senior staff. Like-for-like pay gap: "&TEXT({b.cells["pay_gap_lfl"]},"0.0%")&"."')
    ws["B11"].value = (f'="Indigenous representation is "&TEXT({b.cells["indigenous_share"]},"0.0%")&" against a target of "'
                       f'&TEXT({b.cells["indigenous_target"]},"0%")&"."')

    hs = b.wb["Headcount"]
    f, l = b.pos["headcount"]
    bar = BarChart()
    bar.type, bar.grouping, bar.overlap = "bar", "stacked", 100
    bar.title, bar.height, bar.width = "Headcount by area and employment type", 9.5, 17
    bar.add_data(Reference(hs, min_col=2, max_col=4, min_row=4, max_row=l), titles_from_data=True)
    bar.set_categories(Reference(hs, min_col=1, min_row=f, max_row=l))
    for s, colour in zip(bar.series, ["2A78D6", "EB6834", "1BAF7A"]):
        s.graphicalProperties.solidFill = colour
    bar.y_axis.scaling.orientation = "minMax"
    bar.x_axis.scaling.orientation = "maxMin"
    bar.x_axis.delete = bar.y_axis.delete = False
    bar.legend.position = "b"
    bar.y_axis.crosses = "max"  # categories run top-down, so this keeps the value axis at the bottom
    ws.add_chart(bar, "B13")

    ts = b.wb["Turnover"]
    f, l = b.pos["turnover"]
    line = LineChart()
    line.title, line.height, line.width = "Separation and resignation rates (non-casual)", 9.5, 15
    line.add_data(Reference(ts, min_col=7, max_col=8, min_row=4, max_row=l), titles_from_data=True)
    line.set_categories(Reference(ts, min_col=1, min_row=f, max_row=l))
    for s, colour in zip(line.series, ["2A78D6", "EB6834"]):
        s.graphicalProperties.line.solidFill = colour
        s.graphicalProperties.line.width = 25000
        s.marker.symbol = "circle"
        s.marker.graphicalProperties.solidFill = colour
        s.smooth = False
    line.y_axis.number_format = "0%"
    line.y_axis.scaling.min = 0
    line.x_axis.delete = line.y_axis.delete = False
    line.legend.position = "b"
    ws.add_chart(line, "J13")
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True


DEFINITIONS = [
    ("Headcount", "Number of people employed at close of business on the as-at date. A person whose end date equals the as-at date is not counted."),
    ("FTE", "Sum of contracted full-time-equivalent fractions for staff in the headcount."),
    ("Total separation rate", "All separations of non-casual staff in the calendar year / average of opening and closing non-casual headcount."),
    ("Resignation rate", "As above, counting only separations with reason 'Resignation' (employee-initiated). Retirements are reported separately."),
    ("Senior roles", "Academic Level D and E, and professional HEW 10 and above."),
    ("Gender pay gap", "(Mean men's salary - mean women's salary) / mean men's salary, on FTE-annualised base salary, non-casual staff. Excludes loadings and superannuation."),
    ("Like-for-like gap", "Average of the within-classification gaps, weighted by the number of women at each level. Removes the effect of men and women holding different levels."),
    ("Indigenous representation", "Staff who self-identify as Aboriginal and/or Torres Strait Islander / total headcount. Staff who have not disclosed remain in the denominator."),
    ("Small-number suppression", f"Counts of 1 to {c.SMALL_CELL_THRESHOLD - 1} are not published in any breakdown, to protect individuals' privacy. Non-binary and Indigenous counts are therefore shown at university level only."),
    ("Data source", "Synthetic HR extract generated by src/workforce/generate.py and cleaned by src/workforce/clean.py. No real people are represented."),
]


def build_definitions(b):
    ws = b.wb.create_sheet("Definitions")
    b.title(ws, "Definitions and business rules")
    b.header(ws, 3, ["Measure", "Definition"])
    for i, (k, v) in enumerate(DEFINITIONS, start=4):
        ws.cell(row=i, column=1, value=k).font = BOLD
        cell = ws.cell(row=i, column=2, value=v)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.cell(row=i, column=1).alignment = Alignment(vertical="top")
        ws.row_dimensions[i].height = 34
    b.widths(ws, [28, 110])


def build(df=None, scenario_inputs=None, path=None):
    df = load_clean() if df is None else df
    path = path or c.OUT / "Workforce_Report.xlsx"
    b = Book(df)
    b.cells, b.pos = {}, {}
    b.wb.active.title = "Dashboard"
    build_headcount(b)
    build_turnover(b)
    build_equity(b)
    build_scenario(b, scenario_inputs or {"growth_rate": 0.008, "current_hire_share": 0.02})
    build_definitions(b)
    build_data(b)
    build_dashboard(b)
    path.parent.mkdir(parents=True, exist_ok=True)
    b.wb.save(path)
    return path
