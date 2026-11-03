---
name: cortex-model-compatibility-matrix
description: "Qualify Snowflake Cortex models and SPCS LLM proxy profiles using deterministic 3-repeat × 13-case REST probes across messages, chat, and responses. Use whenever testing new Cortex models, investigating REST API availability, validating SSE streaming/tool roundtrips/structured output, running daily autonomous model scouting, promoting or revoking models in snowflake-proxy-cortexrestapi, or preparing escalation drafts. Triggers: testa endpoint cortex, quali modelli funzionano, qualifica modello, verifica proxy, aggiorna elenco modelli, promuovi modello, rimuovi modello, model scouting."
---

# Cortex Model Compatibility Matrix

## Purpose & Companion Proxy Dependency

Establish which capabilities a Snowflake Cortex model actually supports on the user's selected account, REST endpoint (`/api/v2/cortex/v1/{messages,chat/completions,responses}`), identity, and proxy profile.
- **Catalog visibility (`SHOW MODELS IN ACCOUNT`) is not REST reachability.**
- **A single `HTTP 200` is not agentic tool/streaming correctness.**
- **SDK success is not multi-consumer orchestration certification.**

This skill and its `model_probe` package serve as the **foundational qualification and evidence engine** for [**`snowflake-proxy-cortexrestapi`**](https://github.com/fbattaglieri-snowflake/snowflake-proxy-cortexrestapi):
1. `src/llm_proxy_standard/evidence.py` (`import_campaign`) imports `model_probe` and verifies `source_sha256` digests and the 3-repeat qualification gate before admitting evidence into the Registry.
2. `scripts/daily_scout_and_promote.py` and `scripts/spcs_scout_worker.py` import `model_probe.campaign.Campaign` and `model_probe.transport.Transport` to qualify newly discovered `CORTEX_BASE` models automatically.
3. `Dockerfile.qualification` embeds `model_probe` (`/opt/proxy/model_probe`) inside the SPCS qualification and registry container image.
4. `scripts/promote_model.py` packages `PROFILE_QUALIFIED` profiles into `ProfileV2` (`administrative-standard-v1`, 365-day validity) or builds `--revoke` tombstones for zero-touch stage-inbox ingestion.

## Prerequisites

- Python 3.11+ (core REST runner uses only the Python standard library).
- Snowflake CLI (`snow`) for read-only account and model inventory discovery.
- Optional SDK extras (`pip install -e '.[sdk]'`) for `scripts/sdk_probe.py`.
- Always use absolute paths to this repository's scripts (`scripts/qualify.py`, `scripts/sdk_probe.py`).
- Load `references/protocol.md` for full contract semantics and `references/cross-region.md` for `CORTEX_ENABLED_CROSS_REGION` guidance.

## Workflow

```text
Confirm Target & Scope
  ↓
Step 1: Read-Only Discovery (qualify.py discover) + Verify ANY_REGION
  ↓
Step 2: Authorize & Run 3-Repeat × 13-Case Campaign (qualify.py run --live)
  ↓
Step 3: Inspect Per-Case Evidence & Positive Controls
  ↓
Step 4: Validate Proxy ProfileV2 Compliance (Normalizer, ReplayCache, Ordered-Items, 1M Bounds)
  ↓
Step 5: Zero-Touch Promotion / Revocation (promote_model.py) or Daily Scouting (daily_scout_and_promote.py)
```

### Step 1: Confirm Target, Scope & Cross-Region Setting

1. Confirm the intended Snowflake account locator, host (`<org>-<account>.snowflakecomputing.com`), model ID, protocol (`messages`, `chat`, or `responses`), and scope (`direct-rest`, `service-rest`, or `proxy`). Never assume the IDE's default connection is the target account.
2. Read `references/cross-region.md`. Recommend `CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION'` for maximum model coverage when permitted by the user's residency/compliance rules, but **never** run `ALTER ACCOUNT` automatically.
3. Capture a read-only inventory snapshot into a private directory (`0700`):
   ```bash
   python3 <SKILL_DIR>/scripts/qualify.py discover \
     --connection <CONNECTION_NAME> \
     --host <HOST> \
     --expected-account <LOCATOR> \
     --output /PRIVATE/inventory.json
   ```
   Verify the exact model identifier in `inventory.json` before testing; never invent model aliases.

### Step 2: Declare Capabilities & Run the Qualification Campaign

1. Explain that `--live` probes issue up to 39 synthetic requests (`3 repeats × 13 cases`, `2048` max output tokens per probe, `retries = 0`) and incur token charges. Proceed only after explicit user authorization.
2. Supply credentials via `--token-env SNOWFLAKE_PAT` or `--token-file /PRIVATE/token` (never inline in CLI arguments or committed files).
3. Declare required capabilities **before** starting the campaign via `--capabilities` (`text` [mandatory], `tools`, `parallel_tools`, `streaming`, `structured_output`), or omit `--capabilities` to run the full 13-case suite. Never delete failed cases from existing evidence to manufacture a `PASS`.
4. Run a separate campaign for each `(model, protocol, reasoning)` tuple:
   ```bash
   python3 <SKILL_DIR>/scripts/qualify.py run --live \
     --base-url https://<HOST>/api/v2/cortex/v1 \
     --expected-host <HOST> \
     --expected-account <LOCATOR> \
     --inventory /PRIVATE/inventory.json \
     --model <MODEL_ID> \
     --protocol <messages|chat|responses> \
     --scope direct-rest \
     --token-env SNOWFLAKE_PAT \
     --output /PRIVATE/run-<model>-<protocol>
   ```
   - Channel routing heuristics: `claude-*` &rarr; `messages`; `openai-gpt-*` &rarr; `responses` then `chat` (`--reasoning none` and default); other families (`glm-*`, `grok-*`, `kimi-*`, `gemini-*`, `mistral-*`, `qwen-*`) &rarr; `chat` (default and `--reasoning none`), `responses`, `messages`.

### Step 3: Inspect Evidence, Positive Controls & Proxy Targets

1. Inspect `summary.json` and individual `case-*.json` files before drawing conclusions. Excluded capabilities are `NOT TESTED`; prerequisite failures are `BLOCKED`; HTTP/assertion failures are `FAIL`.
2. When `text` fails with `HTTP 400`, run a separately recorded positive control (a known-good model on the same host and identity) to distinguish model-specific REST unavailability from account/auth issues.
3. For Chat profiles that achieve `PROFILE_QUALIFIED`, optionally run `scripts/sdk_probe.py` to test OpenAI SDK, LangChain (stream/non-stream), and LangGraph (`InMemorySaver`).
4. To test an existing proxy (`--scope proxy`):
   - Use `--local-proxy` for unauthenticated `http://localhost` / `127.0.0.1` loopback (never pass tokens).
   - Use `--expected-base-url` for custom protocol prefixes (`/chat/v1`, `/responses/v1`, `/messages/v1`).
   - Use `--internal-proxy` with `--expected-base-url` for credential-free internal SPCS HTTP (`http://<service>.<ns>.svc.spcs.internal:8080/<protocol>/v1`).

### Step 4: Validate `snowflake-proxy-cortexrestapi` Compliance Gates

When qualifying models or client integrations (**n8n**, **Hermes**, **Langflow**, **SnowflakeLangflow**, **LangChain / LangGraph**) for [**`snowflake-proxy-cortexrestapi`**](https://github.com/fbattaglieri-snowflake/snowflake-proxy-cortexrestapi), verify all six proxy compliance rules:

1. **Universal `ProfileV2` Option Normalization (`normalize_client_options = True` in `rules.py`):**
   - Token budgets accept `1..128000` (clamped if above maximum; default `max_tokens = 4096` on Messages when omitted; `max_output_tokens` left unset on Responses when omitted so long reasoning chains do not truncate downstream `function_call` JSON arguments).
   - **Responses (`/responses/v1`):** Forces `store = false`, injects `include = ["reasoning.encrypted_content"]`, strips empty `"text": {}` objects sent by n8n and `prompt_cache_retention`, strips `temperature`/`top_p` on reasoning models, and clamps out-of-domain `reasoning.effort` (`"none"`/`"minimal"` &rarr; `"low"`) and `reasoning.summary`.
   - **Chat (`/chat/v1`):** Resolves `max_tokens` + `max_completion_tokens` conflicts, forces `reasoning_effort = "none"` on models that require it, strips `reasoning_effort` on Chat models that reject it, and publishes `metadata.constraints` on `GET /chat/v1/models` so `Langflow` and `SnowflakeLangflow` pass `reasoning_effort` via `extra_body` only when supported.
   - **Messages (`/messages/v1`):** Strips unsupported `thinking.type` blocks (such as `"adaptive"`) and paired `output_config.effort`; when `thinking.type == "enabled"`, strips `temperature`/`top_p` and guarantees `max_tokens > thinking.budget_tokens`; normalizes string `tool_choice` (`"auto"` / `"none"`).
2. **Ordered-Items SSE & `encrypted_content` Finalization (`stream_order.py` + `protocol.py`):**
   - On Responses streams (`response_stream = "ordered-items"`), accepts empty `""` or provisional initial `encrypted_content` on `response.output_item.added`, requires non-empty finalized `encrypted_content` on `response.output_item.done` matching `response.completed`, and backfills `response.output_item.added` so `langchain-openai`, `Langflow`, `SnowflakeLangflow`, `Hermes`, and `n8n` never fail with `Opaque reasoning changed`.
3. **Stateless Tool-Loop `ReplayCache` (`replay_cache.py`):**
   - Bounded LRU cache (`max_entries=512`, `ttl=3600s`) keyed by `call_id` / `tool_use.id` rehydrates `reasoning.encrypted_content` (Responses) and `thinking` / `signature` / `redacted_thinking` blocks (Messages) when stateless clients drop them between turns.
4. **Multi-Round Tool Call ID Deduplication (`reused_tool_ids` / `multiround_followup`):**
   - Models that reuse `call_0..call_N` across turns are validated per open batch and renamed across closed rounds (`call_0` &rarr; `call_0_r2`).
5. **1M+ Token Context & Compression Bounds (`app.py`):**
   - Proxy defaults `PROXY_MAX_BODY = 32 MiB`, `PROXY_MAX_RESPONSE = 32 MiB`, `PROXY_DEADLINE = 600s` (10 min), and `httpx.Timeout(180, connect=10, write=60, pool=5)`, while auxiliary context-compression calls on Responses set `reasoning={"effort": "low", "summary": "auto"}`.
6. **Zero-Touch Promotion, Revocation & Daily Autonomous Scouting:**
   - **Manual Promotion / Revocation (`scripts/promote_model.py`):** Package `PROFILE_QUALIFIED` profiles (`administrative-standard-v1`, 365-day validity) or `--revoke` disappeared models into the Registry stage inbox (`/inbox/`) for convergence within 30–60s without restarting services.
   - **Daily Autonomous Scouting (`scripts/daily_scout_and_promote.py` & `scripts/spcs_scout_worker.py`):** Compares daily `SHOW MODELS IN ACCOUNT` snapshots against `MODEL_SNAPSHOT_HISTORY`, qualifies new `CORTEX_BASE` models via `model_probe.campaign.Campaign`, promotes passing models, revokes disappeared models, writes every run report to `MODEL_SCOUTING_RUNS` / `V_LATEST_MODEL_SCOUTING_REPORT`, and triggers email alerts via `EMAIL_INTEGRATION` **exclusively when `ACTION_TAKEN = TRUE`**.

## Stopping Points

- Missing target account/host, credentials, or explicit user authorization before paid `--live` probes.
- Any request to execute `ALTER ACCOUNT`, change grants, modify production proxy services, or overwrite client defaults.
- Ambiguous failure where harness vs upstream behavior must be separated via a positive control before recommending promotion.
- Sending external notifications or publishing account-derived evidence without explicit user approval.

## Output

- Private append-only campaign directory (`0700` dir / `0600` files) containing `manifest.json`, `case-001.json .. case-039.json`, and `summary.json`.
- Structured Model / Protocol / Capability Matrix reporting `PASS`, `FAIL`, `BLOCKED`, or `NOT TESTED` with exact dates, versions, and evidence paths.
