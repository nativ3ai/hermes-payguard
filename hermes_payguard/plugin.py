from __future__ import annotations

from .tools import (
    TOOLSET,
    check_payguard_available,
    execute_payment_intent,
    fetch_paid_url,
    get_payment_intent,
    list_payment_intents,
    prepare_cctp_transfer,
    prepare_usdc_transfer,
)


def register(ctx) -> None:
    ctx.register_tool(
        name="payguard_prepare_usdc_transfer",
        toolset=TOOLSET,
        schema={
            "name": "payguard_prepare_usdc_transfer",
            "description": "Prepare a safe-by-design USDC transfer intent. Circle transfers are staged first and require a separate operator approval stamp before execution.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount_usdc": {"type": "number", "description": "USDC amount in decimal format."},
                    "recipient": {"type": "string", "description": "Destination wallet address."},
                    "rail": {"type": "string", "enum": ["circle_dev", "circle_user"], "description": "Payment rail."},
                    "chain": {"type": "string", "description": "Circle blockchain, e.g. BASE-SEPOLIA or BASE."},
                    "reason": {"type": "string", "description": "Human-readable purpose for the transfer."},
                    "source_wallet_id": {"type": "string", "description": "Optional Circle source wallet ID override."},
                    "token_id": {"type": "string", "description": "Optional Circle token ID override."},
                    "metadata": {"type": "object", "description": "Optional structured metadata to store with the intent."}
                },
                "required": ["amount_usdc", "recipient"],
                "additionalProperties": False,
            },
        },
        handler=prepare_usdc_transfer,
        check_fn=check_payguard_available,
        is_async=False,
        description="Prepare a USDC transfer intent with policy checks.",
        emoji="💸",
    )
    ctx.register_tool(
        name="payguard_prepare_cctp_transfer",
        toolset=TOOLSET,
        schema={
            "name": "payguard_prepare_cctp_transfer",
            "description": "Prepare a cross-chain USDC transfer over Circle CCTP. This stages the route, fee quote, and approval requirements before any burn/mint execution.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount_usdc": {"type": "number", "description": "USDC amount in decimal format."},
                    "recipient": {"type": "string", "description": "Destination wallet address on the destination chain."},
                    "destination_chain": {"type": "string", "description": "Destination chain, e.g. ARBITRUM, ETHEREUM, BASE, BASE-SEPOLIA."},
                    "source_chain": {"type": "string", "description": "Source chain. Defaults to the configured profile chain."},
                    "reason": {"type": "string", "description": "Human-readable purpose for the transfer."},
                    "transfer_speed": {"type": "string", "enum": ["standard", "fast"], "description": "CCTP finality preference. Standard is cheaper; fast prefers lower finality thresholds.", "default": "standard"},
                    "use_forwarder": {"type": "boolean", "description": "Whether to include forwarding-service gas fees in the quote.", "default": False},
                    "forward_gas_level": {"type": "string", "enum": ["low", "medium", "high"], "description": "Forwarding-service gas tier if use_forwarder is true.", "default": "medium"},
                    "metadata": {"type": "object", "description": "Optional structured metadata to store with the intent."}
                },
                "required": ["amount_usdc", "recipient", "destination_chain"],
                "additionalProperties": False,
            },
        },
        handler=prepare_cctp_transfer,
        check_fn=check_payguard_available,
        is_async=False,
        description="Prepare a CCTP cross-chain transfer intent with route and fee checks.",
        emoji="🌉",
    )
    ctx.register_tool(
        name="payguard_execute_payment_intent",
        toolset=TOOLSET,
        schema={
            "name": "payguard_execute_payment_intent",
            "description": "Execute a previously prepared payment intent if policy and operator approval allow it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "intent_id": {"type": "string", "description": "Prepared intent ID."},
                    "transaction_hash": {"type": "string", "description": "Optional source-chain transaction hash for resuming a previously started CCTP burn."}
                },
                "required": ["intent_id"],
                "additionalProperties": False,
            },
        },
        handler=execute_payment_intent,
        check_fn=check_payguard_available,
        is_async=False,
        description="Execute an approved payment intent.",
        emoji="✅",
    )
    ctx.register_tool(
        name="payguard_get_payment_intent",
        toolset=TOOLSET,
        schema={
            "name": "payguard_get_payment_intent",
            "description": "Fetch a payment intent and its approval state.",
            "parameters": {
                "type": "object",
                "properties": {"intent_id": {"type": "string"}},
                "required": ["intent_id"],
                "additionalProperties": False,
            },
        },
        handler=get_payment_intent,
        check_fn=check_payguard_available,
        is_async=False,
        description="Inspect a payment intent.",
        emoji="🧾",
    )
    ctx.register_tool(
        name="payguard_list_payment_intents",
        toolset=TOOLSET,
        schema={
            "name": "payguard_list_payment_intents",
            "description": "List recent payment intents from the local PayGuard ledger.",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}},
                "additionalProperties": False,
            },
        },
        handler=list_payment_intents,
        check_fn=check_payguard_available,
        is_async=False,
        description="List payment intents.",
        emoji="📚",
    )
    ctx.register_tool(
        name="payguard_fetch_paid_url",
        toolset=TOOLSET,
        schema={
            "name": "payguard_fetch_paid_url",
            "description": "Fetch an x402-protected URL. Tiny micropayments can auto-execute below the configured threshold; larger ones become approval-gated intents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Paid HTTP resource URL."},
                    "reason": {"type": "string", "description": "Why the paid resource is needed."},
                    "allow_auto_execute": {"type": "boolean", "description": "Whether to auto-pay when the price is below the configured micropayment threshold.", "default": True}
                },
                "required": ["url"],
                "additionalProperties": False,
            },
        },
        handler=fetch_paid_url,
        check_fn=check_payguard_available,
        is_async=False,
        description="Fetch an x402 paid resource with policy checks.",
        emoji="🌐",
    )
