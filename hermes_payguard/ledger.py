from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .models import PaymentIntent


@dataclass
class ApprovalState:
    approved: bool
    expires_at: str | None = None
    actor: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"approved": self.approved, "expires_at": self.expires_at, "actor": self.actor}


class IntentLedger:
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.intents_dir = state_dir / "intents"
        self.approvals_dir = state_dir / "approvals"
        self.audit_log = state_dir / "audit.jsonl"
        self.intents_dir.mkdir(parents=True, exist_ok=True)
        self.approvals_dir.mkdir(parents=True, exist_ok=True)

    def _intent_path(self, intent_id: str) -> Path:
        return self.intents_dir / f"{intent_id}.json"

    def _approval_path(self, intent_id: str) -> Path:
        return self.approvals_dir / f"{intent_id}.json"

    def save_intent(self, intent: PaymentIntent) -> None:
        path = self._intent_path(intent.id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(intent.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)

    def get_intent(self, intent_id: str) -> PaymentIntent | None:
        path = self._intent_path(intent_id)
        if not path.exists():
            return None
        return PaymentIntent.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_intents(self, limit: int = 20) -> list[PaymentIntent]:
        items: list[PaymentIntent] = []
        for path in sorted(self.intents_dir.glob("*.json"), reverse=True)[:limit]:
            items.append(PaymentIntent.from_dict(json.loads(path.read_text(encoding="utf-8"))))
        return items

    def approve_intent(self, intent_id: str, ttl_seconds: int = 900, actor: str = "operator") -> ApprovalState:
        expires_at = (datetime.now(UTC) + timedelta(seconds=ttl_seconds)).isoformat()
        state = ApprovalState(approved=True, expires_at=expires_at, actor=actor)
        self._approval_path(intent_id).write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
        self.audit("intent_approved", intent_id, state.to_dict())
        return state

    def revoke_intent(self, intent_id: str, actor: str = "operator") -> None:
        path = self._approval_path(intent_id)
        if path.exists():
            path.unlink()
        self.audit("intent_revoked", intent_id, {"actor": actor})

    def get_approval(self, intent_id: str) -> ApprovalState:
        path = self._approval_path(intent_id)
        if not path.exists():
            return ApprovalState(approved=False)
        data = json.loads(path.read_text(encoding="utf-8"))
        expires_at = data.get("expires_at")
        if expires_at:
            dt = datetime.fromisoformat(expires_at)
            if dt <= datetime.now(UTC):
                return ApprovalState(approved=False, expires_at=expires_at, actor=data.get("actor"))
        return ApprovalState(approved=bool(data.get("approved")), expires_at=expires_at, actor=data.get("actor"))

    def audit(self, event: str, intent_id: str | None, payload: dict[str, Any]) -> None:
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "event": event,
            "intent_id": intent_id,
            "payload": payload,
        }
        with self.audit_log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
