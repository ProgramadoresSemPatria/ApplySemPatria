# Local setup templates

Personal data (profile, resume path, email, apply state) is **not** in git.
Copy a track template into `tracks/` on your machine, then run onboarding.

```bash
cd ~/job-search
TRACK=ai-engineer   # or android-developer

mkdir -p "tracks/$TRACK"
cp -R "examples/tracks/$TRACK/." "tracks/$TRACK/"

# Edit profile + resume path, then:
.venv/bin/python scripts/jobsearch.py onboarding --track "$TRACK"
```

Files to edit before applying:

| File | What to set |
|------|-------------|
| `applicant-profile.json` | Name, email, phone, LinkedIn, resume path, message templates |
| `email-apply-config.json` | Sender email/name, resume path |
| `config.json` / `linkedin-posts-config.json` | Search keywords, filters (optional tweaks) |

Shared scam-domain blocklist stays at repo root: `domain-blacklist.json`.
