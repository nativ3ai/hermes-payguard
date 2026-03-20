# Operator Guide

## Core model

PayGuard keeps money movement out of the model's direct control.

The workflow is always:

1. Hermes prepares an intent
2. PayGuard writes the intent to the local ledger
3. the operator approves it externally if required
4. Hermes executes it only if the approval stamp and policy still allow it

## Local state

By default:

- policy: `~/.hermes/payguard/policy.yaml`
- intents: `~/.hermes/payguard/intents/*.json`
- approvals: `~/.hermes/payguard/approvals/*.json`
- audit log: `~/.hermes/payguard/audit.jsonl`

## Commands

### Check environment

```bash
payguard doctor
```

### Create starter policy

```bash
payguard init-policy
```

### Approve a staged payment

```bash
payguard approve <intent-id>
```

Optional:

```bash
payguard approve <intent-id> --ttl-seconds 1800 --actor alice
```

### Revoke approval

```bash
payguard revoke <intent-id>
```

### Inspect intent state

```bash
payguard show <intent-id>
```

## Hermes usage

### Same-chain Circle transfer

```text
Prepare a 12.5 USDC transfer to 0xabc... on Circle developer-controlled wallets for vendor invoice March-20.
```

Then approve:

```bash
payguard approve <intent-id>
```

Then Hermes can execute the prepared intent.

### User-controlled Circle transfer

```text
Prepare a 5 USDC user-controlled transfer to 0xabc... for a payout.
```

Execution returns a `challengeId` from Circle's user-controlled flow.

### CCTP cross-chain transfer

```text
Prepare a 50 USDC CCTP transfer from BASE to ARBITRUM for 0xabc..., use standard finality, and stage it for approval.
```

This does not immediately move money. It stages:

- source chain
- destination chain
- fee quote
- forwarder flag
- finality preference

After approval, execution calls the configured CCTP executor and then tracks message/attestation state through Circle's CCTP API.

### x402 paid fetch

```text
Fetch the paid x402 URL https://example.com/premium if the micropayment is below policy limits.
```

Behavior:

- if free: returns immediately
- if paid and under micropayment threshold: auto-pays
- if paid and above threshold: creates an approval-gated intent

## Policy suggestions

### Conservative production

- `allow_unlisted_circle_recipients: false`
- `allow_unlisted_cctp_destinations: false`
- `micro_auto_approve_limit_usdc: 0.01`
- explicit `allowed_circle_recipients`
- explicit `allowed_cctp_destination_chains`

### Fast internal ops

- `allow_unlisted_cctp_destinations: true`
- `micro_auto_approve_limit_usdc: 0.05`
- destination allowlists still recommended

## Failure modes

### Intent rejected

Common reasons:

- recipient not allowlisted
- destination chain not allowlisted
- amount exceeds configured limit
- unsupported asset or chain

### Intent approved but execution fails

Check:

- `payguard show <intent-id>`
- `~/.hermes/payguard/audit.jsonl`
- missing env vars
- Circle API key/wallet/token config
- `CCTP_EXECUTOR_URL`

### x402 fetch did not auto-pay

Likely reasons:

- host not allowlisted
- quote exceeds auto-pay threshold
- missing EVM key

## Recommended operational stance

- keep real transfers approval-gated
- use auto-pay only for tiny x402 amounts
- keep the burn signer for CCTP behind a dedicated executor
- treat the local audit ledger as part of the control boundary
