# UI e2e scenarios (Given / When / Then)

Readable catalog for the applications dashboard at `ui/applications/index.html`.
Tests live in `tests/e2e/test_ui_dashboard.py` unless noted.

**Legend:** ✅ automated · ⬜ not yet automated · ⚠️ flaky in CI

---

## Background (shared setup)

```gherkin
Background: Mock UI server with one LinkedIn DM job
  Given the mock UI server is running on a random localhost port
  And the server exposes GET /api/meta with ui_approval: true
  And GET /api/days returns a single "live" day with 1 job
  And GET /api/snapshot?day=live returns one card for "Acme AI · AI Engineer"
  And the card has application_steps_enabled: true
  And step pills include "Send connection" (dm_connect) as clickable
  And POST /api/action is mocked to return ok: true plus an updated snapshot
```

Fixture source: `tests/conftest.py` (`mock_ui_server`) + `tests/helpers/jobs.py` (`ui_snapshot`).

---

## UI-01 — Server meta and no stale banner ✅

```gherkin
Scenario: Dashboard confirms UI-approved server on load
  Given I open the applications dashboard at /
  When the page finishes loading
  Then GET /api/meta was called
  And the stale-server banner (#serverStale) is hidden
  And at least one job card is visible
```

**Automated:** `test_dashboard_loads_meta_and_cards`

---

## UI-02 — Snapshot renders card fields ✅

```gherkin
Scenario: Live snapshot renders role and company on cards
  Given I open the applications dashboard at /
  When the snapshot loads
  Then I see a card with company "Acme AI"
  And the card shows step pills for available apply actions
  And the view subtitle mentions the job count
```

**Automated:** `test_dashboard_loads_meta_and_cards` (company assertion)

---

## UI-03 — Tap Send connection ✅

```gherkin
Scenario: Tapping Send connection posts dm_connect action
  Given I open the applications dashboard at /
  And the "Send connection" step pill is visible and clickable
  When I click the step pill with data-action="dm_connect"
  Then the mock server records action "dm_connect" with a job_key
```

**Automated:** `test_tap_connect_posts_action`  
**Stability:** asserts via mock server capture (`wait_for_mock_action`), not Playwright request interception.

---

## UI-04 — In-place card update preserves scroll ✅

```gherkin
Scenario: After an action, only the card updates and scroll stays put
  Given I open the applications dashboard at /
  And #cardsWrap has scrollTop = S
  When I click "Send connection" on the first card
  And the action completes (mock returns snapshot)
  Then at least one card remains visible
  And #cardsWrap scrollTop is still S
  And the full grid was not re-rendered from scratch (no flash-to-top)
```

**Automated:** `test_card_survives_after_action`  
**Implementation detail:** server returns `snapshot` in action response → `applySnapshot` → `updateCard`.

---

## UI-05 — Tap Check connection ⬜

```gherkin
Scenario: Tapping Check connection posts dm_check action
  Given a job card where dm_connect is in_progress
  And the "Check connection accepted" pill is clickable
  When I click the step pill with data-action="dm_check"
  Then POST /api/action is sent with action: "dm_check" and the job_key
  And only that card's step states refresh
```

**Fixture needed:** `ui_snapshot` with `dm_connect.in_progress: true`, `dm_check.available: true`.

---

## UI-06 — Tap Send message ⬜

```gherkin
Scenario: Tapping Send LinkedIn message posts dm_message action
  Given a job card where connection is accepted
  And the "Send LinkedIn message" pill is clickable
  When I click the step pill with data-action="dm_message"
  Then POST /api/action is sent with action: "dm_message" and the job_key
  And the toast shows success
```

**Fixture needed:** actions with `dm_message.available: true`, connect done.

---

## UI-07 — Disposition override from card menu ⬜

```gherkin
Scenario: User overrides triage disposition on a card
  Given I open the dashboard with a review-section job
  And I open the card menu (⋯)
  When I choose disposition "Real role" (data-disposition="real_role")
  Then POST /api/disposition is sent with job_key and disposition
  And the card badge updates to "Real role"
  And a "manual" override marker appears if applicable
  And scroll position is unchanged
```

**Server path:** `setDisposition` → `/api/disposition` → `applySnapshot(data.snapshot, job_key)`.

---

## UI-08 — Human review card hides steps ⬜ (unit only today)

```gherkin
Scenario: Human-review job shows hint and disables step pills
  Given snapshot contains a job with application_steps_enabled: false
  And section is linkedin_review
  When the card renders
  Then no step pill is clickable
  And a human-review hint is visible instead of apply steps
```

**Unit coverage:** `tests/test_applications_ui_actions.py::test_human_review_disables_steps_in_card`  
**E2e gap:** no Playwright test yet.

---

## UI-09 — Filter chips re-render grid ⬜

```gherkin
Scenario: Filter chip shows only matching jobs
  Given snapshot contains jobs in different sections and channels
  And filter chip "Direct message" is active
  When I click filter chip data-filter="email"
  Then only jobs with application_formats including email remain visible
  And the active chip styling moves to "Email"
  And #emptyState is shown if zero jobs match

Scenario: Search box filters by role or company
  Given multiple cards are visible
  When I type "Acme" in #searchInput
  Then only cards whose role or company contains "acme" (case-insensitive) remain
```

---

## UI-10 — Stale server banner ⬜

```gherkin
Scenario: Missing or non-UI-approved meta shows warning
  Given GET /api/meta returns ui_approval: false OR returns HTTP 4xx/5xx OR network error
  When the dashboard loads
  Then #serverStale is visible
  And the user is warned to restart with jobsearch ui (or --ui-approved)

Scenario: UI-approved meta hides warning
  Given GET /api/meta returns ui_approval: true
  When the dashboard loads
  Then #serverStale stays hidden
```

**Automated partially:** UI-01 asserts hidden banner with good meta only.

---

## UI-13 — Bulk DM full pipeline (connect · check · send) ✅

**Automated:** `test_bulk_dm_button_triggers_process_all`, `test_bulk_dm_button_passes_all_dm_job_keys`, `tests/test_bulk_dm_regression.py`

```gherkin
Scenario: List header bulk button processes DM roles in the current filter
  Given I open the applications dashboard at /
  And the list header shows "Applications" with the filtered role count
  And the bulk button sits to the right of the list title
  When I click #bulkDmBtn in the list header
  Then the mock server records bulk action "dm_process_all" with job_keys for visible DM roles
```

**Automated:** `test_bulk_dm_button_triggers_process_all`  
**Server:** `POST /api/bulk-action` → `run_bulk_dm_followup()` → three phases: `dm_apply.py` connect → `dm_followup.py` check → `dm_followup.py` send.

---

## UI-14 — Research prompt (today pending) ✅

**Automated:** `test_research_prompt_when_no_research_today`

---

## UI-15 — Past day while today pending ✅

**Automated:** `test_select_past_day_while_today_pending`

---

## UI-16 — Research progress + completion ✅

**Automated:** `test_research_button_shows_progress_and_completes`

---

## UI-17 — DM message already sent ✅

**Automated:** `test_dm_message_pill_done_when_already_sent` · unit: `tests/test_dm_chat.py`

---

## UI-18 — Bulk DM full pipeline when queue empty ✅

**Automated:** `test_bulk_dm_empty_queue_still_runs_full_pipeline`

---

## UI-19 — Bulk DM legacy profile key match ✅

**Automated:** `test_bulk_dm_legacy_profile_key_runs_full_pipeline` · unit: `tests/test_dm_followup.py`

---

## UI-20 — Bulk email candidature ✅

**Automated:** `test_bulk_email_button_triggers_process_all`, `test_bulk_email_button_disabled_without_email_roles`, `test_bulk_email_button_shows_done_when_all_sent`, `test_stale_server_banner_when_meta_missing_bulk_email`, `tests/test_ui_client_contract.py`, `test_bulk_email_routing_uses_real_handler`  
**Server:** `POST /api/bulk-action` with `action: email_process_all` → `run_bulk_email_apply()` → `email_apply.py --send --smtp --job-keys …`  
**UI:** `#bulkEmailBtn` beside bulk DM; disabled when no pending email roles; shows green ✓ + “sent” when all email roles in list are done; refreshes snapshot without scroll jump via `applySnapshot()`.

---

## UI-11 — Manual DM mode toast hint ⬜

```gherkin
Scenario: Failed action explains manual DM mode when server not UI-approved
  Given serverUiApproval is false (stale banner visible)
  And POST /api/action returns ok: false with message containing "Manual DM mode"
  When I tap an apply step
  Then the toast appends "restart the UI server: jobsearch ui"
```

---

## UI-12 — Day picker and live refresh ⬜

```gherkin
Scenario: Selecting a historical day loads that snapshot
  Given GET /api/days returns "live" and "2026-09-05"
  When I click the day button for 2026-09-05
  Then GET /api/snapshot?day=2026-09-05 is requested
  And cards reflect that day's jobs

Scenario: Live button reloads live snapshot
  Given I am viewing a historical day
  When I click #liveBtn
  Then GET /api/snapshot?day=live is requested
```

---

## Mapping to coverage (Python backend)

| Scenario group | Primary modules measured in `scripts/` |
|----------------|----------------------------------------|
| UI-01, UI-10 | `ui_server.py` (`/api/meta`) |
| UI-02, UI-04, UI-08, UI-09 | `applications_ui_data.py` |
| UI-03, UI-05, UI-06, UI-11 | `ui_server.py` (`run_action`) |
| UI-07 | `ui_server.py`, `position_disposition.py` |
| UI-08 | `applications_ui_data.py`, `position_disposition.py` |

Frontend JS in `index.html` is **not** in pytest-cov scope; e2e tests assert behavior through the browser.

---

## Adding a new scenario

1. Add a **Given / When / Then** block here with ID `UI-XX`.
2. Extend `ui_snapshot()` or add a fixture variant in `tests/helpers/jobs.py`.
3. Implement `test_…` in `tests/e2e/test_ui_dashboard.py`.
4. If backend paths change, run `./scripts/run_tests.sh coverage` and bump floors in `coverage-thresholds.json` if line rates improved.

See also: [COVERAGE.md](./COVERAGE.md) · [SCENARIOS.md](./SCENARIOS.md) · [STRATEGY.md](./STRATEGY.md)
