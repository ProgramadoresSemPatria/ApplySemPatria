# Gmail email apply — one-time setup

Send applications from **caiohandradelima@gmail.com** with resume attached via Gmail API (OAuth).

## 1. Google Cloud (5–10 min)

1. Open [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (e.g. `job-search-email`)
3. **APIs & Services → Enable APIs** → enable **Gmail API**
4. **OAuth consent screen** → External → add your email as test user
5. **Credentials → Create credentials → OAuth client ID**
   - Application type: **Desktop app**
   - Download JSON → save as:
     ```
     ~/job-search/secrets/gmail-credentials.json
     ```

## 2. Install Python deps (once)

```bash
pip3 install --user google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

## 3. Authorize Gmail (browser, once)

```bash
python3 ~/job-search/scripts/gmail_setup.py
```

Opens browser → sign in as **caiohandradelima@gmail.com** → allow **Send email on your behalf**.

Token saved to `~/job-search/state/gmail-token.json` (local only, gitignored).

## 4. Preview applications (no send)

```bash
python3 ~/job-search/scripts/email_apply.py --list
python3 ~/job-search/scripts/email_apply.py --dry-run --limit 5
```

## 5. Send (after you approve preview)

```bash
python3 ~/job-search/scripts/email_apply.py --send --limit 3
```

Each send is logged in `~/job-search/state/email-applications.json` and optionally to Applika.

## Alternative: App Password (SMTP)

If you prefer not to use Google Cloud:

1. Google Account → Security → 2-Step Verification → **App passwords**
2. Create app password for "Mail"
3. Export (never commit):

```bash
export GMAIL_APP_PASSWORD='your-16-char-app-password'
python3 ~/job-search/scripts/email_apply.py --send --smtp
```

## Safety

- Default is **dry-run** — must pass `--send` to actually email
- **45s delay** between sends (configurable)
- Skips jobs already in sent log or Applika "already applied" list
- Never commit `secrets/` or tokens
