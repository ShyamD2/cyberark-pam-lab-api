from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AccountStatus(str, Enum):
    COMPLIANT = "compliant"
    PENDING_ROTATION = "pending_rotation"
    FAILED = "failed"
    DISABLED = "disabled"


class SessionStatus(str, Enum):
    ACTIVE = "active"
    TERMINATED = "terminated"
    COMPLETED = "completed"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SafeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = ""
    cpm: str = "PasswordManager"
    managing_team: str = "pam-admins"


class SafeUpdate(BaseModel):
    description: str | None = None
    cpm: str | None = None
    managing_team: str | None = None


class Safe(SafeCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


class AccountCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    address: str = Field(min_length=1, max_length=255)
    platform_id: str = "WinServerLocal"
    safe_id: str
    status: AccountStatus = AccountStatus.PENDING_ROTATION
    risk_level: RiskLevel = RiskLevel.MEDIUM


class AccountUpdate(BaseModel):
    address: str | None = None
    platform_id: str | None = None
    status: AccountStatus | None = None
    risk_level: RiskLevel | None = None


class Account(AccountCreate):
    id: str
    created_at: datetime
    last_rotated_at: datetime | None = None


class SessionCreate(BaseModel):
    account_id: str
    requested_by: str = Field(min_length=1, max_length=64)
    connection_component: str = "PSM-RDP"


class PamSession(SessionCreate):
    id: str
    status: SessionStatus
    started_at: datetime
    ended_at: datetime | None = None


class SafeSummary(BaseModel):
    safe_id: str
    safe_name: str
    account_count: int


class DashboardSummary(BaseModel):
    total_safes: int
    total_accounts: int
    accounts_by_status: dict[str, int]
    accounts_by_risk: dict[str, int]
    active_sessions: int
    compliance_rate: float
    accounts_per_safe: list[SafeSummary]
