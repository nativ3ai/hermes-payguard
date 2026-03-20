# Hermes PayGuard

Hermes PayGuard is a standalone Hermes plugin for safe-by-design USDC and x402 payments.

It does not patch Hermes core. It installs as an add-on and gives Hermes payment tools with an explicit operator boundary:

- Hermes can prepare payment intents.
- Hermes can inspect payment status.
- Hermes can execute only if policy allows it.
- Larger transfers require a separate human approval stamp via `payguard approve <intent-id>`.
- Tiny x402 micropayments can auto-run below a configured threshold.

## What it supports

- Circle developer-controlled USDC transfers
- Circle user-controlled transfer challenges
- x402 paid HTTP fetches, including micropayments and nanopayments
- Local audit ledger and replayable intent state

## Security model

PayGuard follows the same trust-boundary philosophy as CaMeL Guard, but adapted to payments.

- Trusted control: operator-approved payment intent, local policy, explicit approval stamps
- Untrusted data: webpages, invoices, PDFs, chat text, scraped addresses, model proposals
- Gated execution: payment tools re-check policy and approval state before moving money

The key implementation detail is that approval is external to the model loop. Hermes can stage payment intents, but a separate operator command creates the approval stamp:

```bash
payguard approve <intent-id>
```

That avoids the weakest version of “agent-approved its own payment.”

## Install

### Repo plugin mode

Clone the repo and symlink it into Hermes' plugin directory:

```bash
git clone https://github.com/nativ3ai/hermes-payguard.git
mkdir -p ~/.hermes/plugins
ln -sfn /path/to/hermes-payguard ~/.hermes/plugins/hermes-payguard
pip install -e /path/to/hermes-payguard
```

### Pip plugin mode

```bash
pip install hermes-payguard
```

## Configure

Create `~/.hermes/payguard/policy.yaml`:

```yaml
mode: enforce
asset: USDC
default_chain: BASE-SEPOLIA
per_payment_limit_usdc: 100
micro_auto_approve_limit_usdc: 0.05
allowed_circle_recipients:
  - 0x1111111111111111111111111111111111111111
allowed_x402_hosts:
  - 127.0.0.1
  - localhost
```

Then set the relevant env vars.

### Circle developer-controlled

```bash
export CIRCLE_API_KEY="..."
export CIRCLE_ENTITY_SECRET_CIPHERTEXT="..."
export CIRCLE_WALLET_ID="..."
export CIRCLE_TOKEN_ID="..."
```

### Circle user-controlled

```bash
export CIRCLE_API_KEY="..."
export CIRCLE_X_USER_TOKEN="..."
```

### x402 buyer

```bash
export PAYGUARD_EVM_PRIVATE_KEY="0x..."
export PAYGUARD_X402_NETWORK="eip155:84532"
```

## Operator flow

1. Hermes prepares a transfer with `payguard_prepare_usdc_transfer`.
2. The tool writes a pending intent into the local ledger.
3. If approval is required, Hermes tells you to run:

```bash
payguard approve <intent-id>
```

4. Hermes then calls `payguard_execute_payment_intent`.

For tiny x402 payments below the configured threshold, `payguard_fetch_paid_url` can auto-pay without a separate approval stamp.

## Hermes examples

Natural prompts Hermes can handle once the plugin is installed:

```text
Prepare a 12.5 USDC transfer to 0xabc... on Circle developer-controlled wallets for vendor invoice March-20.
```

```text
Fetch the paid x402 URL https://example.com/premium if the micropayment is below policy limits.
```

## Test coverage

Verified locally:

- Circle developer-controlled transfer intent -> CLI approval -> execution
- Circle user-controlled transfer intent -> CLI approval -> challenge creation
- x402 micropayment auto-pay flow
- x402 over-limit intent -> CLI approval -> paid fetch
- Hermes plugin discovery and tool registration

Detailed notes:

- [`docs/architecture.md`](docs/architecture.md)

## Tool summary

- `payguard_prepare_usdc_transfer`
- `payguard_execute_payment_intent`
- `payguard_get_payment_intent`
- `payguard_list_payment_intents`
- `payguard_fetch_paid_url`

## Tests

```bash
pip install -e .[test]
pytest -q
```

The test suite includes:

- Circle developer-controlled mock transfer flow
- Circle user-controlled challenge flow
- x402 paid fetch flow with auto-approved micropayments
- x402 over-limit flow with explicit operator approval
- Hermes plugin discovery and tool registration
