# Flaky Test Detection — Dashboards Requirements

**Feature:** Flaky Test Detection (Shadow Mode)
**Summary:** Two Grafana dashboards — Flaky tests and Shadow mode — on top of the detection data, plus links into the existing Test inventory and Test drill-down dashboards.
**Scope:** Dashboards (Grafana provisioning JSON, panel queries against `reporting.*` views)
**Stack:** Grafana OSS, PostgreSQL datasource `fq-postgres` (role `grafana_ro`), dashboards as code in `grafana/provisioning/dashboards/`

**References:**
- Feature design: `docs/feature-requirements/2026-11-20-flaky-detection-shadow-mode-design.md` (REQ-7.x, REQ-0.6)
- Backend: `docs/requirements/detection-backend-requirements.md` §12 (view column contract)
- Architecture: §12 (dashboards), §15 (demo data banner)

---

## Requirement ID Reference

| ID | Description |
|----|-------------|
| REQ-7.1a | Flaky tests by level |
| REQ-7.1b | Flaky tests by reason (suggested vs confirmed) with product area |
| REQ-7.1c | Top 10 flaky tests by cost score |
| REQ-7.1d | Flaky tests by environment |
| REQ-7.1e | Flakiness rate trend |
| REQ-7.1f | Environmental runs per repo per week |
| REQ-7.2a | Shadow decisions per team and outcome |
| REQ-7.2b | Would-be quarantined share per team vs 5% cap |
| REQ-7.2c | Protected-flaky tests |
| REQ-7.2d | Shadow decision list with evidence links |
| REQ-7.3 | Shared variables |
| REQ-7.4 | Click-through to Test drill-down |
| REQ-7.5 | DEMO DATA banner |
| REQ-7.6 | No-data explanations |
| REQ-7.7 | Unclassified tests panel on Test inventory |
| REQ-0.6 | English labels, en-US numbers and dates, one-decimal rates |

---

## 1. Dashboards and Navigation

### 1.1 Folder and links

- **Folder:** "Flaky Test Quarantine" (provisioned).
- **Dashboards in this feature:** `flaky-tests` ("Flaky tests") and `shadow-mode` ("Shadow mode").
- **Existing:** `test-inventory` (M1) and `test-drilldown` (stub created here if M4 hasn't built it: one table of executions for `$test_id`).
- Every dashboard has a links bar: Test inventory · Flaky tests · Shadow mode, carrying the current variables (`includeVars`, `keepTime`).

### 1.2 Page structure (Flaky tests)

```
Row 0: DEMO DATA banner (only when $data != real)
Row 1: stat panels — Flaky tests · Flaky occurrences · Avg flakiness rate · Environmental runs (range)
Row 2: Flaky tests by level (bar) | Flaky tests by reason (stacked bar, suggested vs confirmed)
Row 3: Flakiness rate trend (time series) | Flaky tests by environment (bar)
Row 4: Top 10 by cost score (table, full width)
Row 5: Environmental runs per repo per week (time series)
```

### 1.3 Page structure (Shadow mode)

```
Row 0: DEMO DATA banner
Row 1: stat panels — Would auto-quarantine · Would need lead approval · Protected flaky · Teams over cap
Row 2: Decisions per team by outcome (stacked bar) | Would-be quarantined share per team vs cap (bar gauge, threshold line at 5%)
Row 3: Protected-flaky tests (table)
Row 4: Shadow decision list (table, full width)
```

---

## 2. Variables (REQ-7.3)

| Variable | Type | Query / values | Default |
|----------|------|----------------|---------|
| `data` | custom | real, demo, all | real |
| `repo` | query, multi, include All | `SELECT DISTINCT repo FROM reporting.v_flaky_tests WHERE $__data_filter` | All |
| `team` | query, multi | distinct team, filtered by `$repo` | All |
| `product_area` | query, multi | distinct product_area (NULL shown as "Unassigned") | All |
| `level` | custom, multi | unit, integration, api, e2e, unclassified | All |
| `framework` | custom, multi | pytest, playwright, jest | All |
| `reason` | custom, multi | the 9 reasons | All |
| time range | Grafana time picker | — | Last 14 days |

- The `data` filter maps to `is_demo` (`real` → false, `demo` → true, `all` → both) and is a dashboard-level SQL macro so every panel applies it.
- Changing any variable updates every panel on the dashboard.

**Acceptance:**
- [ ] Every panel query uses every applicable variable (checked by the dashboard lint test)
- [ ] Variables chain: choosing a repo narrows the team list

---

## 3. Flaky Tests Dashboard (REQ-7.1)

### 3.1 Stat row
- **Flaky tests:** `COUNT(*)` from `v_flaky_tests` where `flaky_occurrences > 0`
- **Flaky occurrences:** `SUM(flaky_occurrences)`
- **Avg flakiness rate:** weighted (`SUM(occurrences) / SUM(execution_groups)`), shown as percent with one decimal
- **Environmental runs:** `SUM(environmental_runs)` from `v_environmental_runs` in range

### 3.2 Flaky tests by level (REQ-7.1a)
- Bar chart; x = level (unit, integration, api, e2e, unclassified in that order); y = flaky tests
- Tooltip: level, flaky tests, flaky occurrences

### 3.3 Flaky tests by reason (REQ-7.1b)
- Stacked horizontal bar; one bar per reason; segments "Suggested only" and "Confirmed"
- Table mode toggle shows product area per reason (`reason × product_area` counts)
- Sorted by total, highest first

### 3.4 Flakiness rate trend (REQ-7.1e)
- Time series from `v_flakiness_daily`; one line for the weighted rate; optional series per team when one repo is selected
- Y axis percent; a dashed threshold line at 5%

### 3.5 Flaky tests by environment (REQ-7.1d)
- Bar chart; x = environment string; y = flaky tests; sorted desc; top 15

### 3.6 Top 10 by cost score (REQ-7.1c)
- Table columns: Test (link), Team, Product area, Level, Reason (suggested), Rate, Occurrences, Cost (minutes), Last flaky
- Sorted by cost desc; cost shown as minutes with no decimals
- Test cell links to `test-drilldown?var-test_id=${__data.fields.test_id}` (REQ-7.4)

### 3.7 Environmental runs per repo (REQ-7.1f)
- Time series by ISO week; series per repo; ratio as percent; threshold line at 10%

**Acceptance:**
- [ ] All panels read only `reporting.v_flaky_tests`, `v_flakiness_daily`, `v_environmental_runs`
- [ ] Panel titles and legends exactly as named above

---

## 4. Shadow Mode Dashboard (REQ-7.2)

### 4.1 Stat row
- Counts of open shadow decisions by outcome; **Teams over cap** = teams whose `team_would_quarantine / team_active_tests ≥ 0.05`

### 4.2 Decisions per team by outcome (REQ-7.2a)
- Stacked bar; x = team (including `unowned`); segments: auto_quarantine, needs_lead_approval, protected_alert

### 4.3 Would-be quarantined share vs cap (REQ-7.2b)
- Bar gauge per team: `team_would_quarantine / team_active_tests` as percent; thresholds: < 4% neutral, 4–5% warning, ≥ 5% critical

### 4.4 Protected-flaky tests (REQ-7.2c)
- Table: Test (link), Team, Rate, Occurrences, Reason, Decided at

### 4.5 Shadow decision list (REQ-7.2d)
- Table: Decided at (Europe/Kyiv), Test (link), Team, Area, Level, Outcome, Rate, Occurrences, Reason, Evidence run (link to CI)
- Newest first; 50 rows per page

**Acceptance:**
- [ ] All panels read only `reporting.v_shadow_decisions`
- [ ] Outcome labels shown as "Auto-quarantine", "Needs lead approval", "Protected alert"

---

## 4a. Test Inventory Addition (REQ-7.7)

- New table panel **Unclassified tests** on the existing `test-inventory` dashboard: Test (link), Repo, Team, File path, Last seen.
- Source: `reporting.v_test_inventory` where `level = 'unclassified'`; applies the dashboard's repo, team and `$data` variables.
- No-data text: "Every test has a level".

---

## 5. States

### 5.1 No data (REQ-7.6)
- Each panel sets "No data" text: "No flaky tests in this range" (Flaky tests) / "No shadow decisions in this range" (Shadow mode).

### 5.2 Demo banner (REQ-7.5)
- Text panel at the top, visible only when `$data != real` (repeat-by-variable trick or hidden row), text: **DEMO DATA — seeded history, not real CI results.**

### 5.3 Query errors
- Datasource or query errors show Grafana's panel error; the system-health alert (§12) covers ingestion stopping. No custom handling.

### 5.4 Time zone and formats (REQ-0.6)
- Dashboard time zone: Europe/Kyiv; numbers with thousands separators; percents with one decimal.

---

## 6. Panel → View Mapping

```
Flaky tests (dashboard)
├── Stat row ............................ v_flaky_tests, v_environmental_runs
├── Flaky tests by level ................ v_flaky_tests
├── Flaky tests by reason ............... v_flaky_tests
├── Flakiness rate trend ................ v_flakiness_daily
├── Flaky tests by environment .......... v_flaky_tests
├── Top 10 by cost score ................ v_flaky_tests → link test-drilldown
└── Environmental runs per repo ......... v_environmental_runs

Shadow mode (dashboard)
├── Stat row ............................ v_shadow_decisions
├── Decisions per team by outcome ....... v_shadow_decisions
├── Would-be quarantined share vs cap ... v_shadow_decisions
├── Protected-flaky tests ............... v_shadow_decisions
└── Shadow decision list ................ v_shadow_decisions → link test-drilldown, CI run
```

---

## 7. Dependencies

| Requirement | Depends on |
|-------------|------------|
| REQ-7.1, 7.2 | Reporting views from migration `0005_reporting_views` (backend §1, §12) |
| REQ-7.3 | `is_demo`, team, area, level columns in every view |
| REQ-7.4 | `test-drilldown` dashboard (stub here, full in M4-10) |
| REQ-7.5 | Seeded demo data (`fq-admin seed-demo`) |
| All | Datasource `fq-postgres` with `grafana_ro` (M0-05) |

---

## 8. Implementation Order

1. **Lint test first:** `grafana/tests/test_dashboards.py` — every panel uses a `reporting.` view, applies `$data`, has a title and "No data" text.
2. **Flaky tests dashboard:** variables → stat row → charts → top-10 table → environmental runs.
3. **Shadow mode dashboard:** stat row → charts → tables.
4. **Links:** dashboard links bar; test-drilldown stub; data links on test cells.
5. **Check with seeded data:** every panel non-empty for each team and level (REQ-8.5).

---

## 9. Acceptance Criteria Summary

### Navigation
- [ ] Both dashboards in the "Flaky Test Quarantine" folder with a shared links bar

### Flaky tests
- [ ] 4 stats, 5 charts, 1 table as specified; threshold lines at 5% (rate) and 10% (environmental ratio)

### Shadow mode
- [ ] 4 stats, 2 charts, 2 tables; cap gauge thresholds at 4% and 5%

### Behavior
- [ ] All variables apply to all panels; demo banner appears only for demo data
- [ ] Test cells open the drill-down for that test
- [ ] No-data texts shown instead of empty panels

### Quality
- [ ] Dashboards provisioned from JSON in the repo; lint test passes in CI

---

## 10. Colors and Thresholds

| Item | Color |
|------|-------|
| auto_quarantine | blue |
| needs_lead_approval | orange |
| protected_alert | red |
| Suggested only (reason) | light gray |
| Confirmed (reason) | dark blue |
| Rate threshold line (5%) | red, dashed |
| Environmental ratio threshold (10%) | orange, dashed |

Reasons use one fixed palette across all panels so the same reason is always the same color.
