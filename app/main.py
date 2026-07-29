import logging
import os
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from app.models import (
    Account,
    AccountCreate,
    AccountStatus,
    AccountUpdate,
    DashboardSummary,
    PamSession,
    RiskLevel,
    Safe,
    SafeCreate,
    SafeSummary,
    SafeUpdate,
    SessionCreate,
    SessionStatus,
)
from app.store import ConflictError, LabStore, NotFoundError, seed

API_KEY_ENV = "PAM_LAB_API_KEY"

logger = logging.getLogger(__name__)


def _resolve_api_key() -> str:
    key = os.getenv(API_KEY_ENV)
    if key:
        return key
    key = secrets.token_urlsafe(24)
    logger.warning("%s is unset; generated an ephemeral write key: %s", API_KEY_ENV, key)
    return key


API_KEY = _resolve_api_key()

store = seed(LabStore())

app = FastAPI(
    title="CyberArk PAM Lab Dashboard API",
    description="REST API backing a lab dashboard for safes, privileged accounts and PSM sessions.",
    version="1.0.0",
)


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if not x_api_key or not secrets.compare_digest(x_api_key, API_KEY):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or missing X-API-Key")


write = [Depends(require_api_key)]


@app.exception_handler(NotFoundError)
async def _not_found(_: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ConflictError)
async def _conflict(_: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/admin/reseed", tags=["meta"], dependencies=write)
def reseed() -> dict[str, str]:
    seed(store)
    return {"status": "reseeded"}


@app.get("/api/v1/summary", response_model=DashboardSummary, tags=["dashboard"])
def summary() -> DashboardSummary:
    accounts = store.list_accounts()
    by_status = {s.value: 0 for s in AccountStatus}
    by_risk = {r.value: 0 for r in RiskLevel}
    for account in accounts:
        by_status[account.status.value] += 1
        by_risk[account.risk_level.value] += 1
    compliant = by_status[AccountStatus.COMPLIANT.value]
    return DashboardSummary(
        total_safes=len(store.safes),
        total_accounts=len(accounts),
        accounts_by_status=by_status,
        accounts_by_risk=by_risk,
        active_sessions=len(store.list_sessions(SessionStatus.ACTIVE)),
        compliance_rate=round(compliant / len(accounts), 4) if accounts else 0.0,
        accounts_per_safe=[
            SafeSummary(
                safe_id=safe.id,
                safe_name=safe.name,
                account_count=len([a for a in accounts if a.safe_id == safe.id]),
            )
            for safe in store.list_safes()
        ],
    )


@app.get("/api/v1/safes", response_model=list[Safe], tags=["safes"])
def list_safes() -> list[Safe]:
    return store.list_safes()


@app.get("/api/v1/safes/{safe_id}", response_model=Safe, tags=["safes"])
def get_safe(safe_id: str) -> Safe:
    return store.get_safe(safe_id)


@app.post("/api/v1/safes", response_model=Safe, status_code=201, tags=["safes"], dependencies=write)
def create_safe(payload: SafeCreate) -> Safe:
    return store.create_safe(payload)


@app.patch("/api/v1/safes/{safe_id}", response_model=Safe, tags=["safes"], dependencies=write)
def update_safe(safe_id: str, payload: SafeUpdate) -> Safe:
    return store.update_safe(safe_id, payload)


@app.delete("/api/v1/safes/{safe_id}", status_code=204, tags=["safes"], dependencies=write)
def delete_safe(safe_id: str) -> None:
    store.delete_safe(safe_id)


@app.get("/api/v1/accounts", response_model=list[Account], tags=["accounts"])
def list_accounts(
    safe_id: str | None = Query(default=None),
    account_status: AccountStatus | None = Query(default=None, alias="status"),
    risk_level: RiskLevel | None = Query(default=None),
) -> list[Account]:
    return store.list_accounts(safe_id=safe_id, status=account_status, risk_level=risk_level)


@app.get("/api/v1/accounts/{account_id}", response_model=Account, tags=["accounts"])
def get_account(account_id: str) -> Account:
    return store.get_account(account_id)


@app.post("/api/v1/accounts", response_model=Account, status_code=201, tags=["accounts"], dependencies=write)
def create_account(payload: AccountCreate) -> Account:
    return store.create_account(payload)


@app.patch("/api/v1/accounts/{account_id}", response_model=Account, tags=["accounts"], dependencies=write)
def update_account(account_id: str, payload: AccountUpdate) -> Account:
    return store.update_account(account_id, payload)


@app.delete("/api/v1/accounts/{account_id}", status_code=204, tags=["accounts"], dependencies=write)
def delete_account(account_id: str) -> None:
    store.delete_account(account_id)


@app.post("/api/v1/accounts/{account_id}/rotate", response_model=Account, tags=["accounts"], dependencies=write)
def rotate_account(account_id: str) -> Account:
    return store.rotate_account(account_id)


@app.get("/api/v1/sessions", response_model=list[PamSession], tags=["sessions"])
def list_sessions(session_status: SessionStatus | None = Query(default=None, alias="status")) -> list[PamSession]:
    return store.list_sessions(status=session_status)


@app.post("/api/v1/sessions", response_model=PamSession, status_code=201, tags=["sessions"], dependencies=write)
def create_session(payload: SessionCreate) -> PamSession:
    return store.create_session(payload)


@app.post("/api/v1/sessions/{session_id}/terminate", response_model=PamSession, tags=["sessions"], dependencies=write)
def terminate_session(session_id: str) -> PamSession:
    return store.terminate_session(session_id)
