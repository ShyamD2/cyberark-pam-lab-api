---
name: testing-pam-lab-api
description: How to run and end-to-end test the CyberArk PAM Lab Dashboard API (FastAPI, in-memory store) through the Swagger UI, including auth, seed data expectations and the browser/GUI gotchas encountered while driving Swagger with computer-use.
---

# Testing the CyberArk PAM Lab Dashboard API

## Running the service

From the repo root:

```bash
docker compose up -d --build      # container cyberark-pam-lab-api-api-1, binds :8000
curl -s localhost:8000/health     # {"status":"ok"}
```

Swagger UI: `http://localhost:8000/docs`. A local `.venv` also exists for `pytest` / `ruff`.

## Auth

- All write endpoints (`POST`/`PATCH`/`DELETE`, plus `POST /api/v1/admin/reseed`) require header
  `X-API-Key`. Reads are unauthenticated.
- Default key is `lab-demo-key`, overridable via env var `PAM_LAB_API_KEY` (see `app/main.py`).
- There is **no global Swagger "Authorize" button** — the key is a plain `Header(...)` parameter, so you
  must type it into the per-operation `x-api-key` field for *every* write call. Budget for this.
- Wrong/missing key → `401 {"detail":"invalid or missing X-API-Key"}`.

**Devin Secrets Needed**: none. The API key is a non-secret lab default (`lab-demo-key`).

## State model — important for test design

The store is **in-process memory** (`app/store.py`), so:

- State resets on container restart, and is shared across all clients.
- `POST /api/v1/admin/reseed` rebuilds the dataset and **regenerates all IDs**. Capture IDs *after* the
  last reseed, or you will chase stale `safe-*` / `acct-*` values.
- Seed baseline (`seed()` in `app/store.py`): 3 safes, 6 accounts (compliant=3, pending_rotation=1,
  failed=1, disabled=1), `active_sessions=2` (a third seeded session is `completed`),
  `compliance_rate=0.5`.
- The seeded **disabled** account is `oracle_batch@ora01.pam.lab` — find its id with
  `GET /api/v1/accounts?status=disabled`. It is the only account that rejects rotate and session start.

## Business rules worth asserting (all 409 ConflictError)

- Delete a safe that still holds accounts → `409 "safe ... still holds accounts"`.
- Delete an account with an **active** session → `409 "account ... has an active session"`.
- Terminate an already-terminated/completed session → `409 "session ... is not active"`.
- Start a session on a `disabled` account → `409 "account ... is disabled"`.
- Duplicate safe name, or duplicate `username@address` account → `409`.
- `rotate` sets `status="compliant"` **and** `last_rotated_at`; it 409s on a disabled account.
- Note the query alias: the account/session status filter is `?status=`, not `?account_status=`.

### Make reseed/idempotent tests meaningful
A reseed test on an untouched store looks identical whether reseed works or is a no-op. **Mutate seed
data first** (e.g. rotate the seeded `pending_rotation` account so `compliance_rate` becomes `0.6667`),
then reseed and assert the summary returns to `0.5` with fresh safe IDs.

## Browser / Swagger UI gotchas (computer-use)

- **Stale responses**: collapsing and re-expanding an operation keeps the *previous* response body
  on screen. Always click **Execute** again and check the `date:` response header before asserting.
- **Dropped keystrokes**: typing JSON into the Swagger request-body textarea intermittently loses
  characters (`"PSM-SSH"` → `"S-SSH"`). Always `zoom` on the body to verify it before executing;
  splitting the `type` action into two shorter chunks helps.
- Long expanded operations make the page very tall — collapse operations you are done with, and use
  `ctrl+Home` / `ctrl+End` to reposition rather than many scroll calls.

## Restarting the GUI browser if it dies

`google-chrome` on this box is a **wrapper script** that just opens a tab in an already-running browser
via CDP (`curl -XPUT localhost:29229/json/new?<url>`). If the browser window is closed, the wrapper
silently fails with `connection refused`. Relaunch the real binary yourself:

```bash
export DISPLAY=:0
nohup /opt/.devin/playwright_browsers/chromium-*/chrome-linux/chrome \
  --remote-debugging-port=29229 --no-first-run \
  --user-data-dir=/home/ubuntu/.chrome-test "http://localhost:8000/docs" &
wmctrl -l                                              # confirm the window exists
wmctrl -a "Swagger UI"; wmctrl -r :ACTIVE: -b add,maximized_vert,maximized_horz
```

Do not use `xdotool key super+Up` to maximize — it half-tiles under this window manager.
