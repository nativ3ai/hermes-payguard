from __future__ import annotations

import json
import os
import socket
import threading
import types
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from eth_account import Account
from x402 import PaymentRequired, PaymentRequirements, ResourceInfo
from x402.http.utils import encode_payment_required_header

from hermes_payguard import plugin
from hermes_payguard.cli import main as cli_main
from hermes_payguard.config import DEFAULT_POLICY_TEXT, load_config
from hermes_payguard.tools import (
    execute_payment_intent,
    fetch_paid_url,
    get_payment_intent,
    prepare_cctp_transfer,
    prepare_usdc_transfer,
)


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class _ThreadedHTTPServer:
    def __init__(self, handler_cls: type[BaseHTTPRequestHandler], port: int):
        self.server = HTTPServer(("127.0.0.1", port), handler_cls)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self.server

    def __exit__(self, exc_type, exc, tb):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


class CircleMockHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def log_message(self, format, *args):  # noqa: A003
        return

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        CircleMockHandler.requests.append({
            "path": self.path,
            "headers": dict(self.headers),
            "payload": payload,
        })
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if self.path.endswith("/developer/transactions/transfer"):
            body = {"data": {"id": "txn_dev_123", "state": "INITIATED", "idempotencyKey": payload["idempotencyKey"]}}
        elif self.path.endswith("/user/transactions/transfer"):
            body = {"data": {"challengeId": "challenge_123", "state": "PENDING_CHALLENGE", "idempotencyKey": payload["idempotencyKey"]}}
        else:
            body = {"error": "unknown path"}
        self.wfile.write(json.dumps(body).encode("utf-8"))


class X402MockHandler(BaseHTTPRequestHandler):
    smallest_unit_amount: str = "10000"
    seen_payment_headers: list[str] = []

    def log_message(self, format, *args):  # noqa: A003
        return

    def do_GET(self):  # noqa: N802
        if self.path != "/paid":
            self.send_response(404)
            self.end_headers()
            return
        payment_sig = self.headers.get("PAYMENT-SIGNATURE")
        if not payment_sig:
            payment_required = PaymentRequired(
                resource=ResourceInfo(url=f"http://127.0.0.1:{self.server.server_port}/paid", description="Premium data", mimeType="application/json"),
                accepts=[
                    PaymentRequirements(
                        scheme="exact",
                        network="eip155:84532",
                        asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
                        amount=X402MockHandler.smallest_unit_amount,
                        payTo="0x1111111111111111111111111111111111111111",
                        maxTimeoutSeconds=300,
                        extra={"name": "USD Coin", "version": "2", "decimals": 6},
                    )
                ],
            )
            self.send_response(402)
            self.send_header("PAYMENT-REQUIRED", encode_payment_required_header(payment_required))
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "payment required"}).encode("utf-8"))
            return
        X402MockHandler.seen_payment_headers.append(payment_sig)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        body = {"ok": True, "resource": "premium-data", "paid": True}
        self.wfile.write(json.dumps(body).encode("utf-8"))


class CCTPMockHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def log_message(self, format, *args):  # noqa: A003
        return

    def do_GET(self):  # noqa: N802
        CCTPMockHandler.requests.append({"method": "GET", "path": self.path, "headers": dict(self.headers)})
        if self.path.startswith("/v2/burn/USDC/fees/6/3"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            body = [
                {"finalityThreshold": 1000, "minimumFee": 1, "forwardFee": {"low": 90, "medium": 110, "high": 160}},
                {"finalityThreshold": 2000, "minimumFee": 0, "forwardFee": {"low": 90, "medium": 110, "high": 160}},
            ]
            self.wfile.write(json.dumps(body).encode("utf-8"))
            return
        if self.path.startswith("/v2/messages/6"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            body = {
                "messages": [
                    {
                        "messageHash": "0xmessage",
                        "transactionHash": "0xtransfer",
                        "status": "complete",
                        "attestation": "0xattestation",
                        "eventNonce": "42",
                        "forwardTxHash": "0xforward",
                    }
                ]
            }
            self.wfile.write(json.dumps(body).encode("utf-8"))
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        CCTPMockHandler.requests.append({"method": "POST", "path": self.path, "headers": dict(self.headers), "payload": payload})
        if self.path == "/execute-cctp":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            body = {"transactionHash": "0xtransfer", "executorStatus": "submitted"}
            self.wfile.write(json.dumps(body).encode("utf-8"))
            return
        self.send_response(404)
        self.end_headers()


@pytest.fixture()
def hermes_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "hermes"
    state = home / "payguard"
    state.mkdir(parents=True)
    (state / "policy.yaml").write_text(DEFAULT_POLICY_TEXT, encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home


def _write_policy(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_load_config_defaults_to_mainnet(hermes_home: Path):
    config = load_config()
    assert config.network_profile == "mainnet"
    assert config.policy.default_chain == "BASE"
    assert config.circle_api_base_url == "https://api.circle.com"
    assert config.circle_cctp_api_base_url == "https://iris-api.circle.com"
    assert config.x402_network == "eip155:8453"


def test_prepare_and_execute_circle_dev_transfer(hermes_home: Path, monkeypatch: pytest.MonkeyPatch):
    port = _free_port()
    CircleMockHandler.requests.clear()
    _write_policy(
        hermes_home / "payguard" / "policy.yaml",
        """mode: enforce
asset: USDC
default_chain: BASE-SEPOLIA
per_payment_limit_usdc: 100
micro_auto_approve_limit_usdc: 0.05
allowed_circle_recipients:
  - 0xabc0000000000000000000000000000000000000
allowed_x402_hosts: [127.0.0.1]
allow_unlisted_circle_recipients: false
allow_unlisted_x402_hosts: false
""",
    )
    monkeypatch.setenv("CIRCLE_API_BASE_URL", f"http://127.0.0.1:{port}")
    monkeypatch.setenv("CIRCLE_API_KEY", "test-key")
    monkeypatch.setenv("CIRCLE_ENTITY_SECRET_CIPHERTEXT", "ciphertext")
    monkeypatch.setenv("CIRCLE_WALLET_ID", "wallet-123")
    monkeypatch.setenv("CIRCLE_TOKEN_ID", "token-123")

    with _ThreadedHTTPServer(CircleMockHandler, port):
        prepared = json.loads(prepare_usdc_transfer({
            "amount_usdc": 12.5,
            "recipient": "0xabc0000000000000000000000000000000000000",
            "rail": "circle_dev",
            "reason": "vendor invoice",
        }))
        assert prepared["success"] is True
        intent_id = prepared["intent"]["id"]
        assert prepared["next_step"] == "operator_approval_required"

        assert cli_main(["approve", intent_id, "--ttl-seconds", "120"]) == 0
        executed = json.loads(execute_payment_intent({"intent_id": intent_id}))
        assert executed["success"] is True
        assert executed["intent"]["status"] == "executed"
        assert executed["intent"]["provider_response"]["response"]["data"]["id"] == "txn_dev_123"

    assert CircleMockHandler.requests[0]["path"] == "/v1/w3s/developer/transactions/transfer"
    assert CircleMockHandler.requests[0]["payload"]["walletId"] == "wallet-123"
    assert CircleMockHandler.requests[0]["payload"]["destinationAddress"] == "0xabc0000000000000000000000000000000000000"


def test_prepare_and_execute_circle_user_transfer_challenge(hermes_home: Path, monkeypatch: pytest.MonkeyPatch):
    port = _free_port()
    CircleMockHandler.requests.clear()
    _write_policy(
        hermes_home / "payguard" / "policy.yaml",
        """mode: enforce
asset: USDC
default_chain: BASE-SEPOLIA
per_payment_limit_usdc: 100
micro_auto_approve_limit_usdc: 0.05
allowed_circle_recipients:
  - 0xdef0000000000000000000000000000000000000
allowed_x402_hosts: [127.0.0.1]
allow_unlisted_circle_recipients: false
allow_unlisted_x402_hosts: false
""",
    )
    monkeypatch.setenv("CIRCLE_API_BASE_URL", f"http://127.0.0.1:{port}")
    monkeypatch.setenv("CIRCLE_API_KEY", "test-key")
    monkeypatch.setenv("CIRCLE_WALLET_ID", "wallet-999")
    monkeypatch.setenv("CIRCLE_TOKEN_ID", "token-999")
    monkeypatch.setenv("CIRCLE_X_USER_TOKEN", "user-token")

    with _ThreadedHTTPServer(CircleMockHandler, port):
        prepared = json.loads(prepare_usdc_transfer({
            "amount_usdc": 3.25,
            "recipient": "0xdef0000000000000000000000000000000000000",
            "rail": "circle_user",
            "reason": "tip jar",
        }))
        intent_id = prepared["intent"]["id"]
        assert cli_main(["approve", intent_id]) == 0
        executed = json.loads(execute_payment_intent({"intent_id": intent_id}))
        assert executed["success"] is True
        assert executed["intent"]["status"] == "challenge_created"
        assert executed["intent"]["provider_response"]["response"]["data"]["challengeId"] == "challenge_123"

    assert CircleMockHandler.requests[0]["path"] == "/v1/w3s/user/transactions/transfer"
    assert CircleMockHandler.requests[0]["headers"]["X-User-Token"] == "user-token"


def test_x402_autopays_micropayment(hermes_home: Path, monkeypatch: pytest.MonkeyPatch):
    port = _free_port()
    X402MockHandler.smallest_unit_amount = "10000"  # 0.01 USDC
    X402MockHandler.seen_payment_headers.clear()
    _write_policy(
        hermes_home / "payguard" / "policy.yaml",
        """mode: enforce
asset: USDC
default_chain: BASE-SEPOLIA
per_payment_limit_usdc: 100
micro_auto_approve_limit_usdc: 0.05
allowed_circle_recipients: []
allowed_x402_hosts: [127.0.0.1]
allow_unlisted_circle_recipients: false
allow_unlisted_x402_hosts: false
""",
    )
    acct = Account.create()
    monkeypatch.setenv("PAYGUARD_EVM_PRIVATE_KEY", acct.key.hex())
    monkeypatch.setenv("PAYGUARD_X402_NETWORK", "eip155:84532")

    with _ThreadedHTTPServer(X402MockHandler, port):
        result = json.loads(fetch_paid_url({"url": f"http://127.0.0.1:{port}/paid"}))
        assert result["success"] is True
        assert result["intent"]["status"] == "executed"
        assert result["intent"]["provider_response"]["paid"] is True
        assert "premium-data" in result["intent"]["provider_response"]["body_text"]

    assert X402MockHandler.seen_payment_headers, "expected PAYMENT-SIGNATURE on retry"


def test_x402_over_limit_requires_manual_approval(hermes_home: Path, monkeypatch: pytest.MonkeyPatch):
    port = _free_port()
    X402MockHandler.smallest_unit_amount = "100000"  # 0.10 USDC
    X402MockHandler.seen_payment_headers.clear()
    _write_policy(
        hermes_home / "payguard" / "policy.yaml",
        """mode: enforce
asset: USDC
default_chain: BASE-SEPOLIA
per_payment_limit_usdc: 100
micro_auto_approve_limit_usdc: 0.05
allowed_circle_recipients: []
allowed_x402_hosts: [127.0.0.1]
allow_unlisted_circle_recipients: false
allow_unlisted_x402_hosts: false
""",
    )
    acct = Account.create()
    monkeypatch.setenv("PAYGUARD_EVM_PRIVATE_KEY", acct.key.hex())
    monkeypatch.setenv("PAYGUARD_X402_NETWORK", "eip155:84532")

    with _ThreadedHTTPServer(X402MockHandler, port):
        prepared = json.loads(fetch_paid_url({"url": f"http://127.0.0.1:{port}/paid"}))
        assert prepared["success"] is True
        assert prepared["next_step"] == "operator_approval_required"
        intent_id = prepared["intent"]["id"]
        assert cli_main(["approve", intent_id, "--ttl-seconds", "120"]) == 0
        executed = json.loads(execute_payment_intent({"intent_id": intent_id}))
        assert executed["success"] is True
        assert executed["intent"]["status"] == "executed"

    assert X402MockHandler.seen_payment_headers, "expected paid retry after approval"


def test_policy_rejects_unlisted_circle_recipient(hermes_home: Path):
    prepared = json.loads(prepare_usdc_transfer({
        "amount_usdc": 2,
        "recipient": "0xdead000000000000000000000000000000000000",
        "rail": "circle_dev",
        "reason": "blocked recipient",
    }))
    assert prepared["success"] is False
    assert prepared["intent"]["status"] == "rejected"


def test_prepare_and_execute_cctp_transfer(hermes_home: Path, monkeypatch: pytest.MonkeyPatch):
    port = _free_port()
    CCTPMockHandler.requests.clear()
    _write_policy(
        hermes_home / "payguard" / "policy.yaml",
        """mode: enforce
network_profile: testnet
asset: USDC
default_chain: BASE-SEPOLIA
per_payment_limit_usdc: 100
micro_auto_approve_limit_usdc: 0.05
allowed_circle_recipients:
  - 0xabc0000000000000000000000000000000000000
allow_unlisted_circle_recipients: false
allow_unlisted_cctp_destinations: true
allowed_x402_hosts: [127.0.0.1]
allow_unlisted_x402_hosts: false
""",
    )
    monkeypatch.setenv("CIRCLE_CCTP_API_BASE_URL", f"http://127.0.0.1:{port}")
    monkeypatch.setenv("CCTP_EXECUTOR_URL", f"http://127.0.0.1:{port}/execute-cctp")

    with _ThreadedHTTPServer(CCTPMockHandler, port):
        prepared = json.loads(
            prepare_cctp_transfer(
                {
                    "amount_usdc": 12.5,
                    "recipient": "0xabc0000000000000000000000000000000000000",
                    "destination_chain": "ARBITRUM",
                    "source_chain": "BASE-SEPOLIA",
                    "reason": "cross-chain treasury rebalance",
                    "transfer_speed": "fast",
                    "use_forwarder": True,
                    "forward_gas_level": "medium",
                }
            )
        )
        assert prepared["success"] is True
        assert prepared["intent"]["status"] == "pending_approval"
        assert prepared["quote"]["destination_chain"] == "ARBITRUM"
        assert prepared["quote"]["source_domain"] == 6
        intent_id = prepared["intent"]["id"]
        assert cli_main(["approve", intent_id, "--ttl-seconds", "120"]) == 0
        executed = json.loads(execute_payment_intent({"intent_id": intent_id}))
        assert executed["success"] is True
        assert executed["intent"]["status"] == "executed"
        assert executed["intent"]["provider_response"]["executor_response"]["transactionHash"] == "0xtransfer"
        assert executed["intent"]["provider_response"]["message_status"]["attestation"] == "0xattestation"

    paths = [item["path"] for item in CCTPMockHandler.requests]
    assert any(path.startswith("/v2/burn/USDC/fees/6/3") for path in paths)
    assert "/execute-cctp" in paths
    assert any(path.startswith("/v2/messages/6") for path in paths)


def test_plugin_registers_expected_tools():
    registered = []

    class FakeCtx:
        def register_tool(self, **kwargs):
            registered.append(kwargs["name"])

    plugin.register(FakeCtx())
    assert set(registered) == {
        "payguard_prepare_usdc_transfer",
        "payguard_prepare_cctp_transfer",
        "payguard_execute_payment_intent",
        "payguard_get_payment_intent",
        "payguard_list_payment_intents",
        "payguard_fetch_paid_url",
    }


def test_plugin_loads_via_hermes_plugin_manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    hermes_repo = Path("/Users/native/Downloads/hermes-agent-camel")
    if not hermes_repo.exists():
        pytest.skip("local hermes-agent-camel checkout not available")
    monkeypatch.syspath_prepend(str(hermes_repo))
    hermes_home = tmp_path / "hermes_home"
    plugins_dir = hermes_home / "plugins"
    plugins_dir.mkdir(parents=True)
    plugin_target = plugins_dir / "hermes-payguard"
    plugin_target.symlink_to(Path(__file__).resolve().parents[1], target_is_directory=True)
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    fake_registry = types.SimpleNamespace(_tools={})

    def _register(**kwargs):
        fake_registry._tools[kwargs["name"]] = kwargs

    fake_registry_module = types.ModuleType("tools.registry")
    fake_registry_module.registry = types.SimpleNamespace(register=_register)
    fake_tools_module = types.ModuleType("tools")
    fake_tools_module.__path__ = []
    monkeypatch.setitem(__import__("sys").modules, "tools", fake_tools_module)
    monkeypatch.setitem(__import__("sys").modules, "tools.registry", fake_registry_module)

    from hermes_cli.plugins import PluginManager

    mgr = PluginManager()
    mgr.discover_and_load()
    assert "hermes-payguard" in mgr._plugins
    assert mgr._plugins["hermes-payguard"].enabled is True
    assert "payguard_prepare_usdc_transfer" in fake_registry._tools
