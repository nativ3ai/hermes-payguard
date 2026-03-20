from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

from .config import RuntimeConfig
from .models import PaymentIntent
from .networks import normalize_chain_name, resolve_cctp_domain
from .policy import CCTPQuote


class CCTPConfigError(RuntimeError):
    pass


@dataclass
class CCTPExecutionResult:
    executor_response: dict[str, Any]
    message_status: dict[str, Any] | None


class CCTPClient:
    def __init__(self, config: RuntimeConfig):
        self.config = config

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | list[Any]:
        with httpx.Client(timeout=self.config.http_timeout_seconds) as client:
            response = client.get(
                f"{self.config.circle_cctp_api_base_url}{path}",
                params=params,
                headers={"Content-Type": "application/json"},
            )
        response.raise_for_status()
        return response.json()

    def _post_executor(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.config.cctp_executor_url:
            raise CCTPConfigError(
                "CCTP_EXECUTOR_URL is required for live CCTP execution. "
                "Prepare/quote works without it, but execution needs an external burner service."
            )
        with httpx.Client(timeout=self.config.http_timeout_seconds) as client:
            response = client.post(
                self.config.cctp_executor_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _normalize_fee_rows(payload: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            if isinstance(payload.get("data"), list):
                return [row for row in payload["data"] if isinstance(row, dict)]
            if isinstance(payload.get("fees"), list):
                return [row for row in payload["fees"] if isinstance(row, dict)]
        return []

    @staticmethod
    def _bps_to_usdc(amount_usdc: Decimal, basis_points: int) -> Decimal:
        return (amount_usdc * Decimal(basis_points)) / Decimal("10000")

    @staticmethod
    def _smallest_unit_to_usdc(value: Any, decimals: int = 6) -> Decimal:
        scale = Decimal(10) ** decimals
        return Decimal(str(value)) / scale

    def get_fee_quotes(
        self,
        source_chain: str,
        destination_chain: str,
        *,
        forward: bool = False,
    ) -> list[dict[str, Any]]:
        source_domain = resolve_cctp_domain(source_chain)
        destination_domain = resolve_cctp_domain(destination_chain)
        payload = self._get(
            f"/v2/burn/USDC/fees/{source_domain}/{destination_domain}",
            params={"forward": "true" if forward else "false"},
        )
        return self._normalize_fee_rows(payload)

    def select_quote(
        self,
        *,
        amount_usdc: Decimal,
        source_chain: str,
        destination_chain: str,
        transfer_speed: str = "standard",
        use_forwarder: bool = False,
        forward_gas_level: str = "medium",
    ) -> CCTPQuote:
        source_chain = normalize_chain_name(source_chain)
        destination_chain = normalize_chain_name(destination_chain)
        if source_chain == destination_chain:
            raise ValueError("CCTP source and destination chains must differ")
        fee_rows = self.get_fee_quotes(source_chain, destination_chain, forward=use_forwarder)
        if not fee_rows:
            raise ValueError("No CCTP fee quotes returned")
        sorted_rows = sorted(
            fee_rows,
            key=lambda row: int(row.get("finalityThreshold", 0)),
            reverse=(transfer_speed != "fast"),
        )
        selected = sorted_rows[0]
        minimum_fee_bps = int(selected.get("minimumFee", 0))
        forward_fee_map = selected.get("forwardFee") or {}
        forward_fee_raw = int(forward_fee_map.get(forward_gas_level, 0) if use_forwarder else 0)
        forward_fee_usdc = self._smallest_unit_to_usdc(forward_fee_raw)
        minimum_fee_usdc = self._bps_to_usdc(amount_usdc, minimum_fee_bps)
        return CCTPQuote(
            amount_usdc=amount_usdc,
            estimated_fee_usdc=minimum_fee_usdc + forward_fee_usdc,
            source_chain=source_chain,
            destination_chain=destination_chain,
            source_domain=resolve_cctp_domain(source_chain),
            destination_domain=resolve_cctp_domain(destination_chain),
            selected_finality_threshold=int(selected.get("finalityThreshold", 0)),
            forward_fee_usdc=forward_fee_usdc,
            minimum_fee_bps=minimum_fee_bps,
            use_forwarder=use_forwarder,
        )

    @staticmethod
    def _normalize_messages_payload(payload: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            if isinstance(payload.get("messages"), list):
                return [row for row in payload["messages"] if isinstance(row, dict)]
            if isinstance(payload.get("data"), list):
                return [row for row in payload["data"] if isinstance(row, dict)]
        return []

    def get_messages(
        self,
        *,
        source_chain: str,
        transaction_hash: str | None = None,
        nonce: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if transaction_hash:
            params["transactionHash"] = transaction_hash
        if nonce:
            params["nonce"] = nonce
        payload = self._get(f"/v2/messages/{resolve_cctp_domain(source_chain)}", params=params or None)
        return self._normalize_messages_payload(payload)

    def start_transfer(self, intent: PaymentIntent) -> dict[str, Any]:
        payload = {
            "intent_id": intent.id,
            "amount_usdc": intent.amount_usdc,
            "asset": intent.asset,
            "recipient": intent.recipient,
            "source_chain": intent.chain,
            "destination_chain": intent.metadata.get("destination_chain"),
            "reason": intent.reason,
            "quote": intent.metadata.get("cctp_quote"),
            "forward": bool(intent.metadata.get("use_forwarder", False)),
            "forward_gas_level": intent.metadata.get("forward_gas_level", "medium"),
            "finality_preference": intent.metadata.get("transfer_speed", "standard"),
        }
        return self._post_executor(payload)

    def execute_or_resume(self, intent: PaymentIntent, *, transaction_hash: str | None = None) -> CCTPExecutionResult:
        executor_response: dict[str, Any] | None = None
        tx_hash = transaction_hash or str(intent.metadata.get("transaction_hash") or "")
        if not tx_hash:
            executor_response = self.start_transfer(intent)
            tx_hash = str(executor_response.get("transactionHash") or executor_response.get("txHash") or "")
            if tx_hash:
                intent.metadata["transaction_hash"] = tx_hash
            message_hash = executor_response.get("messageHash")
            if message_hash:
                intent.metadata["message_hash"] = str(message_hash)
        messages = self.get_messages(
            source_chain=intent.chain,
            transaction_hash=tx_hash or None,
            nonce=str(intent.metadata.get("nonce")) if intent.metadata.get("nonce") else None,
        )
        message_status = messages[0] if messages else None
        if message_status:
            if message_status.get("messageHash"):
                intent.metadata["message_hash"] = str(message_status["messageHash"])
            if message_status.get("status"):
                intent.metadata["message_status"] = str(message_status["status"])
            if message_status.get("attestation"):
                intent.metadata["attestation"] = str(message_status["attestation"])
            if message_status.get("nonce") or message_status.get("eventNonce"):
                intent.metadata["nonce"] = str(message_status.get("nonce") or message_status.get("eventNonce"))
            if message_status.get("forwardTxHash"):
                intent.metadata["forward_tx_hash"] = str(message_status["forwardTxHash"])
        return CCTPExecutionResult(
            executor_response=executor_response or {},
            message_status=message_status,
        )
