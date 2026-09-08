# LinkedIn Jobs search (pagination)

Collects roles from [LinkedIn Jobs search](https://www.linkedin.com/jobs/search/) — **not** content/post search.

## Selectors (Phase 0 spike)

| Element | Selector / pattern | Notes |
|---------|-------------------|--------|
| Job card root | `data-job-id="{id}"` | Primary stable ID |
| Job URL | `/jobs/view/{id}/` | Canonical listing URL |
| Title | `a.job-card-list__title` or `jobs/view/{id}` anchor text | Fallback: aria-label |
| Company | `h4.base-search-card__subtitle` | |
| Location | `.job-search-card__location` | |
| Posted time | `<time>` or `\d+[mhdw]\s*ago` in card chunk | Parsed via `parse_linkedin_relative_posted_at` |
| Easy Apply | text `Easy Apply` in card chunk | Sets `linkedin_easy_apply=true` |
| External apply | `Apply on company website` | `apply_method=external` |
| Next page | `start=` URL param + `button[aria-label="View next page"]` | Scroll results list before each page |

## URL parameters

- `keywords` — role name only (from config `roles`, via `query_template` default `{role}`)
- `location` — LATAM uses `Latin America`; worldwide omits location param
- `start` — pagination offset (`0`, `25`, `50`, … — 25 jobs per page)
- `f_WT=2` — remote only (when `remote_only: true`)
- `f_TPR` — time posted (`r86400` = past 24 hours when `default_period_days: 1`)
- `f_SAL` — optional salary band from config `salary_filter`
- `location` — per-country LATAM variants (Brazil, Mexico, …) instead of broken "Latin America" text
- `sortBy=DD` — date descending
- `location` — from `region_locations` (e.g. Latin America for latam)

## Pipeline

```bash
./scripts/linkedin-jobs-collect.sh --all-queries --merge --since 7d
python3 scripts/linkedin_jobs_merge.py --input runs/.../file.json --merge
```

Registry source: `linkedin_jobs`. Filtering uses `filters.evaluate_job()` (board rules), **not** post intent.

Cross-dedup: skips listings whose `/jobs/view/{id}` already exists in registry (from posts or prior runs).

Apply channel: URL/form — job page opens in browser.

**Easy Apply automation** (`scripts/linkedin_easy_apply.py`):
- Deterministic flow: `flows/linkedin-easy-apply-open.json` + wizard autofill (form-answers bank)
- Default **visual** (`--visual`) headed browser to watch execution
- Full submit: `linkedin_easy_apply.py apply --url … --visual --submit`
- UI **Apply via form** pill routes Easy Apply jobs here automatically
