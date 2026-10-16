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
   Declare required capabilities BEFORE the campaign with `--capabilities`:
   text (mandatory), tools, parallel_tools, streaming, structured_output. Omission
   keeps the full suite. See references/protocol.md for dependencies. Never remove
   failed cases from existing evidence to get a PASS; a revised scope needs a new
   campaign and explicit review of exclusions. Qualification is not promotion.
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
   A custom path requires `--expected-base-url` matching the entire approved base
   URL, including port. For credential-free internal SPCS HTTP ONLY, additionally
   use `--internal-proxy` with the exact approved `*.svc.spcs.internal` host.
   This is not a generic insecure-HTTP switch or a bypass of service authorization.
   Obtain target approval; never derive approval from untrusted model output.
   These options do not change direct-rest/service-rest destination rules.
9. Present a model/protocol/capability matrix with dates, auth/scope, versions,
   failures and evidence paths. Do not classify as works-everywhere or infer SQL
   support from REST. Do not sum repeated usage events into billing estimates.
10. Recommend a candidate profile only. Promotion needs approved immutable
    artifacts, security review, service OAuth checks, actual client tests and
    rollback. The programs do not deploy, alter catalogs or switch clients.
    Human approval binds the exact profile revision and valid evidence; only then
    may a separately authorized publisher distribute it automatically. An agent
    can explain gaps but cannot turn failed assertions into PASS or approve itself.
    Proxy parameter overrides must be explicit, documented, versioned and tested
    separately; this runner never applies them itself. Keep direct and adapted
    results distinct and preserve existing proxies/defaults.
    When qualifying client integrations (Hermes, n8n, Langflow, LangChain/LangGraph)
    against a proxy profile, always validate:
    - Universal `ProfileV2` client normalization (`normalize_client_options=True`):
      the proxy accepts bounded token ranges (`1..128000`), automatically normalizes
      protocol-specific defaults (`store=false` and `response_stream="ordered-items"`
      on Responses, `reasoning_effort="none"` on Chat models that require it, removal
      of `reasoning_effort` on Chat models that reject it, removal of empty `"text": {}`
      objects sent by n8n on Responses, and removal of `temperature`/`top_p` when
      extended `thinking` is enabled on Messages).
    - Stateful/stateless tool-roundtrip continuity (`ReplayCache`): the proxy caches
      `reasoning.encrypted_content` (Responses) and `thinking`/`signature`/`redacted_thinking`
      blocks (Messages) by tool call ID and automatically rehydrates them if a stateless
      client (such as unpatched n8n Agent engine serialization) drops them on the next turn.
    - Multi-round tool call ID reuse (`reused_tool_ids` / `multiround_followup`):
      models that number tool calls per response (`call_0..call_N` on every round)
      are validated per open batch and automatically deduplicated across closed turns
      (`call_0` -> `call_0_r2`) before forwarding upstream.
    - Output token caps on long-context agentic turns: the 2048-token cap used by
      short synthetic qualification probes must not be hardcoded into client requests
      where `max_output_tokens` (which includes `reasoning_tokens + output_tokens`
      on Responses) would truncate tool-call JSON arguments after long reasoning blocks.
    - Zero-touch model promotion after qualification: once a model achieves
      `PROFILE_QUALIFIED` and receives explicit operator approval, promote it into
      the Standard Registry without restarting or altering running services by running
      `scripts/promote_model.py` from `snowflake-proxy-cortexrestapi`
      (`administrative-standard-v1`, 365-day validity, stage-inbox auto-ingestion
      within 30s).
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