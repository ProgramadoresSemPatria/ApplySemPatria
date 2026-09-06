# HAR fixtures

Offline LinkedIn profile captures for stable CI. **Not** real linkedin.com traffic.

## Generate (after editing `tests/fixtures/linkedin/*.html`)

```bash
python scripts/generate_linkedin_hars.py
git add tests/fixtures/har/
```

Uses mock server at `http://127.0.0.1:18766/in/<slug>/` (fixed port — required for replay).

| HAR file | Slug | HTML fixture |
|----------|------|--------------|
| `profile-connect.har` | `test-connect` | Connect + Send without note |
| `profile-message.har` | `test-message` | Message + compose form |
| `profile-pending.har` | `test-pending` | Pending button |
| `profile-connect-more.har` | `test-connect-more` | More → Invite to connect |
| `profile-connected.har` | `test-connected` | Message + Remove connection in More |
| `profile-connected-only.har` | `test-connected-only` | More → Remove connection only |

Tests replay via `context.route_from_har(..., not_found="abort")` — zero network in CI.
