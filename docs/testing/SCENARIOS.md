# Test scenarios

Catalog of behaviors we must preserve. Each scenario maps to automated tests in `tests/`.

## UI dashboard (`ui/applications/index.html`)

Full **Given / When / Then** e2e catalog: [UI_E2E_SCENARIOS.md](./UI_E2E_SCENARIOS.md)

| ID | Scenario | Expected |
|----|----------|----------|
| UI-01 | Load `/api/meta` | `ui_approval: true`; no stale-server banner |
| UI-02 | Load snapshot | Cards render role, company, step pills |
| UI-03 | Tap **Send connection** | `POST /api/action` `{ action: "dm_connect", job_key }` |
| UI-04 | After action success | Only that card updates; scroll position unchanged |
| UI-05 | Tap **Check connection** | `POST` with `action: "dm_check"` |
| UI-06 | Tap **Send message** | `POST` with `action: "dm_message"` |
| UI-07 | Disposition override | `POST /api/disposition`; card badge updates |
| UI-08 | Human review card | Steps hidden; hint shown |
| UI-09 | Filter chips | Grid re-renders; matching cards only |
| UI-10 | Stale server | Missing `/api/meta` shows warning banner |
| UI-13 | Bulk DM follow-up | `POST /api/bulk-action` `{ action: "dm_process_all" }` runs check-all then send-all |

## Feature / domain logic

| ID | Scenario | Expected |
|----|----------|----------|
| FE-01 | DM job, no prior state | `dm_connect` available; `dm_check` not |
| FE-02 | Connect pending | `dm_connect` in progress; `dm_check` available |
| FE-03 | Accepted, message wanted | `dm_message` available / in progress |
| FE-04 | Message sent | All DM steps done |
| FE-05 | Form+DM LinkedIn post | Both form and DM formats |
| FE-06 | Manual DM mode + UI approve | `linkedin_connect_allowed(ui_approved=True)` passes |
| FE-07 | Manual DM mode + CLI | Blocked without `--force-send` |
| FE-08 | Posted epoch (Himalayas) | Displays `4h` / `3d` / `YYYY-MM-DD`, not raw integer |
| FE-09 | Disposition auto | `filter_result` → best_fit / human_review / not_real |
| FE-10 | Disposition override | Stored on job; steps follow override |

## LinkedIn flow runner (`flows/linkedin-connect-or-message.json`)

| ID | Scenario | Expected (dry-run) |
|----|----------|-------------------|
| LI-01 | Profile with top **Connect** | Would commit `connect`; no message branch |
| LI-02 | Profile with **Message** only | Would commit `message` |
| LI-03 | Profile **Pending** | classify → `follow_only` |
| LI-04 | **Connect via More** menu | classify → `connect_more` |
| LI-05 | Already connected (More only) | classify → `connected` |
| LI-06 | Connected + Message button | classify → `message` (message preferred) |

## HAR replay (`tests/fixtures/har/*.har`)

| ID | Scenario | Expected |
|----|----------|----------|
| LI-HAR-01 | Replay connect HAR offline | Flow dry-run commits `connect` |
| LI-HAR-02 | Replay message HAR offline | Flow dry-run commits `message` |
| LI-HAR-03 | Classify all 6 profile types | Matches LI-01..06 |
| LI-HAR-04 | Wrong URL with `not_found=abort` | Navigation fails (no live network) |
| LI-HAR-05 | HAR files committed | Valid JSON, fixed port `18766`, ≥1 entry each |

## CLI / API (`ui_server.run_action`)

| ID | Scenario | Expected command |
|----|----------|------------------|
| CLI-01 | `dm_connect` from UI | `dm_apply.py --send --ui-approved --force-send …` |
| CLI-02 | `dm_message` from UI | `dm_followup.py --send --ui-approved …` |
| CLI-03 | `email_send` from UI | `email_apply.py --send --ui-approved --smtp …` |
| CLI-04 | `form_apply` | `url_apply.py apply --url …` |
| CLI-05 | Subprocess env | `JOBSEARCH_UI_APPROVED=1` set |
| CLI-06 | Missing job | `{ ok: false, message: "Job not found" }` |
| CLI-07 | Human review job | Steps disabled message |
| CLI-08 | Bulk DM process all | `dm_followup.py` check (no `--match`) then `--send --ui-approved --force-send` |

## Judge criteria (automated)

Rule-based judge (`tests/helpers/judge.py`) checks structured expectations.
Optional LLM judge (`JOBSEARCH_LLM_JUDGE=1`) for message template quality only — never required in CI.
