# LinkedIn content search — browser only

**We do not use LinkedIn MCP** (removed — low yield, session risk). All LinkedIn post discovery uses **Patchright browser scroll** via `linkedin-deep-collect.sh`.

## Recommended command

```bash
~/job-search/scripts/linkedin-deep-collect.sh --all-queries --merge --since 7d
```

Or per track (when wired):

```bash
~/job-search/scripts/linkedin-deep-collect.sh \
  --query '"ai engineer" + "latam"' \
  --max-roles 100 \
  --merge --since 7d
```

## Why browser only

| Approach | Yield | Status |
|----------|-------|--------|
| **Browser deep-collect** | Up to 100 roles/query, scroll + accumulate | **Active** |
| LinkedIn MCP `search_posts` | ~3 posts/query | **Removed** |
| Board APIs (RemoteOK, etc.) | Full listings | **Active** via `jobsearch discover` |

Browser scroll uses `mouse.wheel`, accumulates `Feed post` chunks, and saves to `runs/browser-collect-*/`.

## Login

```bash
~/job-search/scripts/linkedin-login.sh status
```

Cookies: `~/.linkedin-mcp/cookies.json` (directory name is legacy; no MCP server required).

## After collect

1. `repair_linkedin_urls.py` — fix profile/post URLs from saved runs
2. `backfill_post_permalinks.py` — resolve `/posts/…` permalinks
3. `generate_applications.py` or `jobsearch table` — refresh applications table

## Query format

Same as LinkedIn UI content search:

```
"{role}" + "{region}"
```

6 queries per track (3 roles × latam/worldwide). Config: `linkedin-posts-config.json` per track.
