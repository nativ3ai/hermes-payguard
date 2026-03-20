from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from .config import RuntimeConfig
from .models import PaymentIntent


class CircleConfigError(RuntimeError):
    pass


@dataclass
class CircleExecutionResult:
    rail: str
    response: dict[str, Any]


class CircleClient:
    def __init__(self, config: RuntimeConfig):
        self.config = config

    def _headers(self, *, user_controlled: bool = False) -> dict[str, str]:
        if not self.config.circle_api_key:
            raise CircleConfigError("CIRCLE_API_KEY is required")
        headers = {
            "Authorization": f"Bearer {self.config.circle_api_key}",
            "Content-Type": "application/json",
            "X-Request-Id": str(uuid.uuid4()),
        }
        if user_controlled:
            if not self.config.circle_x_user_token:
                raise CircleConfigError("CIRCLE_X_USER_TOKEN is required for user-controlled transfers")
            headers["X-User-Token"] = self.config.circle_x_user_token
        return headers

    def _post(self, path: str, payload: dict[str, Any], *, user_controlled: bool = False) -> dict[str, Any]:
        with httpx.Client(timeout=self.config.http_timeout_seconds) as client:
            response = client.post(
                f"{self.config.circle_api_base_url}{path}",
                headers=self._headers(user_controlled=user_controlled),
                json=payload,
            )
        response.raise_for_status()
        return response.json()

    def transfer_dev(self, intent: PaymentIntent) -> CircleExecutionResult:
        if not self.config.circle_entity_secret_ciphertext:
            raise CircleConfigError("CIRCLE_ENTITY_SECRET_CIPHERTEXT is required for developer-controlled transfers")
        wallet_id = intent.source_wallet_id or self.config.circle_wallet_id
        if not wallet_id:
            raise CircleConfigError("CIRCLE_WALLET_ID or source_wallet_id is required")
        token_id = intent.token_id or self.config.circle_token_id
        if not token_id:
            raise CircleConfigError("CIRCLE_TOKEN_ID or token_id is required")
        payload = {
            "idempotencyKey": intent.id,
            "destinationAddress": intent.recipient,
            "entitySecretCiphertext": self.config.circle_entity_secret_ciphertext,
            "amounts": [intent.amount_usdc],
            "feeLevel": "MEDIUM",
            "refId": intent.reason or intent.id,
            "tokenId": token_id,
            "walletId": wallet_id,
            "blockchain": intent.chain,
        }
        data = self._post("/v1/w3s/developer/transactions/transfer", payload)
        return CircleExecutionResult(rail="circle_dev", response=data)

    def transfer_user(self, intent: PaymentIntent) -> CircleExecutionResult:
        wallet_id = intent.source_wallet_id or self.config.circle_wallet_id
        if not wallet_id:
            raise CircleConfigError("CIRCLE_WALLET_ID or source_wallet_id is required")
        token_id = intent.token_id or self.config.circle_token_id
        if not token_id:
            raise CircleConfigError("CIRCLE_TOKEN_ID or token_id is required")
        payload = {
            "idempotencyKey": intent.id,
            "destinationAddress": intent.recipient,
            "walletId": wallet_id,
            "amounts": [intent.amount_usdc],
            "feeLevel": "MEDIUM",
            "refId": intent.reason or intent.id,
            "tokenId": token_id,
            "blockchain": intent.chain,
        }
        data = self._post("/v1/w3s/user/transactions/transfer", payload, user_controlled=True)
        return CircleExecutionResult(rail="circle_user", response=data)
