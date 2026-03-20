from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urlparse

from .config import PolicyConfig
from .models import PaymentIntent, PolicyDecision
from .networks import normalize_chain_name


USDC_DECIMALS = Decimal("1000000")


def _normalize_address(value: str) -> str:
    return value.strip().lower()


def _host_allowed(host: str, allowed: list[str], allow_unlisted: bool) -> bool:
    host = host.lower().strip()
    if allow_unlisted:
        return True
    return host in allowed or any(host.endswith(f".{suffix}") for suffix in allowed if not suffix.startswith("127."))


@dataclass
class X402Quote:
    amount_usdc: Decimal
    host: str
    network: str
    asset: str
    pay_to: str


@dataclass
class CCTPQuote:
    amount_usdc: Decimal
    estimated_fee_usdc: Decimal
    source_chain: str
    destination_chain: str
    source_domain: int
    destination_domain: int
    selected_finality_threshold: int
    forward_fee_usdc: Decimal
    minimum_fee_bps: int
    use_forwarder: bool


def evaluate_usdc_transfer(intent: PaymentIntent, policy: PolicyConfig) -> PolicyDecision:
    amount = Decimal(intent.amount_usdc)
    recipient = _normalize_address(intent.recipient)
    if intent.asset.upper() != policy.asset.upper():
        return PolicyDecision(False, True, False, f"asset must be {policy.asset}")
    if amount <= 0:
        return PolicyDecision(False, True, False, "amount must be positive")
    if amount > policy.per_payment_limit_usdc:
        return PolicyDecision(False, True, False, f"amount exceeds per-payment limit {policy.per_payment_limit_usdc}")
    if not policy.allow_unlisted_circle_recipients and recipient not in policy.allowed_circle_recipients:
        return PolicyDecision(False, True, False, "recipient not in allowed Circle recipient list")
    return PolicyDecision(True, True, False, "circle transfers require explicit operator approval", {
        "recipient": recipient,
        "amount_usdc": str(amount),
    })


def evaluate_x402_quote(url: str, quote: X402Quote, policy: PolicyConfig) -> PolicyDecision:
    if quote.amount_usdc <= 0:
        return PolicyDecision(False, True, False, "x402 amount must be positive")
    if quote.amount_usdc > policy.per_payment_limit_usdc:
        return PolicyDecision(False, True, False, f"x402 amount exceeds per-payment limit {policy.per_payment_limit_usdc}")
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not _host_allowed(host, policy.allowed_x402_hosts, policy.allow_unlisted_x402_hosts):
        return PolicyDecision(False, True, False, "x402 host not in allowed host list")
    auto = quote.amount_usdc <= policy.micro_auto_approve_limit_usdc
    return PolicyDecision(True, not auto, auto, "x402 quote accepted" if auto else "x402 quote requires operator approval", {
        "host": host,
        "amount_usdc": str(quote.amount_usdc),
        "network": quote.network,
        "pay_to": quote.pay_to,
        "asset": quote.asset,
    })


def evaluate_cctp_transfer(intent: PaymentIntent, quote: CCTPQuote, policy: PolicyConfig) -> PolicyDecision:
    amount = Decimal(intent.amount_usdc)
    recipient = _normalize_address(intent.recipient)
    dest_chain = normalize_chain_name(quote.destination_chain)
    if intent.asset.upper() != policy.asset.upper():
        return PolicyDecision(False, True, False, f"asset must be {policy.asset}")
    if amount <= 0:
        return PolicyDecision(False, True, False, "amount must be positive")
    if quote.estimated_fee_usdc < 0:
        return PolicyDecision(False, True, False, "cctp fee quote is invalid")
    if amount + quote.estimated_fee_usdc > policy.per_payment_limit_usdc:
        return PolicyDecision(False, True, False, f"amount plus cctp fee exceeds per-payment limit {policy.per_payment_limit_usdc}")
    if not policy.allow_unlisted_circle_recipients and recipient not in policy.allowed_circle_recipients:
        return PolicyDecision(False, True, False, "recipient not in allowed Circle recipient list")
    if not policy.allow_unlisted_cctp_destinations and dest_chain not in policy.allowed_cctp_destination_chains:
        return PolicyDecision(False, True, False, "destination chain not in allowed CCTP destination list")
    return PolicyDecision(True, True, False, "cctp transfers require explicit operator approval", {
        "recipient": recipient,
        "amount_usdc": str(amount),
        "estimated_fee_usdc": str(quote.estimated_fee_usdc),
        "source_chain": quote.source_chain,
        "destination_chain": quote.destination_chain,
        "source_domain": quote.source_domain,
        "destination_domain": quote.destination_domain,
        "selected_finality_threshold": quote.selected_finality_threshold,
        "forward_fee_usdc": str(quote.forward_fee_usdc),
        "minimum_fee_bps": quote.minimum_fee_bps,
        "use_forwarder": quote.use_forwarder,
    })
