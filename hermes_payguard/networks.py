from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NetworkProfile:
    name: str
    default_chain: str
    x402_network: str
    circle_api_base_url: str
    circle_cctp_api_base_url: str


NETWORK_PROFILES = {
    "mainnet": NetworkProfile(
        name="mainnet",
        default_chain="BASE",
        x402_network="eip155:8453",
        circle_api_base_url="https://api.circle.com",
        circle_cctp_api_base_url="https://iris-api.circle.com",
    ),
    "testnet": NetworkProfile(
        name="testnet",
        default_chain="BASE-SEPOLIA",
        x402_network="eip155:84532",
        circle_api_base_url="https://api-sandbox.circle.com",
        circle_cctp_api_base_url="https://iris-api-sandbox.circle.com",
    ),
}


CCTP_DOMAIN_BY_CHAIN = {
    "ETHEREUM": 0,
    "ETHEREUM-SEPOLIA": 0,
    "AVALANCHE": 1,
    "AVALANCHE-FUJI": 1,
    "OP": 2,
    "OPTIMISM": 2,
    "OP-SEPOLIA": 2,
    "ARBITRUM": 3,
    "ARBITRUM-SEPOLIA": 3,
    "NOBLE": 4,
    "SOLANA": 5,
    "SOLANA-DEVNET": 5,
    "BASE": 6,
    "BASE-SEPOLIA": 6,
    "POLYGON-POS": 7,
    "POLYGON-AMOY": 7,
    "SUI": 8,
    "APTOS": 9,
    "UNICHAIN": 10,
    "WORLD_CHAIN": 14,
    "LINEA": 11,
    "SONIC": 13,
}


def get_network_profile(name: str | None) -> NetworkProfile:
    key = (name or "mainnet").strip().lower()
    return NETWORK_PROFILES.get(key, NETWORK_PROFILES["mainnet"])


def normalize_chain_name(name: str) -> str:
    return name.strip().upper().replace(" ", "-")


def resolve_cctp_domain(chain_name: str) -> int:
    normalized = normalize_chain_name(chain_name)
    if normalized not in CCTP_DOMAIN_BY_CHAIN:
        raise ValueError(f"Unsupported CCTP chain: {chain_name}")
    return CCTP_DOMAIN_BY_CHAIN[normalized]
