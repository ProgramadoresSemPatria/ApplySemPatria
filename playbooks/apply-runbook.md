# Apply runbook — deterministic step-by-step

Single source of truth for the exact commands to apply per channel. Follow in
order. All live actions default to dry-run / no-submit; real actions need an
explicit flag. Keep this deterministic so runs are repeatable.

Profile data: `~/job-search/applicant-profile.json` (generic, per-user).
Table window: `~/job-search/state/table-window.json` (set when you run
`generate_applications.py`; apply scripts read it for `--table-only`).
When a needed field is empty, ASK the user, then persist:

```bash
python3 ~/job-search/scripts/profile_store.py missing        # list empty required fields
python3 ~/job-search/scripts/profile_store.py set phone "+55 11 9....."
python3 ~/job-search/scripts/profile_store.py show
```

---

## −1. Discovery (optional — populate registry before table)

Only needed when the registry is stale or you want new posts since last run.

```bash
# LinkedIn posts (browser deep-collect only) — see skill linkedin-posts-discover
# Board jobs — see skill job-search-discover
python3 ~/job-search/scripts/discover.py --since 7d
```

Then continue with step 0.

---

## 0. Refresh the table (channels) — always first

Generated tables: `~/job-search/runs/tables/applications/` (see `runs/tables/README.md`).

```bash
python3 ~/job-search/scripts/repair_registry_fields.py
# Window defaults to last Monday; persisted in state/table-window.json
python3 ~/job-search/scripts/generate_applications.py
# → ~/job-search/runs/tables/applications/applications-$(date +%Y-%m-%d)-full.md
```

Channel column = Email | URL/Form | Direct Msg. Comment-to-apply → Direct Msg
(NEVER comment).

**Note:** the apply scripts auto-refresh this table after every `--send` run
(`email_apply.py`, `dm_apply.py`, `dm_followup.py` → `table_refresh.py`), so the
**Status** column always reflects live progress. Step 0 is still the deterministic
first step for a fresh discovery, but you never have to manually refresh after
applying.

---

## 1. EMAIL channel

Goal: send resume + short message to recruiter email.

```bash
# a. Preview candidates
python3 ~/job-search/scripts/email_apply.py --list --table-only

# b. Dry run (no send)
python3 ~/job-search/scripts/email_apply.py --dry-run --table-only --limit 3

# c. Send (SMTP app password from ~/.zshrc)
source ~/.zshrc
python3 ~/job-search/scripts/email_apply.py --send --smtp --table-only --limit 3
```

Subject: `Application for {role}` · Body: greeting + qualifications line · resume attached.
Log: `state/email-applications.json`.

---

## 2. DIRECT MSG channel

Goal: connect (NO note); once ACCEPTED, send a message. Already-connected → message
directly. No resume yet. NEVER comment. **Runtime: `~/job-search/.venv/bin/python`.**

Pipeline: `scan → connect → [wait for acceptance] → follow-up message`.
You can only message AFTER acceptance.

```bash
PY=~/job-search/.venv/bin/python

# a. Scan (headless): classify profiles -> runs/dm-scan.json
$PY ~/job-search/scripts/dm_apply.py --scan

# b. Connect-only, audit 1-by-1 (dry, then live)
$PY ~/job-search/scripts/dm_apply.py --actionable --limit 1
$PY ~/job-search/scripts/dm_apply.py --actionable --limit 1 --send

# c. Follow-up: message those who ACCEPTED (dry, then live)
$PY ~/job-search/scripts/dm_followup.py --list
$PY ~/job-search/scripts/dm_followup.py --send --limit 1
```

- Connect → "Send without a note" (scope actions to `<main>`).
- Follow-only (out-of-network) profiles are skipped — cannot connect w/o Premium.
- Message text: `applicant-profile.json` → `dm_message_template`.
- State: `state/dm-applications.json` (connect_requested → accepted → message_sent),
  surfaced in the table **Status** column. 20s between real actions.
- Verify: Sent Invitations page (connects); message thread (messages).
- If DOM automation breaks, retry with headed browser or update flow recipes in `flows/`.

---

## 3. URL/FORM channel

Goal: open apply link visibly, understand form, autofill, upload resume, submit after review.

```bash
# a. Inspect the form schema (agent reads fields)
python3 ~/job-search/scripts/url_apply.py inspect --url "APPLY_URL" --hold 60

# b. Autofill from profile + upload resume (no submit)
python3 ~/job-search/scripts/url_apply.py apply --url "APPLY_URL" --hold 180

# c. Fill gaps then submit
#    /tmp/answers.json = {"field-name-or-label": "value", ...}
python3 ~/job-search/scripts/url_apply.py apply --url "APPLY_URL" \
  --answers /tmp/answers.json --submit --hold 120
```

Before URL runs, ensure profile has: phone, years_experience,
salary_expectation_usd, notice_period (else forms block).

---

## Deterministic flows (save LLM cost)

Browser steps are stored as recipes in `flows/*.json` and replayed by
`flow_runner.py` — no LLM reasoning per application.

- DM uses `flows/linkedin-connect-or-message.json`.
- URL/Form resolves an ATS recipe by domain (`flows/ats-*.json`), then heuristic gap-fill.
- Unknown site? Inspect ONCE, write `flows/<site>.json`, then always replay it.
- See skill `playwright-flows` for the recipe schema.

Never re-analyze a known site with the LLM — replay its saved recipe.

## Per-role loop (all channels)

1. Read next role from the table (top → down).
2. Determine `Channel`.
3. Run the channel's command with `--limit 1` (or the URL for that role).
4. Report: role, channel, action taken, result, any blocker.
5. Dedupe via each channel's state file; skip Applika blocklist.
6. Continue to next role until the table end.
