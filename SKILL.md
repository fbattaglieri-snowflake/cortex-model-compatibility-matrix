---
name: cortex-model-compatibility-matrix
description: "Qualify Cortex models for a proxy using repeatable endpoint-specific tests. Use when testing new models, investigating REST availability, validating streaming/tools/structured output, or preparing a proxy model catalog and escalation draft."
---

# Cortex model compatibility matrix

## Purpose

Establish which capabilities a model actually supports on the user's selected
account, endpoint, identity and client. Catalog visibility is not REST access;
HTTP 200 is not tool correctness; SDK success is not application certification.
Use the bundled programs, not improvised curl tests or hardcoded model lists.

## Prerequisites

Python 3.11+ for REST tests; Snowflake CLI for read-only discovery. Optional SDK
dependencies are declared in pyproject.toml. All commands use absolute paths to
this skill's repository. See references/protocol.md for exact coverage and limits.

## Workflow

1. Confirm the intended account, host, model, protocol and scope. Do not assume
   the IDE's connected account is the target. Preserve all deployed defaults.
2. Read references/cross-region.md. Recommend ANY_REGION for maximum coverage
   only when the user's residency/compliance requirements permit it. Never
   change account settings, grants or enablement as a side effect of testing.
3. Use `scripts/qualify.py discover --connection NAME --host HOST
   --expected-account LOCATOR --output /PRIVATE/inventory.json`. Inspect the
   returned account, policy and exact identifier; do not invent aliases.
4. Explain live probes incur inference charges and use synthetic fixtures only.
   Run only after live testing is authorized. Set credentials through a secret
   environment variable or selected token file, never chat/argv/repository.
5. Use `scripts/qualify.py run --live --base-url https://HOST/api/v2/cortex/v1
   --expected-host HOST --expected-account LOCATOR --inventory /PRIVATE/inventory.json
   --model MODEL --protocol chat --scope direct-rest --token-env SNOWFLAKE_PAT
   --output /PRIVATE/new-run`. Choose messages or responses explicitly where
   appropriate. Treat each reasoning variant as a separate campaign, never a
   silent downgrade. No retry or model/protocol fallback.
6. Inspect per-case evidence before interpreting the summary. Missing capability
   tests are BLOCKED or NOT TESTED, not PASS. An API rejection is dated evidence,
   not proof that a model will never work. Run a separately recorded positive
   control on the same target if access is ambiguous.
7. After a Chat profile passes, optionally run scripts/sdk_probe.py against
   that campaign. Other SDK protocols and real apps need separate qualification.
8. Test an existing proxy separately with `--scope proxy`; use explicit
   `--local-proxy` for unauthenticated loopback and never send Snowflake tokens
   there. Remote proxies must use TLS and an explicitly approved host/credential.
9. Present a model/protocol/capability matrix with dates, auth/scope, versions,
   failures and evidence paths. Do not classify as works-everywhere or infer SQL
   support from REST. Do not sum repeated usage events into billing estimates.
10. Recommend a candidate profile only. Promotion needs approved immutable
    artifacts, security review, service OAuth checks, actual client tests and
    rollback. The programs do not deploy, alter catalogs or switch clients.
11. If asked, draft an escalation with sanitized recent errors/request IDs.
    Show the draft before sending. Never publish private evidence automatically.

## Stopping points

- Missing target, credentials or authorization for paid live probes.
- Any request to change policy, grants, production settings or client defaults.
- Unclear interpretation of error versus harness defect: diagnose before promoting.
- Sending messages or publishing account-derived evidence without permission.

## Output

Private manifest, exclusive per-case JSON evidence and capability summary.
Each result is PASS, FAIL or BLOCKED; out-of-scope features are NOT TESTED.
PROFILE_QUALIFIED is bounded test evidence, never deployment approval.
Keep historical failures; use a new directory for every retest or harness revision.