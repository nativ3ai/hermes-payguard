# CCTP Executor Boundary

## Why this exists

PayGuard can quote, stage, approve, and track CCTP transfers, but it intentionally does not embed a source-chain hot signer into the Hermes plugin itself.

That would collapse the trust boundary.

Instead, PayGuard delegates the actual source-chain burn submission to:

- `CCTP_EXECUTOR_URL`

## What the executor should do

The executor is a separate service that:

1. accepts an approved CCTP transfer request
2. submits the source-chain burn / deposit-for-burn transaction
3. returns a source-chain `transactionHash`
4. optionally returns `messageHash`, `nonce`, or other route metadata

PayGuard then uses Circle's CCTP API to:

- query messages by source domain
- persist status
- persist attestation when available

## Current payload shape

PayGuard sends JSON like:

```json
{
  "intent_id": "uuid",
  "amount_usdc": "50",
  "asset": "USDC",
  "recipient": "0xabc...",
  "source_chain": "BASE",
  "destination_chain": "ARBITRUM",
  "reason": "treasury rebalance",
  "quote": {
    "amount_usdc": "50",
    "estimated_fee_usdc": "0.005",
    "source_chain": "BASE",
    "destination_chain": "ARBITRUM",
    "source_domain": 6,
    "destination_domain": 3,
    "selected_finality_threshold": 2000,
    "forward_fee_usdc": "0",
    "minimum_fee_bps": 1,
    "use_forwarder": false
  },
  "forward": false,
  "forward_gas_level": "medium",
  "finality_preference": "standard"
}
```

## Minimum response shape

The executor should return:

```json
{
  "transactionHash": "0x..."
}
```

Optional:

```json
{
  "transactionHash": "0x...",
  "messageHash": "0x...",
  "nonce": "42",
  "executorStatus": "submitted"
}
```

## Recommended deployment model

- private internal service
- auth in front of the executor
- wallet isolation from the Hermes host
- dedicated signer or MPC flow
- structured logs

## What PayGuard does after executor response

1. store `transactionHash`
2. query Circle CCTP message API for the source domain
3. persist:
   - `messageHash`
   - `status`
   - `attestation`
   - `nonce`
   - `forwardTxHash` when present
4. mark the intent:
   - `attestation_pending` if attestation is not ready
   - `executed` once attestation is present
