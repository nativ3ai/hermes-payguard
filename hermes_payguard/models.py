from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from datetime import UTC, datetime
from enum import Enum
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [json_safe(v) for v in value]
    return value


class IntentKind(str, Enum):
    USDC_TRANSFER = "usdc_transfer"
    X402_FETCH = "x402_fetch"


class PaymentRail(str, Enum):
    CIRCLE_DEV = "circle_dev"
    CIRCLE_USER = "circle_user"
    X402 = "x402"


class IntentStatus(str, Enum):
    PENDING_APPROVAL = "pending_approval"
    READY = "ready"
    EXECUTED = "executed"
    CHALLENGE_CREATED = "challenge_created"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass
class PolicyDecision:
    allowed: bool
    requires_approval: bool
    auto_approved: bool
    reason: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return json_safe(asdict(self))


@dataclass
class PaymentIntent:
    id: str
    kind: IntentKind
    rail: PaymentRail
    asset: str
    amount_usdc: str
    recipient: str
    chain: str
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)
    source_wallet_id: str | None = None
    source_wallet_address: str | None = None
    token_id: str | None = None
    status: IntentStatus = IntentStatus.PENDING_APPROVAL
    requires_approval: bool = True
    auto_approved: bool = False
    policy_reason: str = ""
    policy_details: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    executed_at: str | None = None
    approval_expires_at: str | None = None
    provider_response: dict[str, Any] | None = None
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["kind"] = self.kind.value
        data["rail"] = self.rail.value
        data["status"] = self.status.value
        return json_safe(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PaymentIntent":
        return cls(
            id=data["id"],
            kind=IntentKind(data["kind"]),
            rail=PaymentRail(data["rail"]),
            asset=data["asset"],
            amount_usdc=str(data["amount_usdc"]),
            recipient=data["recipient"],
            chain=data["chain"],
            reason=data.get("reason", ""),
            metadata=data.get("metadata") or {},
            source_wallet_id=data.get("source_wallet_id"),
            source_wallet_address=data.get("source_wallet_address"),
            token_id=data.get("token_id"),
            status=IntentStatus(data.get("status", IntentStatus.PENDING_APPROVAL.value)),
            requires_approval=bool(data.get("requires_approval", True)),
            auto_approved=bool(data.get("auto_approved", False)),
            policy_reason=data.get("policy_reason", ""),
            policy_details=data.get("policy_details") or {},
            created_at=data.get("created_at", utc_now()),
            executed_at=data.get("executed_at"),
            approval_expires_at=data.get("approval_expires_at"),
            provider_response=data.get("provider_response"),
            last_error=data.get("last_error"),
        )
