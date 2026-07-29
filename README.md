# CyberArk PAM Lab Dashboard API

REST API backing a lab dashboard for CyberArk-style Privileged Access Management data:
safes, privileged accounts, password rotation and PSM sessions. State is in-memory and
seeded with a small realistic lab dataset on startup — it is a lab, not a production vault.

## Run

```bash
docker compose up --build          # http://localhost:8000
```

Or without Docker:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload
```

Interactive docs: http://localhost:8000/docs

## Auth

Read endpoints are open. Every write endpoint requires the `X-API-Key` header, compared in
constant time against `PAM_LAB_API_KEY`. If that variable is unset, a random key is generated
at startup and logged as a warning — there is no well-known default. `docker-compose.yml`
sets `lab-demo-key` for local lab use.

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/health` | Liveness probe |
| GET | `/api/v1/summary` | Dashboard metrics (counts, compliance rate, active sessions) |
| GET/POST | `/api/v1/safes` | List / create safes |
| GET/PATCH/DELETE | `/api/v1/safes/{safe_id}` | Read / update / delete a safe |
| GET/POST | `/api/v1/accounts` | List (filters: `safe_id`, `status`, `risk_level`) / create accounts |
| GET/PATCH/DELETE | `/api/v1/accounts/{account_id}` | Read / update / delete an account |
| POST | `/api/v1/accounts/{account_id}/rotate` | Rotate credential, mark compliant |
| GET/POST | `/api/v1/sessions` | List (filter: `status`) / start PSM sessions |
| POST | `/api/v1/sessions/{session_id}/terminate` | Terminate an active session |
| POST | `/api/v1/admin/reseed` | Reset store to the seed dataset |

Referential rules: a safe holding accounts cannot be deleted, an account with an active
session cannot be deleted, disabled accounts cannot be rotated or connected to, and
duplicate safe names or `username@address` pairs return `409`.

## Test

```bash
pip install -e '.[dev]'
pytest -q
ruff check .
```
