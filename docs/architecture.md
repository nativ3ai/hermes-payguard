# Architecture

## Goal

Provide Hermes with payment capabilities without giving the model direct, unreviewed authority to move money.

## Design

Hermes PayGuard uses a separate payment state machine:

1. `prepare`
   - validate recipient, asset, amount, host, and thresholds against local policy
   - write a pending intent into the local ledger
2. `approve`
   - operator runs `payguard approve <intent-id>` outside the model loop
   - approval stamp is local, time-bound, and auditable
3. `execute`
   - re-evaluate policy
   - confirm approval stamp if required
   - execute the chosen rail

## Rails

### Circle developer-controlled

Use for treasury or platform-controlled USDC transfers.

- prepare transfer intent
- require explicit operator approval
- execute against Circle developer-controlled transfer endpoint

### Circle user-controlled

Use when the end user should approve the transfer in Circle's challenge/UI flow.

- prepare transfer intent
- require explicit operator approval
- create Circle user-controlled transfer challenge
- return `challengeId`

### x402

Use for paid HTTP resources and micropayments.

- probe resource
- if free, return immediately
- if paid, parse payment requirements
- auto-pay only if under configured micropayment threshold
- otherwise stage an approval-gated intent

## Why approval is external

Hermes plugins can register tools and hooks, but plugin hooks are observational. They do not intercept model intent at the same trust boundary as CaMeL Guard in Hermes core.

Because of that, PayGuard does not rely on the model to self-confirm payment execution. The approval stamp is created by a separate CLI command outside the model loop.

## Local state

By default, state lives under `~/.hermes/payguard/`:

- `policy.yaml`
- `intents/*.json`
- `approvals/*.json`
- `audit.jsonl`

## Test scope

The automated suite covers:

- Circle developer-controlled transfer flow using a local mock of the documented endpoint
- Circle user-controlled challenge flow using a local mock of the documented endpoint
- x402-compatible paid fetch flow using a local resource server that emits a real `PAYMENT-REQUIRED` header and accepts a retried signed request
- Hermes plugin discovery/registration

The x402 client path uses the real `x402` Python package and real EVM signing logic. The Circle flows use local mocks so the suite stays deterministic and does not require live funds.
