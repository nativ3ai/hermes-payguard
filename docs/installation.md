# Installation

## Goal

Install Hermes PayGuard as an optional plugin without modifying Hermes core.

## Prerequisites

- Python 3.11+
- Hermes Agent already installed
- a writable Hermes home directory, usually `~/.hermes`

## Option 1: Repo plugin install

Clone the repository, install the package, and symlink it into Hermes' plugin directory.

```bash
git clone https://github.com/nativ3ai/hermes-payguard.git
cd hermes-payguard
pip install -e .
payguard install-plugin
```

That creates:

- `~/.hermes/plugins/hermes-payguard -> /path/to/hermes-payguard`

## Option 2: Manual symlink

```bash
git clone https://github.com/nativ3ai/hermes-payguard.git
pip install -e /path/to/hermes-payguard
mkdir -p ~/.hermes/plugins
ln -sfn /path/to/hermes-payguard ~/.hermes/plugins/hermes-payguard
```

## Verify

```bash
payguard doctor
hermes
/plugins
```

Expected:

- `payguard doctor` shows the resolved state directory and profile
- Hermes lists `hermes-payguard` as an enabled plugin

## Default profile behavior

Without any override, PayGuard boots in `mainnet` profile:

- `default_chain=BASE`
- `CIRCLE_API_BASE_URL=https://api.circle.com`
- `CIRCLE_CCTP_API_BASE_URL=https://iris-api.circle.com`
- `PAYGUARD_X402_NETWORK=eip155:8453`

To switch to testnet defaults:

```bash
export PAYGUARD_ENV=testnet
```

That changes the implicit defaults to:

- `default_chain=BASE-SEPOLIA`
- `CIRCLE_API_BASE_URL=https://api-sandbox.circle.com`
- `CIRCLE_CCTP_API_BASE_URL=https://iris-api-sandbox.circle.com`
- `PAYGUARD_X402_NETWORK=eip155:84532`

## Policy bootstrap

Generate a starting policy file:

```bash
payguard init-policy
```

That writes:

- `~/.hermes/payguard/policy.yaml`

## Environment variables

### Shared

```bash
export PAYGUARD_ENV=mainnet
export PAYGUARD_HTTP_TIMEOUT_SECONDS=20
```

### Circle developer-controlled transfers

```bash
export CIRCLE_API_KEY="..."
export CIRCLE_ENTITY_SECRET_CIPHERTEXT="..."
export CIRCLE_WALLET_ID="..."
export CIRCLE_TOKEN_ID="..."
```

### Circle user-controlled transfers

```bash
export CIRCLE_API_KEY="..."
export CIRCLE_X_USER_TOKEN="..."
export CIRCLE_WALLET_ID="..."
export CIRCLE_TOKEN_ID="..."
```

### Circle CCTP

```bash
export CCTP_EXECUTOR_URL="https://your-burn-executor.internal/execute-cctp"
```

### x402 buyer

```bash
export PAYGUARD_EVM_PRIVATE_KEY="0x..."
export PAYGUARD_X402_NETWORK="eip155:8453"
```
