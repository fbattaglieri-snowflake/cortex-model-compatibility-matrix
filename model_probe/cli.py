"""CLI for read-only discovery and explicit paid synthetic inference."""
import argparse
import json
import os
import re
import subprocess
from pathlib import Path

from .campaign import Campaign, private_write, CAPABILITIES
from .transport import Transport, validate_url


def discover(connection, host, expected_account):
    validate_url("https://" + host + "/api/v2/cortex/v1", host)
    result = subprocess.run(["snow", "sql", "--connection", connection, "--host", host,
        "--format", "JSON", "--silent", "--query",
        "SELECT CURRENT_ACCOUNT() AS ACCOUNT, CURRENT_REGION() AS REGION; "
        "SHOW PARAMETERS LIKE 'CORTEX_ENABLED_CROSS_REGION' IN ACCOUNT; SHOW MODELS IN ACCOUNT;"],
        capture_output=True, text=True, timeout=120, check=True)
    rows = json.loads(result.stdout)
    if rows[0][0]["ACCOUNT"].upper() != expected_account.upper():
        raise ValueError("Account mismatch; inference not authorized")
    return {"host": host, "context": rows[0][0], "parameters": rows[1], "models": rows[2]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inventory = sub.add_parser("discover", help="Read-only Snowflake CLI inventory")
    for name in ("connection", "host", "expected-account", "output"):
        inventory.add_argument("--" + name, required=True)
    run = sub.add_parser("run", help="Paid live probes; no settings or catalog changes")
    run.add_argument("--live", action="store_true", required=True)
    run.add_argument("--base-url", required=True)
    run.add_argument("--expected-host", required=True)
    run.add_argument("--model", required=True)
    run.add_argument("--protocol", choices=["chat", "messages", "responses"], required=True)
    run.add_argument("--scope", choices=["direct-rest", "service-rest", "proxy"], required=True)
    run.add_argument("--inventory", type=Path)
    run.add_argument("--expected-account")
    run.add_argument("--local-proxy", action="store_true")
    run.add_argument("--expected-base-url", help="Exact approved proxy URL including scheme, port and path")
    run.add_argument("--internal-proxy", action="store_true",
                     help="Explicit credential-free HTTP SPCS service mode; requires --expected-base-url")
    run.add_argument("--capabilities", nargs="+", choices=CAPABILITIES,
                     help="Required capabilities declared before execution; default: full suite")
    credentials = run.add_mutually_exclusive_group()
    credentials.add_argument("--token-env")
    credentials.add_argument("--token-file")
    run.add_argument("--auth-type", choices=["PROGRAMMATIC_ACCESS_TOKEN", "OAUTH", "KEYPAIR_JWT"], default="PROGRAMMATIC_ACCESS_TOKEN")
    run.add_argument("--reasoning", choices=["none", "minimal", "low", "medium", "high", "xhigh", "max"])
    run.add_argument("--repeats", type=int, choices=[1, 3], default=3)
    run.add_argument("--max-requests", type=int, default=60)
    run.add_argument("--deadline", type=float, default=1800)
    run.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "discover":
        private_write(Path(args.output), discover(args.connection, args.host, args.expected_account))
        print("Inventory written privately; inspect account, policy and model identifiers before inference.")
        return
    if not re.fullmatch(r"[A-Za-z0-9_.:/-]+", args.model):
        parser.error("Invalid model identifier")
    if args.local_proxy and args.scope != "proxy":
        parser.error("Loopback mode requires --scope proxy")
    if (args.expected_base_url or args.internal_proxy) and args.scope != "proxy":
        parser.error("Custom destination policy requires --scope proxy; direct/service REST remains unchanged")
    if args.scope == "service-rest":
        if (not args.expected_account or os.environ.get("SNOWFLAKE_ACCOUNT", "").upper() != args.expected_account.upper()
                or args.auth_type != "OAUTH" or not args.token_file):
            parser.error("Service REST requires matching SNOWFLAKE_ACCOUNT, expected account and OAuth token file")
    if args.scope == "direct-rest":
        if not args.inventory or not args.expected_account:
            parser.error("Direct REST requires --inventory and --expected-account")
        inventory_doc = json.loads(args.inventory.read_text())
        if (inventory_doc["host"] != args.expected_host or
                inventory_doc["context"]["ACCOUNT"].upper() != args.expected_account.upper()):
            parser.error("Inventory account/host mismatch")
        if args.model.lower() not in {row["name"].lower() for row in inventory_doc["models"]}:
            parser.error("Exact model absent from inventory; no aliases inferred")
    transport = Transport(args.base_url, args.expected_host, token_env=args.token_env,
        token_file=args.token_file, auth_type=args.auth_type, local=args.local_proxy,
        expected_base_url=args.expected_base_url, internal_proxy=args.internal_proxy)
    campaign = Campaign(transport, args.model, args.protocol, args.output, repeats=args.repeats,
        reasoning=args.reasoning, max_requests=args.max_requests, deadline=args.deadline, scope=args.scope,
        capabilities=args.capabilities)
    if args.inventory:
        private_write(args.output / "inventory.json", json.loads(args.inventory.read_text()))
    summary = campaign.run()
    print(json.dumps(summary, indent=2))
    raise SystemExit(0 if summary["status"] == "PROFILE_QUALIFIED" else 1)


if __name__ == "__main__":
    main()