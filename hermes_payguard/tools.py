from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any

from .circle import CircleClient
from .config import RuntimeConfig, load_config
from .ledger import IntentLedger
from .models import IntentKind, IntentStatus, PaymentIntent, PaymentRail
from .policy import evaluate_usdc_transfer, evaluate_x402_quote
from .x402_exec import X402Executor


TOOLSET = "payments_payguard"


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


def _services() -> tuple[RuntimeConfig, IntentLedger]:
    config = load_config()
    return config, IntentLedger(config.state_dir)


def _intent_summary(intent: PaymentIntent) -> dict[str, Any]:
    data = intent.to_dict()
    data["approval_command"] = f"payguard approve {intent.id}"
    return data


def check_payguard_available() -> bool:
    return True


def prepare_usdc_transfer(args: dict[str, Any], **_: Any) -> str:
    config, ledger = _services()
    rail = PaymentRail(args.get("rail", PaymentRail.CIRCLE_DEV.value))
    intent = PaymentIntent(
        id=str(uuid.uuid4()),
        kind=IntentKind.USDC_TRANSFER,
        rail=rail,
        asset=str(args.get("asset", "USDC")),
        amount_usdc=str(args["amount_usdc"]),
        recipient=str(args["recipient"]),
        chain=str(args.get("chain", config.policy.default_chain)),
        reason=str(args.get("reason", "")),
        metadata=args.get("metadata") or {},
        source_wallet_id=args.get("source_wallet_id"),
        source_wallet_address=args.get("source_wallet_address"),
        token_id=args.get("token_id"),
    )
    decision = evaluate_usdc_transfer(intent, config.policy)
    intent.requires_approval = decision.requires_approval
    intent.auto_approved = decision.auto_approved
    intent.policy_reason = decision.reason
    intent.policy_details = decision.details
    if not decision.allowed:
        intent.status = IntentStatus.REJECTED
        ledger.save_intent(intent)
        ledger.audit("intent_rejected", intent.id, {"reason": decision.reason, "details": decision.details})
        return _json({"success": False, "intent": intent.to_dict(), "error": decision.reason})
    intent.status = IntentStatus.PENDING_APPROVAL if decision.requires_approval else IntentStatus.READY
    ledger.save_intent(intent)
    ledger.audit("intent_created", intent.id, {"kind": intent.kind.value, "rail": intent.rail.value, "amount_usdc": intent.amount_usdc, "recipient": intent.recipient})
    return _json({
        "success": True,
        "intent": _intent_summary(intent),
        "next_step": "operator_approval_required" if intent.requires_approval else "ready_to_execute",
    })


def execute_payment_intent(args: dict[str, Any], **_: Any) -> str:
    config, ledger = _services()
    intent_id = str(args["intent_id"])
    intent = ledger.get_intent(intent_id)
    if intent is None:
        return _json({"success": False, "error": f"Unknown intent: {intent_id}"})
    if intent.kind == IntentKind.USDC_TRANSFER:
        decision = evaluate_usdc_transfer(intent, config.policy)
    else:
        executor = X402Executor(config)
        probe = executor.probe(intent.recipient)
        if probe.quote is None:
            intent.status = IntentStatus.FAILED
            intent.last_error = "x402 endpoint did not return payment requirements"
            ledger.save_intent(intent)
            return _json({"success": False, "intent": intent.to_dict(), "error": intent.last_error})
        decision = evaluate_x402_quote(intent.recipient, probe.quote, config.policy)
        original_amount = Decimal(intent.amount_usdc)
        if probe.quote.amount_usdc > original_amount:
            decision = type(decision)(False, True, False, f"current x402 price {probe.quote.amount_usdc} exceeds approved intent price {original_amount}", decision.details)
    if not decision.allowed:
        intent.status = IntentStatus.REJECTED
        intent.last_error = decision.reason
        ledger.save_intent(intent)
        ledger.audit("intent_rejected", intent.id, {"reason": decision.reason})
        return _json({"success": False, "intent": intent.to_dict(), "error": decision.reason})
    approval = ledger.get_approval(intent.id)
    if decision.requires_approval and not approval.approved:
        return _json({
            "success": False,
            "intent": _intent_summary(intent),
            "error": "operator approval is required before execution",
            "approval_command": f"payguard approve {intent.id}",
        })

    try:
        if intent.kind == IntentKind.USDC_TRANSFER:
            circle = CircleClient(config)
            if intent.rail == PaymentRail.CIRCLE_DEV:
                result = circle.transfer_dev(intent)
                intent.status = IntentStatus.EXECUTED
            elif intent.rail == PaymentRail.CIRCLE_USER:
                result = circle.transfer_user(intent)
                intent.status = IntentStatus.CHALLENGE_CREATED
            else:
                raise ValueError(f"Unsupported rail for transfer intent: {intent.rail.value}")
            intent.provider_response = {"rail": result.rail, "response": result.response}
        elif intent.kind == IntentKind.X402_FETCH:
            x402 = X402Executor(config)
            result = x402.fetch(intent.recipient)
            intent.status = IntentStatus.EXECUTED
            intent.provider_response = {
                "status_code": result.status_code,
                "headers": result.headers,
                "body_text": result.body_text,
                "paid": result.paid,
                "payment_headers": result.payment_headers,
                "quote": result.quote.__dict__ if result.quote else None,
            }
        else:
            raise ValueError(f"Unsupported intent kind: {intent.kind.value}")
        intent.executed_at = __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat()
        intent.last_error = None
        ledger.save_intent(intent)
        ledger.audit("intent_executed", intent.id, {"status": intent.status.value})
        return _json({"success": True, "intent": intent.to_dict()})
    except Exception as exc:
        intent.status = IntentStatus.FAILED
        intent.last_error = str(exc)
        ledger.save_intent(intent)
        ledger.audit("intent_failed", intent.id, {"error": str(exc)})
        return _json({"success": False, "intent": intent.to_dict(), "error": str(exc)})


def get_payment_intent(args: dict[str, Any], **_: Any) -> str:
    _, ledger = _services()
    intent = ledger.get_intent(str(args["intent_id"]))
    if intent is None:
        return _json({"success": False, "error": "intent not found"})
    approval = ledger.get_approval(intent.id)
    return _json({"success": True, "intent": intent.to_dict(), "approval": approval.to_dict()})


def list_payment_intents(args: dict[str, Any], **_: Any) -> str:
    _, ledger = _services()
    limit = int(args.get("limit", 20))
    intents = [intent.to_dict() for intent in ledger.list_intents(limit=limit)]
    return _json({"success": True, "items": intents})


def fetch_paid_url(args: dict[str, Any], **_: Any) -> str:
    config, ledger = _services()
    url = str(args["url"])
    x402 = X402Executor(config)
    probe = x402.probe(url)
    if probe.status_code != 402 or probe.quote is None:
        return _json({
            "success": True,
            "paid": False,
            "status_code": probe.status_code,
            "headers": probe.headers,
            "body_text": probe.body.decode("utf-8", "ignore"),
        })
    decision = evaluate_x402_quote(url, probe.quote, config.policy)
    intent = PaymentIntent(
        id=str(uuid.uuid4()),
        kind=IntentKind.X402_FETCH,
        rail=PaymentRail.X402,
        asset=config.policy.asset,
        amount_usdc=str(probe.quote.amount_usdc),
        recipient=url,
        chain=probe.quote.network,
        reason=str(args.get("reason", f"x402 fetch for {url}")),
        metadata={
            "host": probe.quote.host,
            "pay_to": probe.quote.pay_to,
            "asset": probe.quote.asset,
        },
        requires_approval=decision.requires_approval,
        auto_approved=decision.auto_approved,
        policy_reason=decision.reason,
        policy_details=decision.details,
    )
    if not decision.allowed:
        intent.status = IntentStatus.REJECTED
        ledger.save_intent(intent)
        ledger.audit("intent_rejected", intent.id, {"reason": decision.reason})
        return _json({"success": False, "intent": intent.to_dict(), "error": decision.reason})
    ledger.save_intent(intent)
    ledger.audit("intent_created", intent.id, {"kind": intent.kind.value, "url": url, "amount_usdc": intent.amount_usdc})
    if decision.auto_approved and bool(args.get("allow_auto_execute", True)):
        return execute_payment_intent({"intent_id": intent.id})
    intent.status = IntentStatus.PENDING_APPROVAL
    ledger.save_intent(intent)
    return _json({
        "success": True,
        "intent": _intent_summary(intent),
        "quote": {"amount_usdc": intent.amount_usdc, "network": probe.quote.network, "pay_to": probe.quote.pay_to, "asset": probe.quote.asset},
        "next_step": "operator_approval_required",
    })
