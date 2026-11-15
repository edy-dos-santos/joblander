"""Build the Excel benchmark workbook.

The 'Benchmark' sheet has a university drop-down and a year drop-down. Every
figure on it, and the whole 'League' table behind it, is a live formula
(SUMIFS / INDEX-MATCH / RANK / MEDIAN / COUNTIFS) over two tidy data sheets, so
choosing a different university re-benchmarks the entire workbook.
tests/test_excel_reconciliation.py recalculates it and checks it against Python.
"""
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L
from openpyxl.worksheet.datavalidation import DataValidation

from . import config as c

NAVY, PALE, INPUT = "0D366B", "EEF4FC", "FFF6D6"
H1 = Font(name="Calibri", size=16, bold=True, color=NAVY)
H2 = Font(name="Calibri", size=12, bold=True, color=NAVY)
NOTE = Font(name="Calibri", size=9, italic=True, color="52514E")
HEAD = Font(name="Calibri", bold=True, color="FFFFFF")
BOLD = Font(name="Calibri", bold=True)
PCT, INT, PTS, RATIO = "0.0%", "#,##0", "+0.0;-0.0;0.0", "0.00"
UNI, YEAR = "Benchmark!$C$4", "Benchmark!$C$5"

COMP_COLS = ["reporting_year", "university", "manager_category", "occupation", "employment_status",
             "employment_type", "gender", "n_employees", "senior"]
MOVE_COLS = ["reporting_year", "university", "movement_type", "manager_category", "employment_type", "gender",
             "n_employees"]


def header(ws, row, labels, col=1):
    for i, label in enumerate(labels):
        cell = ws.cell(row=row, column=col + i, value=label)
        cell.font, cell.fill = HEAD, PatternFill("solid", fgColor=NAVY)
        cell.alignment = Alignment(horizontal="center" if i else "left", vertical="center", wrap_text=True)
    ws.row_dimensions[row].height = 45


def widths(ws, ws_widths):
    for i, w in enumerate(ws_widths):
        ws.column_dimensions[L(i + 1)].width = w


class Ref:
    """Builds SUMIFS formulas over a data sheet."""

    def __init__(self, sheet, cols, n):
        self.sheet, self.n = sheet, n
        self.col = {name: L(i + 1) for i, name in enumerate(cols)}

    def rng(self, name):
        return f"{self.sheet}!${self.col[name]}$2:${self.col[name]}${self.n + 1}"

    def sumifs(self, *pairs):
        crit = "".join(f",{self.rng(k)},{v}" for k, v in pairs)
        return f"SUMIFS({self.rng('n_employees')}{crit})"


def data_sheet(wb, name, df, cols):
    ws = wb.create_sheet(name)
    header(ws, 1, cols)
    ws.row_dimensions[1].height = 20
    for rec in df[cols].itertuples(index=False):
        ws.append(list(rec))
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{L(len(cols))}{len(df) + 1}"
    widths(ws, [14, 38, 16, 38, 16, 16, 9, 12, 8])
    return Ref(name, cols, len(df))


# League columns: (header, formula builder taking the row number, number format)
def league_columns(C, M):
    y = ("reporting_year", YEAR)

    def comp(*extra):
        return lambda r: "=" + C.sumifs(y, ("university", f"$A{r}"), *extra)

    def move(mtype, *extra):
        return lambda r: "=" + M.sumifs(y, ("university", f"$A{r}"), ("movement_type", f'"{mtype}"'),
                                        ("employment_type", '"<>Casual"'), *extra)
    W, MGR = ("gender", '"Women"'), ("manager_category", '"Manager"')
    return [
        ("Headcount", comp(), INT),                                            # B
        ("Women", comp(W), INT),                                               # C
        ("Managers", comp(MGR), INT),                                          # D
        ("Women managers", comp(MGR, W), INT),                                 # E
        ("Senior management", comp(("senior", 1)), INT),                       # F
        ("Women in senior management", comp(("senior", 1), W), INT),           # G
        ("Casual", comp(("employment_type", '"Casual"')), INT),                # H
        ("Fixed-term contract", comp(("employment_type", '"Contract"')), INT),  # I
        ("Non-casual women", comp(("employment_type", '"<>Casual"'), W), INT),  # J
        ("Non-casual staff", comp(("employment_type", '"<>Casual"')), INT),    # K
        ("Promotions", move("Promotions"), INT),                               # L
        ("Promotions to women", move("Promotions", W), INT),                   # M
        ("Women % of employees", lambda r: f'=IF(B{r}=0,"",C{r}/B{r})', PCT),            # N
        ("Women % of managers", lambda r: f'=IF(D{r}=0,"",E{r}/D{r})', PCT),             # O
        ("Women % of senior management", lambda r: f'=IF(F{r}=0,"",G{r}/F{r})', PCT),    # P
        ("Leadership gap (pts)", lambda r: f'=IF(B{r}=0,"",(O{r}-N{r})*100)', PTS),      # Q
        ("Managers % of employees", lambda r: f'=IF(B{r}=0,"",D{r}/B{r})', PCT),         # R
        ("Casual % of headcount", lambda r: f'=IF(B{r}=0,"",H{r}/B{r})', PCT),           # S
        ("Contract % of headcount", lambda r: f'=IF(B{r}=0,"",I{r}/B{r})', PCT),         # T
        ("Promotion parity ratio", lambda r: f'=IF(OR(L{r}=0,K{r}=0),"",(M{r}/L{r})/(J{r}/K{r}))', RATIO),  # U
        ("Rank: women % of senior management", lambda r: f'=IF(P{r}="","",RANK(P{r},P$FIRST:P$LAST))', INT),  # V
        ("z-score vs sector (senior)", lambda r: (
            f'=IF(F{r}=0,"",(P{r}-G$TOT/F$TOT)/SQRT((G$TOT/F$TOT)*(1-G$TOT/F$TOT)/F{r}))'), "0.00"),      # W
        ("Signal", lambda r: f'=IF(W{r}="","Not reported",IF(ABS(W{r})>3.09,"Differs (99.8%)",'
                             f'IF(ABS(W{r})>1.96,"Outside 95% only","Consistent with sector")))', None),  # X
    ]


def build_league(wb, C, M, universities):
    ws = wb.create_sheet("League")
    ws["A1"].value, ws["A1"].font = "League table - all universities, selected year", H1
    ws["A2"].value = "Year follows the drop-down on the Benchmark sheet. Counts on the left, rates built from them on the right."
    ws["A2"].font = NOTE
    cols = league_columns(C, M)
    header(ws, 4, ["University"] + [h for h, _, _ in cols])
    first, last = 5, 4 + len(universities)
    tot = last + 1
    for i, u in enumerate(universities):
        r = first + i
        ws.cell(row=r, column=1, value=u)
        for j, (_, f, fmt) in enumerate(cols):
            formula = f(r).replace("$FIRST", f"${first}").replace("$LAST", f"${last}").replace("$TOT", f"${tot}")
            cell = ws.cell(row=r, column=2 + j, value=formula)
            if fmt:
                cell.number_format = fmt
    ws.cell(row=tot, column=1, value="All universities (pooled)")
    for j in range(12):                       # counts B..M
        col = L(2 + j)
        ws.cell(row=tot, column=2 + j, value=f"=SUM({col}{first}:{col}{last})").number_format = INT
    for j, (_, f, fmt) in enumerate(cols[12:20]):   # rates N..U from the pooled counts
        ws.cell(row=tot, column=14 + j, value=f(tot)).number_format = fmt
    med = tot + 1
    ws.cell(row=med, column=1, value="Median university")
    for j, (_, _, fmt) in enumerate(cols[12:20]):
        col = L(14 + j)
        ws.cell(row=med, column=14 + j, value=f"=MEDIAN({col}{first}:{col}{last})").number_format = fmt
    for r in (tot, med):
        for col in range(1, 25):
            ws.cell(row=r, column=col).font = BOLD
            if r == tot:
                ws.cell(row=r, column=col).border = Border(top=Side(style="thin", color="C3C2B7"))
    ws.conditional_formatting.add(f"A{first}:A{last}", CellIsRule(operator="equal", formula=[UNI],
                                                                  fill=PatternFill("solid", bgColor=INPUT, fgColor=INPUT)))
    widths(ws, [38] + [12] * 23)
    ws.column_dimensions["X"].width = 24
    ws.freeze_panes = "B5"
    return first, last, tot, med


def build_benchmark(wb, C, universities, pos, focus):
    ws = wb["Benchmark"]
    first, last, tot, med = pos
    ws.sheet_view.showGridLines = False
    ws["B1"].value, ws["B1"].font = "University gender equity benchmark", H1
    ws["B2"].value = ("Source: WGEA public data files (data.gov.au, CC BY 3.0 AU). Independent analysis. "
                      "Choose a university and year in the yellow cells.")
    ws["B2"].font = NOTE
    for r, label, value in [(4, "University", focus), (5, "Reporting year", c.LATEST)]:
        ws.cell(row=r, column=2, value=label).font = BOLD
        cell = ws.cell(row=r, column=3, value=value)
        cell.fill, cell.font = PatternFill("solid", fgColor=INPUT), BOLD
    dv_u = DataValidation(type="list", formula1=f"=League!$A${first}:$A${last}", allow_blank=False)
    dv_y = DataValidation(type="list", formula1='"' + ",".join(c.YEARS) + '"', allow_blank=False)
    ws.add_data_validation(dv_u)
    ws.add_data_validation(dv_y)
    dv_u.add("C4")
    dv_y.add("C5")
    ws["D4"].value = f'=IF(INDEX(League!$B${first}:$B${last},MATCH($C$4,League!$A${first}:$A${last},0))=0,"Did not report in this year","")'
    ws["D4"].font = Font(name="Calibri", bold=True, color="D03B3B")

    def pick(col):  # the selected university's value in a League column
        return f"INDEX(League!${col}${first}:${col}${last},MATCH($C$4,League!$A${first}:$A${last},0))"

    ws["B7"].value, ws["B7"].font = "Scorecard", H2
    header(ws, 8, ["Measure", "Selected university", "All universities (pooled)", "Median university",
                   "Difference from pooled", "Rank (1 = highest)", "Universities reporting"], col=2)
    ws.row_dimensions[8].height = 32
    rows = [("Headcount", "B", INT, False), ("Women % of employees", "N", PCT, True),
            ("Women % of managers", "O", PCT, True), ("Women % of senior management", "P", PCT, True),
            ("Leadership gap (pts)", "Q", PTS, True), ("Managers % of employees", "R", PCT, True),
            ("Casual % of headcount", "S", PCT, True), ("Contract % of headcount", "T", PCT, True),
            ("Promotion parity ratio", "U", RATIO, True)]
    for i, (label, col, fmt, has_bench) in enumerate(rows):
        r = 9 + i
        ws.cell(row=r, column=2, value=label)
        ws.cell(row=r, column=3, value=f"={pick(col)}").number_format = fmt
        if has_bench:
            ws.cell(row=r, column=4, value=f"=League!{col}{tot}").number_format = fmt
            ws.cell(row=r, column=5, value=f"=League!{col}{med}").number_format = fmt
            diff = ws.cell(row=r, column=6, value=(f'=IF(C{r}="","",C{r}-D{r})' if fmt != PCT
                                                   else f'=IF(C{r}="","",(C{r}-D{r})*100)'))
            diff.number_format = PTS if fmt in (PCT, PTS) else "+0.00;-0.00;0.00"
            rng = f"League!${col}${first}:${col}${last}"
            ws.cell(row=r, column=7, value=f'=IF(C{r}="","",RANK(C{r},{rng}))')
            ws.cell(row=r, column=8, value=f"=COUNT({rng})")
    ws.cell(row=18, column=2, value="Differences for percentages are in percentage points. "
                                    "Rank 1 is the highest value, which is not always the best.").font = NOTE

    # Signal for the headline measure
    ws["B20"].value, ws["B20"].font = "Is the senior-management difference more than chance?", H2
    ws["B21"].value = "z-score against the pooled sector rate"
    ws["C21"].value, ws["C21"].number_format = f"={pick('W')}", "0.00"
    ws["B22"].value = "Reading"
    ws["C22"].value = f"={pick('X')}"
    ws["B23"].value = "Additional women in senior management needed to match the pooled sector rate"
    ws["C23"].value = f"=MAX(0,ROUNDUP(League!P{tot}*{pick('F')},0)-{pick('G')})"
    ws["B24"].value = "Additional women in senior management needed to reach 50%"
    ws["C24"].value = f"=MAX(0,ROUNDUP(0.5*{pick('F')},0)-{pick('G')})"

    # Tier table
    ws["B26"].value, ws["B26"].font = "Women's share at each level", H2
    header(ws, 27, ["Level", "Selected: employees", "Selected: women %", "All other universities: women %",
                    "Difference (pts)"], col=2)
    ws.row_dimensions[27].height = 32
    y, u, W = ("reporting_year", "$C$5"), ("university", "$C$4"), ("gender", '"Women"')
    levels = [(c.TIER_LABELS[t], [("occupation", f'"{t}"'), ("manager_category", '"Manager"')]) for t in c.MANAGER_TIERS]
    levels.append(("Non-managers", [("manager_category", '"Non-manager"')]))
    for i, (label, crit) in enumerate(levels):
        r = 28 + i
        ws.cell(row=r, column=2, value=label)
        ws.cell(row=r, column=3, value="=" + C.sumifs(y, u, *crit)).number_format = INT
        ws.cell(row=r, column=4, value=f'=IF(C{r}=0,"",{C.sumifs(y, u, W, *crit)}/C{r})').number_format = PCT
        ws.cell(row=r, column=5, value=(f"=({C.sumifs(y, W, *crit)}-{C.sumifs(y, u, W, *crit)})"
                                        f"/({C.sumifs(y, *crit)}-C{r})")).number_format = PCT
        ws.cell(row=r, column=6, value=f'=IF(D{r}="","",(D{r}-E{r})*100)').number_format = PTS
    ws.cell(row=34, column=2, value="Tiers with few employees (CEO, key management personnel) swing widely; "
                                    "treat their percentages as indicative.").font = NOTE

    # Trend table
    ws["B36"].value, ws["B36"].font = "Three-year trend: women % of senior management", H2
    header(ws, 37, ["Reporting year", "Selected university", "All universities reporting that year"], col=2)
    ws.row_dimensions[37].height = 32
    sen = ("senior", 1)
    for i, yr in enumerate(c.YEARS):
        r = 38 + i
        ws.cell(row=r, column=2, value=yr)
        yc = ("reporting_year", f"$B{r}")
        ws.cell(row=r, column=3, value=(f'=IF({C.sumifs(yc, u, sen)}=0,NA(),'
                                        f'{C.sumifs(yc, u, sen, W)}/{C.sumifs(yc, u, sen)})')).number_format = PCT
        ws.cell(row=r, column=4, value=f"={C.sumifs(yc, sen, W)}/{C.sumifs(yc, sen)}").number_format = PCT

    bar = BarChart()
    bar.type, bar.title, bar.height, bar.width = "bar", "Women's share by level", 9, 16
    bar.add_data(Reference(ws, min_col=4, max_col=5, min_row=27, max_row=33), titles_from_data=True)
    bar.set_categories(Reference(ws, min_col=2, min_row=28, max_row=33))
    for s, colour in zip(bar.series, ["2A78D6", "EB6834"]):
        s.graphicalProperties.solidFill = colour
    bar.x_axis.scaling.orientation = "maxMin"
    bar.y_axis.crosses = "max"
    bar.y_axis.number_format = "0%"
    bar.y_axis.scaling.min, bar.y_axis.scaling.max = 0, 1
    bar.x_axis.delete = bar.y_axis.delete = False
    bar.legend.position = "b"
    ws.add_chart(bar, "J7")

    line = LineChart()
    line.title, line.height, line.width = "Women % of senior management", 8, 16
    line.add_data(Reference(ws, min_col=3, max_col=4, min_row=37, max_row=40), titles_from_data=True)
    line.set_categories(Reference(ws, min_col=2, min_row=38, max_row=40))
    for s, colour in zip(line.series, ["2A78D6", "EB6834"]):
        s.graphicalProperties.line.solidFill = colour
        s.graphicalProperties.line.width = 25000
        s.marker.symbol = "circle"
        s.marker.graphicalProperties.solidFill = colour
        s.smooth = False
    line.y_axis.number_format = "0%"
    line.x_axis.delete = line.y_axis.delete = False
    line.legend.position = "b"
    ws.add_chart(line, "J26")
    widths(ws, [2, 70, 38, 20, 18, 16, 14, 14, 3])
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True


NOTES = [
    ("Source", "Workplace Gender Equality Agency (WGEA) public data files for 2022-23, 2023-24 and 2024-25, published on data.gov.au under Creative Commons Attribution 3.0 Australia. Only ANZSIC class 'Higher Education' is kept."),
    ("Independence", "This is an independent analysis of public data. It is not affiliated with, or endorsed by, WGEA or any university named."),
    ("Who is a university", "A higher-education employer whose name contains 'University', is not a subsidiary or pathway entity, and reports at least 1,000 employees."),
    ("Headcount", "Employees reported in the workplace profile, including casuals. A person is counted once regardless of hours."),
    ("Managers", "WGEA manager categories: CEO, key management personnel, other executives and general managers, senior managers, other managers. Each employer decides how its own roles map to these categories."),
    ("Senior management", "All manager tiers above 'Other managers'."),
    ("Leadership gap", "Women's share of managers minus women's share of all employees, in percentage points. Negative means women are under-represented in management relative to the workforce."),
    ("Promotion parity ratio", "Women's share of promotions divided by women's share of non-casual staff. 1.00 means promotions are proportionate. Casual staff are excluded from both."),
    ("z-score / signal", "(University rate - pooled sector rate) / binomial standard error for that university's number of senior roles. Beyond +/-3.09 the university differs from the sector by more than chance would explain (99.8% limits); between 1.96 and 3.09 is suggestive only, because with about 37 universities one or two fall there by chance."),
    ("Comparability warning", "Universities report between about 3% and 23% of employees as managers. 'Senior management' is therefore not the same set of roles everywhere, and cross-university differences partly reflect classification choices."),
    ("Gender", "The public files report women and men only. Employers can report non-binary employees to WGEA, but those counts are not included in the public files."),
    ("Data handling", "Subtotal rows in the 2022-23 movements file are removed (they double-count appointments). 'Promotions from non-manager to manager' exists only in 2024-25 and is excluded from promotion counts so years are comparable."),
]


def build_notes(wb):
    ws = wb.create_sheet("Notes")
    ws.sheet_view.showGridLines = False
    ws["A1"].value, ws["A1"].font = "Definitions, source and caveats", H1
    header(ws, 3, ["Item", "Detail"])
    ws.row_dimensions[3].height = 20
    for i, (k, v) in enumerate(NOTES, start=4):
        ws.cell(row=i, column=1, value=k).font = BOLD
        ws.cell(row=i, column=1).alignment = Alignment(vertical="top")
        ws.cell(row=i, column=2, value=v).alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[i].height = 48
    widths(ws, [26, 120])


def build(r, path=None):
    path = path or c.OUT / "University_Benchmark.xlsx"
    comp = r["comp"].copy()
    comp["senior"] = comp["occupation"].isin(c.SENIOR_TIERS).astype(int)
    move = r["move"].groupby(MOVE_COLS[:-1], as_index=False)["n_employees"].sum()
    universities = sorted(comp["university"].unique())
    wb = Workbook()
    wb.active.title = "Benchmark"
    wb.create_sheet("League")
    wb.remove(wb["League"])
    C = Ref("Composition", COMP_COLS, len(comp))
    M = Ref("Movements", MOVE_COLS, len(move))
    pos = build_league(wb, C, M, universities)
    build_benchmark(wb, C, universities, pos, r["focus"])
    build_notes(wb)
    data_sheet(wb, "Composition", comp, COMP_COLS)
    data_sheet(wb, "Movements", move, MOVE_COLS)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
