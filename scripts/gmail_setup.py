#!/usr/bin/env python3
"""One-time Gmail OAuth setup for email_apply.py (send scope only)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from track_store import default_track_id, load_email_config, resolve_track  # noqa: E402

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Authorize Gmail for email apply")
    parser.add_argument("--track", default=None, help=f"Track id (default: {default_track_id()})")
    args = parser.parse_args()

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Install deps: jobsearch install   (or pip install google-api-python-client google-auth-oauthlib)")
        return 1

    tid = resolve_track(args.track)
    cfg = load_email_config(tid)
    creds_path = ROOT / cfg["gmail_credentials_path"]
    token_path = ROOT / cfg["gmail_token_path"]
    token_path.parent.mkdir(parents=True, exist_ok=True)

    if not creds_path.exists():
        print(f"Missing OAuth client file: {creds_path}")
        print("Run: jobsearch onboarding --track", tid)
        print("Or see: playbooks/gmail-email-apply-setup.md")
        return 1

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    print(f"Gmail authorized for: {cfg['sender_email']}")
    print(f"Token saved: {token_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
