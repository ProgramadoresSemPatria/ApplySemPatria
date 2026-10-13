# Opt-in telemetry (Firebase / GA4)

ApplySemPatria is **local-first**. Telemetry is **off by default** and only runs when you create `secrets/telemetry.json` with `"enabled": true`.

We use **Google Analytics 4** (Firebase Analytics web stream):

- **Browser:** Firebase JS SDK — research failures, UI errors (no job text, no emails).
- **Server:** GA4 Measurement Protocol — ingestion step failures from Python (same project).

**Firebase Crashlytics** targets native mobile apps. This project is Python + a local web UI; use Analytics **custom events** and the **support bundle** below instead of Crashlytics for now.

## 1. Create a Firebase project

1. [Firebase console](https://console.firebase.google.com/) → **Add project** (e.g. `applysempatria-telemetry`).
2. Disable Google Analytics only if you do not want any analytics; otherwise keep it enabled and pick or create a GA4 property.

## 2. Register a Web app

1. Project overview → **Web** (`</>`).
2. App nickname: `ApplySemPatria UI`.
3. Copy the `firebaseConfig` object fields into `firebase_web` in the example file.

## 3. GA4 Measurement Protocol (server events)

1. [Google Analytics](https://analytics.google.com/) → **Admin** → your property → **Data streams** → select the **Web** stream.
2. Note **Measurement ID** (`G-…`) → `measurement_id` in config.
3. **Measurement Protocol API secrets** → **Create** → copy secret → `api_secret` in config (keep in `secrets/` only).

## 4. Enable on a machine

```bash
cp examples/telemetry.firebase.json secrets/telemetry.json
# Edit: enabled true, fill measurement_id, api_secret, firebase_web
make telemetry-doctor
make stop && make ui
```

Hard refresh the dashboard. Failed research should emit `research_failed` / `research_step_failed` in GA4 **DebugView** (enable debug mode in browser devtools if needed).

## 5. Gather logs from a user (support)

**Anonymous bundle (recommended):**

```bash
make support-bundle
# prints path to runs/support-bundle-*.json — user can attach to issue/email
```

From the UI (when telemetry is enabled): **Copy debug report** in the research prompt area sends the same redacted JSON and logs a `support_bundle_shared` event.

The bundle includes: anonymous `install_id`, git HEAD hint, `research-run` summary (sanitized message), last ~40 audit lines. It does **not** include `tracks/`, resumes, Gmail tokens, or LinkedIn cookies.

## Privacy

- No job titles, employer names, or apply URLs in telemetry params (messages are URL-stripped and truncated).
- `install_id` is a random UUID in `state/telemetry-install-id` (local).
- Set `"enabled": false` or delete `secrets/telemetry.json` to turn off all sends.
