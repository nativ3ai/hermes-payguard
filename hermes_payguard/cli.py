from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

from .config import DEFAULT_POLICY_TEXT, load_config
from .ledger import IntentLedger


def cmd_doctor(_: argparse.Namespace) -> int:
    config = load_config()
    state = {
        "state_dir": str(config.state_dir),
        "policy_path": str(config.policy_path),
        "policy_exists": config.policy_path.exists(),
        "circle_api_key": bool(config.circle_api_key),
        "circle_entity_secret_ciphertext": bool(config.circle_entity_secret_ciphertext),
        "circle_wallet_id": bool(config.circle_wallet_id),
        "circle_token_id": bool(config.circle_token_id),
        "circle_x_user_token": bool(config.circle_x_user_token),
        "x402_private_key": bool(config.x402_private_key),
        "x402_network": config.x402_network,
    }
    print(json.dumps(state, indent=2))
    return 0


def cmd_init_policy(args: argparse.Namespace) -> int:
    config = load_config()
    path = Path(args.path) if args.path else config.policy_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not args.force:
        raise SystemExit(f"Policy already exists at {path}. Use --force to overwrite.")
    path.write_text(DEFAULT_POLICY_TEXT, encoding="utf-8")
    print(path)
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    config = load_config()
    ledger = IntentLedger(config.state_dir)
    state = ledger.approve_intent(args.intent_id, ttl_seconds=args.ttl_seconds, actor=args.actor)
    print(json.dumps(state.to_dict(), indent=2))
    return 0


def cmd_revoke(args: argparse.Namespace) -> int:
    config = load_config()
    ledger = IntentLedger(config.state_dir)
    ledger.revoke_intent(args.intent_id, actor=args.actor)
    print(json.dumps({"revoked": True, "intent_id": args.intent_id}, indent=2))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    config = load_config()
    ledger = IntentLedger(config.state_dir)
    intent = ledger.get_intent(args.intent_id)
    if intent is None:
        raise SystemExit(f"Unknown intent: {args.intent_id}")
    print(json.dumps({"intent": intent.to_dict(), "approval": ledger.get_approval(args.intent_id).to_dict()}, indent=2))
    return 0


def cmd_install_plugin(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    hermes_home = Path(args.hermes_home or os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser()
    plugins_dir = hermes_home / "plugins"
    target = plugins_dir / "hermes-payguard"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        if args.force:
            if target.is_symlink() or target.is_file():
                target.unlink()
            else:
                shutil.rmtree(target)
        else:
            raise SystemExit(f"Plugin target already exists: {target}")
    if args.mode == "copy":
        shutil.copytree(repo_root, target)
    else:
        target.symlink_to(repo_root, target_is_directory=True)
    print(target)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="payguard")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor")
    doctor.set_defaults(func=cmd_doctor)

    init_policy = sub.add_parser("init-policy")
    init_policy.add_argument("--path")
    init_policy.add_argument("--force", action="store_true")
    init_policy.set_defaults(func=cmd_init_policy)

    approve = sub.add_parser("approve")
    approve.add_argument("intent_id")
    approve.add_argument("--ttl-seconds", type=int, default=900)
    approve.add_argument("--actor", default="operator")
    approve.set_defaults(func=cmd_approve)

    revoke = sub.add_parser("revoke")
    revoke.add_argument("intent_id")
    revoke.add_argument("--actor", default="operator")
    revoke.set_defaults(func=cmd_revoke)

    show = sub.add_parser("show")
    show.add_argument("intent_id")
    show.set_defaults(func=cmd_show)

    install = sub.add_parser("install-plugin")
    install.add_argument("--hermes-home")
    install.add_argument("--mode", choices=["symlink", "copy"], default="symlink")
    install.add_argument("--force", action="store_true")
    install.set_defaults(func=cmd_install_plugin)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
