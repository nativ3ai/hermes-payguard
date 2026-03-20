from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from .networks import get_network_profile


@dataclass
class PolicyConfig:
    mode: str = "enforce"
    network_profile: str = "mainnet"
    asset: str = "USDC"
    default_chain: str = "BASE"
    per_payment_limit_usdc: Decimal = Decimal("100")
    micro_auto_approve_limit_usdc: Decimal = Decimal("0.05")
    allowed_circle_recipients: list[str] = field(default_factory=list)
    allowed_cctp_destination_chains: list[str] = field(default_factory=list)
    allowed_x402_hosts: list[str] = field(default_factory=lambda: ["127.0.0.1", "localhost"])
    allow_unlisted_circle_recipients: bool = False
    allow_unlisted_cctp_destinations: bool = True
    allow_unlisted_x402_hosts: bool = False


@dataclass
class RuntimeConfig:
    state_dir: Path
    policy_path: Path
    policy: PolicyConfig
    network_profile: str
    circle_api_base_url: str
    circle_cctp_api_base_url: str
    circle_api_key: str | None
    circle_entity_secret_ciphertext: str | None
    circle_wallet_id: str | None
    circle_token_id: str | None
    circle_x_user_token: str | None
    cctp_executor_url: str | None
    x402_network: str
    x402_private_key: str | None
    http_timeout_seconds: float = 20.0


DEFAULT_POLICY_TEXT = """mode: enforce
network_profile: mainnet
asset: USDC
default_chain: BASE
per_payment_limit_usdc: 100
micro_auto_approve_limit_usdc: 0.05
allowed_circle_recipients: []
allowed_cctp_destination_chains: []
allowed_x402_hosts:
  - 127.0.0.1
  - localhost
allow_unlisted_circle_recipients: false
allow_unlisted_cctp_destinations: true
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


def load_policy(policy_path: Path, default_profile_name: str = "mainnet") -> PolicyConfig:
    profile = get_network_profile(default_profile_name)
    if not policy_path.exists():
        return PolicyConfig(network_profile=profile.name, default_chain=profile.default_chain)
    raw = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
    return PolicyConfig(
        mode=str(raw.get("mode", "enforce")),
        network_profile=str(raw.get("network_profile", profile.name)).strip().lower(),
        asset=str(raw.get("asset", "USDC")),
        default_chain=str(raw.get("default_chain", profile.default_chain)),
        per_payment_limit_usdc=_parse_decimal(raw, "per_payment_limit_usdc", "100"),
        micro_auto_approve_limit_usdc=_parse_decimal(raw, "micro_auto_approve_limit_usdc", "0.05"),
        allowed_circle_recipients=_normalize_yaml_address_list(raw.get("allowed_circle_recipients", [])),
        allowed_cctp_destination_chains=[str(x).strip().upper().replace(" ", "-") for x in raw.get("allowed_cctp_destination_chains", [])],
        allowed_x402_hosts=[str(x).lower() for x in raw.get("allowed_x402_hosts", ["127.0.0.1", "localhost"])],
        allow_unlisted_circle_recipients=bool(raw.get("allow_unlisted_circle_recipients", False)),
        allow_unlisted_cctp_destinations=bool(raw.get("allow_unlisted_cctp_destinations", True)),
        allow_unlisted_x402_hosts=bool(raw.get("allow_unlisted_x402_hosts", False)),
    )


def load_config() -> RuntimeConfig:
    hermes_home = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser()
    state_dir = Path(os.environ.get("PAYGUARD_STATE_DIR", str(hermes_home / "payguard"))).expanduser()
    policy_path = Path(os.environ.get("PAYGUARD_POLICY_FILE", str(state_dir / "policy.yaml"))).expanduser()
    state_dir.mkdir(parents=True, exist_ok=True)
    selected_profile_name = os.environ.get("PAYGUARD_ENV", "mainnet").strip().lower()
    selected_profile = get_network_profile(selected_profile_name)
    policy = load_policy(policy_path, default_profile_name=selected_profile.name)
    active_profile = get_network_profile(policy.network_profile or selected_profile.name)
    return RuntimeConfig(
        state_dir=state_dir,
        policy_path=policy_path,
        policy=policy,
        network_profile=active_profile.name,
        circle_api_base_url=os.environ.get("CIRCLE_API_BASE_URL", active_profile.circle_api_base_url).rstrip("/"),
        circle_cctp_api_base_url=os.environ.get("CIRCLE_CCTP_API_BASE_URL", active_profile.circle_cctp_api_base_url).rstrip("/"),
        circle_api_key=os.environ.get("CIRCLE_API_KEY"),
        circle_entity_secret_ciphertext=os.environ.get("CIRCLE_ENTITY_SECRET_CIPHERTEXT"),
        circle_wallet_id=os.environ.get("CIRCLE_WALLET_ID"),
        circle_token_id=os.environ.get("CIRCLE_TOKEN_ID"),
        circle_x_user_token=os.environ.get("CIRCLE_X_USER_TOKEN"),
        cctp_executor_url=os.environ.get("CCTP_EXECUTOR_URL"),
        x402_network=os.environ.get("PAYGUARD_X402_NETWORK", active_profile.x402_network),
        x402_private_key=os.environ.get("PAYGUARD_EVM_PRIVATE_KEY"),
        http_timeout_seconds=float(os.environ.get("PAYGUARD_HTTP_TIMEOUT_SECONDS", "20")),
    )
