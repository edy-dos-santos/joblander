# Methodology

## 1. Data

`data/raw/employees_raw.csv` is a synthetic HR extract: one row per employment record for
everyone employed at the fictional Riverbend University between 1 January 2021 and
31 December 2025. It is produced by `src/workforce/generate.py` with a fixed random seed, so
the whole project is reproducible. 2021 is a burn-in year for the simulation; reporting covers
2022 to 2025, with a snapshot date of 31 December 2025.

### Data dictionary

| Field | Description |
|---|---|
| `employee_id` | Unique identifier |
| `division` | Faculty or professional division (10 values) |
| `staff_group` | Academic / Professional |
| `classification` | Academic Level A to E; professional HEW 3 to HEW 10+ |
| `employment_type` | Ongoing / Fixed-term / Casual |
| `fte` | Contracted full-time-equivalent fraction (0 to 1) |
| `gender` | Woman / Man / Non-binary |
| `date_of_birth` | Used only to derive age in aggregate |
| `indigenous_status` | Self-identified: Aboriginal and/or Torres Strait Islander / Neither / Not disclosed |
| `start_date`, `end_date` | Commencement and last day worked (blank if still employed) |
| `separation_reason` | Resignation / End of contract / Retirement / Redundancy / Other |
| `base_salary_fte` | Annual base salary at 1.0 FTE (AUD), excluding loadings and superannuation |

Derived in cleaning: `active_at_snapshot`, `age`, `age_band`, `tenure_years`, `tenure_band`,
`senior`, `separation_year`.

### Patterns built into the simulation

So that the analysis has something to find, the generator includes: higher separation hazard
for fixed-term and casual staff, for ongoing staff in their first two years, for staff aged
62+, and for Digital & Technology; a turnover spike in 2022; fewer women at senior
classifications and in Engineering and Digital & Technology; a small (about 1.2%) salary
loading for men at the same classification; an older academic profile in Engineering; and
Indigenous self-identification that is low in the opening workforce and slightly higher among
new hires. The analysis recovers these without being told where they are, which is a useful
check on the method, but it also means the findings say nothing about any real university.

## 2. Data quality

`src/workforce/clean.py` applies eleven rules. Each either fixes records or flags them, and
writes a row to `outputs/data_quality_log.csv`.

| Rule | Treatment |
|---|---|
| Exact duplicate rows | Remove, keep first |
| Employee ID on more than one distinct record | Flag |
| Division with stray whitespace or casing | Standardise to reference list |
| Division not in reference list | Flag |
| Non-standard gender label (F, male, X ...) | Map to standard categories |
| End date before start date | Swap (transposed at entry) |
| Salary more than 3x the classification median | Divide by 10 (extra digit keyed) |
| Missing FTE | Impute median for the employment type |
| Separated with no reason | Set to "Other" so it is never counted as voluntary |
| Under 16 at commencement | Flag |
| FTE outside 0 to 1 | Flag |

In a real setting the automatic fixes would be proposals for the data owner to confirm, and
the corrections would be made in the source system rather than only in the extract.

## 3. Metric definitions

| Metric | Definition |
|---|---|
| Headcount | People employed at close of business on the date: `start_date <= date` and (`end_date` blank or `end_date > date`). Someone whose last day is the snapshot date is not counted. |
| FTE | Sum of `fte` over the headcount. |
| Total separation rate | Separations of non-casual staff in the calendar year / average of opening and closing non-casual headcount. |
| Resignation rate | As above, counting only reason = Resignation. Retirement is employee-initiated too, but is reported separately because the response to it (succession planning) is different. |
| Senior roles | Level D, Level E, HEW 10+. |
| Gender pay gap | (mean men's salary - mean women's salary) / mean men's salary, on `base_salary_fte`, non-casual staff. Non-binary staff are excluded from this two-group comparison because the group is too small to report an average for. |
| Like-for-like gap | Mean of the within-classification gaps, weighted by the number of women at each level. |
| Structural gap | Overall gap minus like-for-like gap: the part due to women and men holding different classifications. |
| Indigenous representation | Staff identifying as Aboriginal and/or Torres Strait Islander / total headcount. "Not disclosed" stays in the denominator. |
| Retirement exposure | Ongoing staff who will be 65 or older five years after the snapshot / ongoing headcount. |

Casual staff are excluded from turnover because casual engagements end by design; including
them would roughly double the rate without saying anything about retention.

## 4. Statistical methods

| Question | Method | Why |
|---|---|---|
| Is resignation related to employment type? | Chi-square test of independence, with Cramer's V | Two categorical variables; V shows whether a significant result is also a large one. |
| Is Digital & Technology really different? | Two-proportion z-test, 95% CI for the difference | A confidence interval tells a manager how big the gap plausibly is, not just that it exists. |
| How certain is a small proportion? | Wilson score interval | Behaves better than the normal approximation when the proportion is near zero. |
| Which factors matter once the others are held constant? | Logistic regression on person-years, standard errors clustered by employee | Tenure, contract type, age and area overlap; the model separates them. Clustering is needed because one person contributes several years. |
| When would the representation target be met? | Deterministic stock-and-flow scenario | Transparent arithmetic a stakeholder can change in Excel. |

The unit of analysis for resignations is the person-year: each non-casual staff member
contributes one row for each year they began employed (11,825 rows), with characteristics
measured at 1 January.

## 5. Privacy and ethical use

- Counts of 1 to 4 are suppressed in any published breakdown
  (`metrics.suppress_small_cells`). Zero is shown. Where a total is published alongside
  suppressed cells, a real release would also need secondary suppression so that the hidden
  value cannot be recovered by subtraction.
- Indigenous status and non-binary gender are reported at university level only.
- Age is analysed in aggregate for workforce planning. Reaching 65 is not treated as a
  prediction that any individual will retire, and nothing here is intended to inform
  decisions about individuals.
- The resignation model describes groups. It is not used to score individual employees.
- Indigenous data is about Indigenous people, so how it is collected, interpreted and acted on
  should be guided by Indigenous staff and leadership (Indigenous data sovereignty).

## 6. Limitations

- Synthetic data: the findings demonstrate method, not fact.
- The regression shows association, not causation, and omits things a real analysis would
  want (pay relativity to market, manager, workload, engagement scores).
- Salary is a single current value per person, so pay progression cannot be analysed.
- The scenario model assumes separation rates are equal across groups and constant over time.
- Turnover uses a two-point average headcount; a monthly average would be more accurate for
  areas with seasonal casual-to-fixed-term movement.

## 7. Quality assurance

`pytest` runs 13 tests: metric definitions against hand-calculated examples, integrity of the
cleaned dataset, idempotence of cleaning, and reconciliation of the recalculated Excel
workbook against the Python results (headcount, turnover, equity and scenario sheets).
