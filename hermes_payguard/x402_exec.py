from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx
from eth_account import Account
from x402 import PaymentRequired, x402ClientSync
from x402.http.x402_http_client import x402HTTPClientSync
from x402.mechanisms.evm.exact import register_exact_evm_client

from .config import RuntimeConfig
from .policy import X402Quote


class X402ConfigError(RuntimeError):
    pass


@dataclass
class X402ProbeResult:
    status_code: int
    headers: dict[str, str]
    body: bytes
    payment_required: PaymentRequired | None
    quote: X402Quote | None


@dataclass
class X402FetchResult:
    status_code: int
    headers: dict[str, str]
    body_text: str
    paid: bool
    payment_headers: dict[str, str] | None = None
    quote: X402Quote | None = None


class X402Executor:
    def __init__(self, config: RuntimeConfig):
        self.config = config
        if not config.x402_private_key:
            raise X402ConfigError("PAYGUARD_EVM_PRIVATE_KEY is required for x402 buyer flows")
        self._wallet = Account.from_key(config.x402_private_key)
        self._client = x402ClientSync()
        register_exact_evm_client(self._client, self._wallet, networks=config.x402_network)
        self._http_client = x402HTTPClientSync(self._client)

    @staticmethod
    def _usdc_from_smallest_units(value: str, decimals: int = 6) -> Decimal:
        scale = Decimal(10) ** decimals
        return Decimal(value) / scale

    def _build_quote(self, payment_required: PaymentRequired) -> X402Quote:
        req = payment_required.accepts[0]
        decimals = 6
        if req.extra and str(req.extra.get("decimals", "")).isdigit():
            decimals = int(req.extra["decimals"])
        amount_usdc = self._usdc_from_smallest_units(req.amount, decimals=decimals)
        return X402Quote(
            amount_usdc=amount_usdc,
            host=payment_required.resource.url if payment_required.resource else "",
            network=req.network,
            asset=req.asset,
            pay_to=req.pay_to,
        )

    def probe(self, url: str, method: str = "GET", headers: dict[str, str] | None = None) -> X402ProbeResult:
        with httpx.Client(timeout=self.config.http_timeout_seconds, follow_redirects=True) as client:
            response = client.request(method, url, headers=headers)
        payment_required = None
        quote = None
        if response.status_code == 402:
            get_header, body_data = self._http_client._handle_402_common(dict(response.headers), response.content)
            payment_required = self._http_client.get_payment_required_response(get_header, body_data)
            if isinstance(payment_required, PaymentRequired):
                quote = self._build_quote(payment_required)
        return X402ProbeResult(
            status_code=response.status_code,
            headers=dict(response.headers),
            body=response.content,
            payment_required=payment_required,
            quote=quote,
        )

    def fetch(self, url: str, method: str = "GET", headers: dict[str, str] | None = None) -> X402FetchResult:
        probe = self.probe(url, method=method, headers=headers)
        if probe.status_code != 402 or probe.payment_required is None:
            return X402FetchResult(
                status_code=probe.status_code,
                headers=probe.headers,
                body_text=probe.body.decode("utf-8", "ignore"),
                paid=False,
                quote=probe.quote,
            )
        payment_headers, _ = self._http_client.handle_402_response(probe.headers, probe.body)
        merged_headers = dict(headers or {})
        merged_headers.update(payment_headers)
        with httpx.Client(timeout=self.config.http_timeout_seconds, follow_redirects=True) as client:
            response = client.request(method, url, headers=merged_headers)
        return X402FetchResult(
            status_code=response.status_code,
            headers=dict(response.headers),
            body_text=response.text,
            paid=True,
            payment_headers=payment_headers,
            quote=probe.quote,
        )
