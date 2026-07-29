import threading
import uuid
from datetime import datetime, timedelta, timezone

from app.models import (
    Account,
    AccountCreate,
    AccountStatus,
    AccountUpdate,
    PamSession,
    RiskLevel,
    Safe,
    SafeCreate,
    SafeUpdate,
    SessionCreate,
    SessionStatus,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


class LabStore:
    """In-memory datastore for the PAM lab dashboard."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.safes: dict[str, Safe] = {}
        self.accounts: dict[str, Account] = {}
        self.sessions: dict[str, PamSession] = {}

    def reset(self) -> None:
        with self._lock:
            self.safes.clear()
            self.accounts.clear()
            self.sessions.clear()

    # safes
    def list_safes(self) -> list[Safe]:
        return sorted(self.safes.values(), key=lambda s: s.name)

    def get_safe(self, safe_id: str) -> Safe:
        try:
            return self.safes[safe_id]
        except KeyError:
            raise NotFoundError(f"safe {safe_id} not found") from None

    def create_safe(self, payload: SafeCreate) -> Safe:
        with self._lock:
            if any(s.name.lower() == payload.name.lower() for s in self.safes.values()):
                raise ConflictError(f"safe named {payload.name} already exists")
            safe = Safe(id=_new_id("safe"), created_at=_now(), **payload.model_dump())
            self.safes[safe.id] = safe
            return safe

    def update_safe(self, safe_id: str, payload: SafeUpdate) -> Safe:
        with self._lock:
            safe = self.get_safe(safe_id)
            updated = safe.model_copy(update=payload.model_dump(exclude_none=True))
            self.safes[safe_id] = updated
            return updated

    def delete_safe(self, safe_id: str) -> None:
        with self._lock:
            self.get_safe(safe_id)
            if any(a.safe_id == safe_id for a in self.accounts.values()):
                raise ConflictError(f"safe {safe_id} still holds accounts")
            del self.safes[safe_id]

    # accounts
    def list_accounts(
        self,
        safe_id: str | None = None,
        status: AccountStatus | None = None,
        risk_level: RiskLevel | None = None,
    ) -> list[Account]:
        items = list(self.accounts.values())
        if safe_id:
            items = [a for a in items if a.safe_id == safe_id]
        if status:
            items = [a for a in items if a.status == status]
        if risk_level:
            items = [a for a in items if a.risk_level == risk_level]
        return sorted(items, key=lambda a: (a.address, a.username))

    def get_account(self, account_id: str) -> Account:
        try:
            return self.accounts[account_id]
        except KeyError:
            raise NotFoundError(f"account {account_id} not found") from None

    def create_account(self, payload: AccountCreate) -> Account:
        with self._lock:
            self.get_safe(payload.safe_id)
            duplicate = any(
                a.username.lower() == payload.username.lower()
                and a.address.lower() == payload.address.lower()
                for a in self.accounts.values()
            )
            if duplicate:
                raise ConflictError(f"account {payload.username}@{payload.address} already exists")
            account = Account(id=_new_id("acct"), created_at=_now(), **payload.model_dump())
            self.accounts[account.id] = account
            return account

    def update_account(self, account_id: str, payload: AccountUpdate) -> Account:
        with self._lock:
            account = self.get_account(account_id)
            updated = account.model_copy(update=payload.model_dump(exclude_none=True))
            self.accounts[account_id] = updated
            return updated

    def delete_account(self, account_id: str) -> None:
        with self._lock:
            self.get_account(account_id)
            if any(
                s.account_id == account_id and s.status == SessionStatus.ACTIVE
                for s in self.sessions.values()
            ):
                raise ConflictError(f"account {account_id} has an active session")
            del self.accounts[account_id]

    def rotate_account(self, account_id: str) -> Account:
        with self._lock:
            account = self.get_account(account_id)
            if account.status == AccountStatus.DISABLED:
                raise ConflictError(f"account {account_id} is disabled")
            rotated = account.model_copy(
                update={"status": AccountStatus.COMPLIANT, "last_rotated_at": _now()}
            )
            self.accounts[account_id] = rotated
            return rotated

    # sessions
    def list_sessions(self, status: SessionStatus | None = None) -> list[PamSession]:
        items = list(self.sessions.values())
        if status:
            items = [s for s in items if s.status == status]
        return sorted(items, key=lambda s: s.started_at, reverse=True)

    def get_session(self, session_id: str) -> PamSession:
        try:
            return self.sessions[session_id]
        except KeyError:
            raise NotFoundError(f"session {session_id} not found") from None

    def create_session(self, payload: SessionCreate) -> PamSession:
        with self._lock:
            account = self.get_account(payload.account_id)
            if account.status == AccountStatus.DISABLED:
                raise ConflictError(f"account {account.id} is disabled")
            session = PamSession(
                id=_new_id("psm"),
                status=SessionStatus.ACTIVE,
                started_at=_now(),
                **payload.model_dump(),
            )
            self.sessions[session.id] = session
            return session

    def terminate_session(self, session_id: str) -> PamSession:
        with self._lock:
            session = self.get_session(session_id)
            if session.status != SessionStatus.ACTIVE:
                raise ConflictError(f"session {session_id} is not active")
            terminated = session.model_copy(
                update={"status": SessionStatus.TERMINATED, "ended_at": _now()}
            )
            self.sessions[session_id] = terminated
            return terminated


def seed(store: LabStore) -> LabStore:
    """Populate the store with a small, realistic PAM lab dataset."""
    store.reset()
    windows = store.create_safe(
        SafeCreate(name="WIN-DOMAIN-ADMINS", description="Domain admin accounts", cpm="PasswordManager")
    )
    linux = store.create_safe(
        SafeCreate(name="LINUX-ROOT", description="Root accounts for Linux fleet", managing_team="unix-ops")
    )
    db = store.create_safe(
        SafeCreate(name="DB-SERVICE-ACCOUNTS", description="Database service accounts", managing_team="dba")
    )

    specs = [
        ("svc_da01", "dc01.pam.lab", "WinDomainAccount", windows.id, AccountStatus.COMPLIANT, RiskLevel.CRITICAL),
        ("svc_da02", "dc02.pam.lab", "WinDomainAccount", windows.id, AccountStatus.PENDING_ROTATION, RiskLevel.CRITICAL),
        ("root", "app01.pam.lab", "UnixSSH", linux.id, AccountStatus.COMPLIANT, RiskLevel.HIGH),
        ("root", "app02.pam.lab", "UnixSSH", linux.id, AccountStatus.FAILED, RiskLevel.HIGH),
        ("sa_reports", "sql01.pam.lab", "MSSQLServer", db.id, AccountStatus.COMPLIANT, RiskLevel.MEDIUM),
        ("oracle_batch", "ora01.pam.lab", "Oracle", db.id, AccountStatus.DISABLED, RiskLevel.LOW),
    ]
    accounts = [
        store.create_account(
            AccountCreate(
                username=username,
                address=address,
                platform_id=platform,
                safe_id=safe_id,
                status=status,
                risk_level=risk,
            )
        )
        for username, address, platform, safe_id, status, risk in specs
    ]

    for account in accounts:
        if account.status == AccountStatus.COMPLIANT:
            store.accounts[account.id] = account.model_copy(
                update={"last_rotated_at": _now() - timedelta(days=3)}
            )

    store.create_session(SessionCreate(account_id=accounts[0].id, requested_by="alice", connection_component="PSM-RDP"))
    store.create_session(SessionCreate(account_id=accounts[2].id, requested_by="bob", connection_component="PSM-SSH"))
    finished = store.create_session(
        SessionCreate(account_id=accounts[4].id, requested_by="carol", connection_component="PSM-SQLPlus")
    )
    store.sessions[finished.id] = finished.model_copy(
        update={"status": SessionStatus.COMPLETED, "ended_at": _now() - timedelta(hours=1)}
    )
    return store
