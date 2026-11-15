# Methodology

## 1. Source and licence

Workplace Gender Equality Agency (WGEA), *WGEA Dataset*, public data files for reporting years
2022-23, 2023-24 and 2024-25, from <https://data.gov.au/data/dataset/wgea-dataset>.
Licensed under Creative Commons Attribution 3.0 Australia.

Two files are used from each year:

| File | Content |
|---|---|
| Workforce composition | Employee counts by employer, manager category, occupation, employment status (full-time / part-time / casual), employment type (permanent / contract / casual) and gender. |
| Workforce management statistics | Counts of promotions, internal and external appointments, resignations and parental leave, by the same dimensions. |

`src/benchmark/fetch.py` downloads the national files, keeps ANZSIC class "Higher Education",
harmonises the schema and writes two small CSVs to `data/extract/`. Those extracts are
committed so the analysis runs without the 170 MB download.

This is an independent analysis of public data. It is not affiliated with or endorsed by
WGEA or any university named.

## 2. Cleaning and inclusion decisions

| Issue | Decision | Why |
|---|---|---|
| 2022-23 movements file has subtotal rows ("Total appointments including / excluding promotions") | Removed (1,880 rows) | They repeat their components; leaving them in double-counts 233,109 appointments. |
| Column names differ in 2022-23 | Renamed to the later schema | One schema downstream. |
| `Manager` / `Managers`, `Non-manager` / `Non-managers` | Standardised to singular | Same category, inconsistent label. |
| `Promtions from non-manager to manager` | Spelling corrected; kept separate; excluded from promotion counts | Exists only in 2024-25. Including it would break comparability, and the files do not say whether it overlaps with "Promotions". |
| "Heads of Business" (39 people across all higher-education employers and years) | Folded into the CEO tier | Used by very few employers; otherwise these managers fall outside every tier table. |
| Employer names vary slightly between years | One name per ABN (most recent), tidied | ABN is the stable key. |
| Higher Education class includes non-universities | Keep employers with "University" in the name, excluding names containing College, Enterprises, Online, Ventures, Training or Admissions, with at least 1,000 employees | 38 universities; 37 reported in 2024-25. |
| University of Technology Sydney has no 2024-25 record; University of South Australia has no 2022-23 record | Kept for the years they report; excluded from trends | Trends use the balanced panel of 36. |

## 3. Definitions

| Measure | Definition |
|---|---|
| Headcount | Employees in the workplace profile, casuals included. |
| Managers | WGEA manager categories: CEO, key management personnel, other executives and general managers, senior managers, other managers. |
| Senior management | All manager tiers above "other managers". |
| Leadership gap | Women's share of managers minus women's share of all employees, in percentage points. |
| Promotion parity ratio | Women's share of promotions / women's share of non-casual staff. Casuals are excluded from both. |
| Sector (pooled) | Sum of numerators / sum of denominators across universities, so each employee counts once. The median university is reported alongside because the two answer different questions. |
| "Other universities" | The pooled sector excluding the focus university, used wherever the focus is tested against the sector. |

## 4. Statistical methods

| Question | Method | Note |
|---|---|---|
| Is women's share of senior management at QUT different from other universities? | Two-proportion z-test, 95% CI for the difference | Reports the size of the gap, not only whether one exists. |
| Is that more than chance, given 37 universities are being compared? | Funnel plot: binomial control limits (95% and 99.8%) around the pooled rate, by number of senior roles | With 37 universities, about two fall outside 95% limits by chance. The 99.8% limit is the conventional threshold for "investigate". |
| Is gender independent of level within QUT? | Chi-square test, with Cramer's V | V shows the effect is small even though p is tiny, because n is large. |
| Are promotions proportionate? | Exact binomial test of women's share of promotions against their share of non-casual staff, pooled over three years | Annual counts are too small to test alone. |
| How uncertain is a single percentage? | Wilson score interval | Reliable for small groups and proportions near 0 or 1. |

### Sensitivity of the headline result

The senior-management comparison was repeated with narrower definitions of "senior":

| Definition | QUT | Other universities | QUT roles |
|---|---|---|---|
| All tiers above "other managers" (headline) | 45.1% | 49.8% | 665 |
| Senior managers only | 45.2% | 49.4% | 598 |
| Executives, key management personnel and CEO only | 44.8% | 50.6% | 67 |

The direction and approximate size hold under each definition.

## 5. Limitations

1. **Comparability of manager categories.** Each employer maps its own roles to WGEA's
   categories. Universities report between 3% and 23% of employees as managers (median 9%);
   QUT reports 21% and has the largest number of senior management roles of any university.
   Its "senior management" is therefore likely to include roles other universities report as
   professionals. Cross-university differences partly reflect these choices. Findings about
   the pattern *within* QUT do not depend on this.
2. **Gender is binary in the public files.** Employers can report non-binary employees to
   WGEA, but the published files contain women and men only.
3. **No academic level, age, remuneration or Aboriginal and Torres Strait Islander status.**
   The data cannot answer whether the senior-tier pattern sits in academic or professional
   roles, or how gender intersects with other characteristics.
4. **Snapshot effects.** Headcount includes casuals and depends on each employer's snapshot
   date, so casual shares are indicative.
5. **Association only.** Nothing here identifies why a pattern exists.
6. **Three years.** Enough to show direction, not to establish a trend.

## 6. Quality assurance

`pytest` runs 16 tests:

- the loading rules (subtotals removed, universities only, one name per ABN, harmonised
  categories, balanced panel, every manager in a reported tier);
- metric definitions against a small hand-calculated dataset;
- internal consistency of the real results;
- reconciliation of the Excel workbook: it is recalculated with LibreOffice and its league
  table, scorecard, tier table and parity cells are compared with the Python results for
  every university.
