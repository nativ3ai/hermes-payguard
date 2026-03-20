from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml


@dataclass
class PolicyConfig:
    mode: str = "enforce"
    asset: str = "USDC"
    default_chain: str = "BASE-SEPOLIA"
    per_payment_limit_usdc: Decimal = Decimal("100")
    micro_auto_approve_limit_usdc: Decimal = Decimal("0.05")
    allowed_circle_recipients: list[str] = field(default_factory=list)
    allowed_x402_hosts: list[str] = field(default_factory=lambda: ["127.0.0.1", "localhost"])
    allow_unlisted_circle_recipients: bool = False
    allow_unlisted_x402_hosts: bool = False


@dataclass
class RuntimeConfig:
    state_dir: Path
    policy_path: Path
    policy: PolicyConfig
    circle_api_base_url: str
    circle_api_key: str | None
    circle_entity_secret_ciphertext: str | None
    circle_wallet_id: str | None
    circle_token_id: str | None
    circle_x_user_token: str | None
    x402_network: str
    x402_private_key: str | None
    http_timeout_seconds: float = 20.0


DEFAULT_POLICY_TEXT = """mode: enforce
asset: USDC
default_chain: BASE-SEPOLIA
per_payment_limit_usdc: 100
micro_auto_approve_limit_usdc: 0.05
allowed_circle_recipients: []
allowed_x402_hosts:
  - 127.0.0.1
  - localhost
allow_unlisted_circle_recipients: false
allow_unlisted_x402_hosts: false
"""


def _parse_decimal(data: dict[str, Any], key: str, default: str) -> Decimal:
    value = data.get(key, default)
    return Decimal(str(value))


def _normalize_yaml_address_list(values: list[Any]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        if isinstance(value, int):
            normalized.append(hex(value).lower())
        else:
            normalized.append(str(value).strip().lower())
    return normalized


def load_policy(policy_path: Path) -> PolicyConfig:
    if not policy_path.exists():
        return PolicyConfig()
    raw = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
    return PolicyConfig(
        mode=str(raw.get("mode", "enforce")),
        asset=str(raw.get("asset", "USDC")),
        default_chain=str(raw.get("default_chain", "BASE-SEPOLIA")),
        per_payment_limit_usdc=_parse_decimal(raw, "per_payment_limit_usdc", "100"),
        micro_auto_approve_limit_usdc=_parse_decimal(raw, "micro_auto_approve_limit_usdc", "0.05"),
        allowed_circle_recipients=_normalize_yaml_address_list(raw.get("allowed_circle_recipients", [])),
        allowed_x402_hosts=[str(x).lower() for x in raw.get("allowed_x402_hosts", ["127.0.0.1", "localhost"])],
        allow_unlisted_circle_recipients=bool(raw.get("allow_unlisted_circle_recipients", False)),
        allow_unlisted_x402_hosts=bool(raw.get("allow_unlisted_x402_hosts", False)),
    )


def load_config() -> RuntimeConfig:
    hermes_home = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser()
    state_dir = Path(os.environ.get("PAYGUARD_STATE_DIR", str(hermes_home / "payguard"))).expanduser()
    policy_path = Path(os.environ.get("PAYGUARD_POLICY_FILE", str(state_dir / "policy.yaml"))).expanduser()
    state_dir.mkdir(parents=True, exist_ok=True)
    policy = load_policy(policy_path)
    return RuntimeConfig(
        state_dir=state_dir,
        policy_path=policy_path,
        policy=policy,
        circle_api_base_url=os.environ.get("CIRCLE_API_BASE_URL", "https://api.circle.com").rstrip("/"),
        circle_api_key=os.environ.get("CIRCLE_API_KEY"),
        circle_entity_secret_ciphertext=os.environ.get("CIRCLE_ENTITY_SECRET_CIPHERTEXT"),
        circle_wallet_id=os.environ.get("CIRCLE_WALLET_ID"),
        circle_token_id=os.environ.get("CIRCLE_TOKEN_ID"),
        circle_x_user_token=os.environ.get("CIRCLE_X_USER_TOKEN"),
        x402_network=os.environ.get("PAYGUARD_X402_NETWORK", "eip155:84532"),
        x402_private_key=os.environ.get("PAYGUARD_EVM_PRIVATE_KEY"),
        http_timeout_seconds=float(os.environ.get("PAYGUARD_HTTP_TIMEOUT_SECONDS", "20")),
    )
