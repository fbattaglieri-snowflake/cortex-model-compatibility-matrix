# Qualification Contract v2 & Proxy Compliance Reference

> [!WARNING]
> **Disclaimer:** This project is an independent, open-source community and field-engineering qualification kit built on top of Snowflake Cortex REST APIs and Snowpark Container Services (SPCS). It is **NOT an official Snowflake product** and is released under the **[MIT License](../LICENSE)**.

---

## 1. Architecture & Dependency with [`snowflake-proxy-cortexrestapi`](https://github.com/fbattaglieri-snowflake/snowflake-proxy-cortexrestapi)

`cortex-model-compatibility-matrix` (`model_probe`) is the authoritative qualification and evidence engine used by [**`snowflake-proxy-cortexrestapi`**](https://github.com/fbattaglieri-snowflake/snowflake-proxy-cortexrestapi):

1. **`src/llm_proxy_standard/evidence.py` (`import_campaign`):** Imports `model_probe` and verifies `manifest["schema_version"] == 2`, `manifest["version"] == model_probe.__version__`, byte-exact `manifest["source_sha256"]` against `model_probe/*.py`, `manifest["profile_sha256"]`, `repeats == 3`, `retries == 0`, and `gate(rows, 3, caps)`.
2. **`scripts/daily_scout_and_promote.py` & `scripts/spcs_scout_worker.py` (`qualify_model_on_channel`):** Imports `Campaign` and `Transport` from `model_probe` to qualify every newly discovered `CORTEX_BASE` model across `messages`, `chat`, and `responses` before zero-touch promotion.
3. **`Dockerfile.qualification`:** Copies `model_probe` directly into `/opt/proxy/model_probe` (`COPY --from=kit model_probe /opt/proxy/model_probe`) inside the SPCS qualification and registry container image.
4. **`scripts/promote_model.py`:** Packages `PROFILE_QUALIFIED` profiles into `ProfileV2` (`administrative-standard-v1`, 365-day validity) or builds administrative revocation packages (`--revoke`) for the Registry stage inbox (`/inbox/`).

---

## 2. REST Coverage (13 Synthetic Cases × 3 Repeats per Campaign)

| Case ID | Capability Group | Prerequisite | Protocol & Semantic Assertion |
|---|---|---|---|
| `text` | `text` *(mandatory)* | — | Exact text `"OK"`, valid stop status (`end_turn`, `stop`, `completed`), no tool calls. |
| `stream_text` | `streaming` | `text` | Valid `text/event-stream` SSE framing, terminal completion event, reconstructed text `"OK"`. |
| `history` | `text` *(mandatory)* | `text` | Multi-turn context recall (`"Remember BLUE7."` &rarr; `"Noted."` &rarr; `"BLUE7"`). |
| `single` | `tools` | `text` | Single call to `lookup_fixture` with `{"key": "alpha"}` and unique tool call ID. |
| `single_roundtrip` | `tools` | `single` | Preserves assistant turn + opaque reasoning/thinking, injects `"17"`, verifies final `"17"`. |
| `parallel` | `parallel_tools` | `text` | Two parallel calls (`alpha` and `beta`) in one turn with distinct tool call IDs. |
| `parallel_roundtrip` | `parallel_tools` | `parallel` | Pairs outputs (`17` and `25`) by tool call ID and verifies numeric sum `"42"`. |
| `stream_parallel` | `streaming` + `parallel_tools` | `text` | Reconstructs two parallel tool calls from SSE deltas/events with distinct IDs. |
| `stream_parallel_roundtrip` | `streaming` + `parallel_tools` | `stream_parallel` | Roundtrip with streamed parallel tool outputs; verifies final answer `"42"`. |
| `error_setup` | `tools` | `text` | Calls `lookup_fixture` (`alpha`) under instruction not to retry on failure. |
| `error_roundtrip` | `tools` | `error_setup` | Injects synthetic error (`is_error: true` on Messages); model must return `"UNAVAILABLE"` without fabricating a value. |
| `structured` | `structured_output` | `text` | Enforces strict JSON schema (`{"ok": true, "result": 42}`, `additionalProperties: false`). |
| `structured_negative` | `structured_output` | `text` | Prompts for an extra `forbidden` field under strict schema; verifies extra field is omitted. |

### Protocol-Specific Stream & State Rules

- **No Arbitrary Code or Data Access:** Synthetic tools never execute shell commands, network calls, or database queries. Unknown tool names or arguments outside `{"key": "alpha" | "beta"}` fail immediately.
- **Opaque Reasoning & Thinking Continuity:** `followup()` preserves full `response["output"]` (including `reasoning.encrypted_content`) on `responses` and signed `thinking` / `redacted_thinking` blocks on `messages`.
- **Multi-Round Tool Call ID Deduplication (`reused_tool_ids` & `multiround_followup`):** Models that emit sequential per-response tool IDs (`call_0..call_N` on every round) are detected by `reused_tool_ids()` and deterministically renamed across closed rounds (`call_0` &rarr; `call_0_r2`) by `multiround_followup()` (and in production by `snowflake-proxy-cortexrestapi/src/llm_proxy_standard/rules.py`).
- **Responses SSE Sentinel Handling:** `decode_stream(..., "responses")` accepts at most one optional `[DONE]` sentinel **after** a valid `response.completed` event. A bare `[DONE]`, duplicate `[DONE]`, trailing JSON event after completion, `response.failed`, or `response.incomplete` raises `ValueError` while preserving bounded raw response metadata in the failed case file.

---

## 3. Out-of-Scope Dimensions (`NOT TESTED`)

Vision, audio, embeddings, prompt-cache hit ratios, forced/required `tool_choice`, subjective intelligence benchmarks, high-concurrency load testing, natural long-lived OAuth token rotation, durable database checkpoint recovery, and SQL `AI_COMPLETE` inference are outside the scope of this synthetic REST runner.

- The optional `scripts/sdk_probe.py` stage tests direct `chat` campaigns across `openai`, `langchain` (non-stream and stream), and `langgraph` (`InMemorySaver`).
- Multi-protocol consumer loops (**n8n**, **Hermes**, **Langflow**, **SnowflakeLangflow**, **LangChain / LangGraph**) are validated through the companion test suite in [**`snowflake-proxy-cortexrestapi`**](https://github.com/fbattaglieri-snowflake/snowflake-proxy-cortexrestapi) (`91/91` offline unit & integration tests).

---

## 4. Gate Semantics & Capability Dependencies

- **`PASS`:** Exact fixture and protocol assertions held.
- **`FAIL`:** HTTP rejection (`HTTP_REJECTION`), malformed SSE/JSON (`ValueError`), or wrong output (`FIXTURE_MISMATCH`).
- **`BLOCKED`:** Prerequisite case (`text` or tool setup) failed, or campaign request/time budget was exhausted.
- **`NOT TESTED`:** Capability was intentionally excluded via `--capabilities` before the campaign started.

| Capability | Required Cases | Dependency Rule |
|---|---|---|
| `text` | `text`, `history` | Mandatory in every campaign. |
| `tools` | `single`, `single_roundtrip`, `error_setup`, `error_roundtrip` | Requires `text`. |
| `parallel_tools` | `parallel`, `parallel_roundtrip` | Requires `tools`. |
| `streaming` | `stream_text` (+ `stream_parallel`, `stream_parallel_roundtrip` when `parallel_tools` is selected) | If combined with `tools`, requires `parallel_tools`. |
| `structured_output` | `structured`, `structured_negative` | Requires `text`. |

All required cases must pass all 3 repeats (`repeats = 3`, `retries = 0`). Excluded capabilities are recorded as `NOT TESTED` without issuing HTTP requests. Historical failed campaigns must never be edited or overwritten; narrowing a capability profile requires running a new campaign in a fresh directory.

---

## 5. Proxy Destination Policy (`--scope proxy`)

- **Direct & Service REST (`direct-rest`, `service-rest`):** Enforce `https://<expected-host>/api/v2/cortex/v1` with no redirects (`NoRedirect`).
- **Explicit Proxy Base URL (`--expected-base-url`):** Approves the exact `<scheme>://<host>:<port>/<path>` prefix (e.g., `/chat/v1`, `/responses/v1`, `/messages/v1`) before appending `/chat/completions`, `/responses`, or `/messages`.
- **Credential-Free Internal SPCS HTTP (`--internal-proxy`):** Permits `http://` **only** when `--expected-base-url` targets an explicit `*.svc.spcs.internal` hostname and rejects any `--token-env` or `--token-file` argument so credentials are never transmitted over plaintext HTTP.
- **Local Loopback (`--local-proxy`):** Permits `http://localhost`, `http://127.0.0.1`, or `http://[::1]` without credentials.

---

## 6. Proxy Compliance, Promotion & Daily Scouting Checklist

When qualifying models for [**`snowflake-proxy-cortexrestapi`**](https://github.com/fbattaglieri-snowflake/snowflake-proxy-cortexrestapi), verify the following end-to-end checklist:

1. **Exact Profile Qualification:** Confirm `status == "PROFILE_QUALIFIED"` (`3/3 PASS` across all required cases) or core agentic qualification (`33/33 PASS` on `text`, `tools`, `parallel_tools`, `streaming`), distinguishing upstream rejections from positive controls.
2. **Universal `ProfileV2` Client Normalization (`normalize_client_options = True` in `rules.py`):**
   - **Token Ranges (`1..128000`):** Clamps `max_tokens`, `max_completion_tokens`, and `max_output_tokens` to `1..128000`; defaults `max_tokens = 4096` on Messages when omitted; leaves `max_output_tokens` unset on Responses when omitted so long reasoning chains never truncate downstream `function_call` JSON arguments (`status="incomplete"`).
   - **Responses (`/responses/v1`):** Forces `store = false`, injects `include = ["reasoning.encrypted_content"]`, strips empty `"text": {}` and `prompt_cache_retention`, strips `temperature`/`top_p` on reasoning models, clamps out-of-domain `reasoning.effort` (`"none"`/`"minimal"` &rarr; `"low"`) and `reasoning.summary`, and enables `response_stream = "ordered-items"` (`stream_order.py` + `protocol.py`), finalizing `encrypted_content` at `response.output_item.done` (matching `response.completed`) and backfilling `response.output_item.added`.
   - **Chat (`/chat/v1`):** Resolves `max_tokens` + `max_completion_tokens` conflicts, forces `reasoning_effort = "none"` on models that require it, strips `reasoning_effort` on Chat models that reject it, and publishes `metadata.constraints` on `GET /chat/v1/models` so `Langflow` and `SnowflakeLangflow` pass `reasoning_effort` via `extra_body` only when supported.
   - **Messages (`/messages/v1`):** Strips unsupported `thinking.type` blocks (such as `"adaptive"`) and paired `output_config.effort`; when `thinking.type == "enabled"`, strips `temperature`/`top_p` and ensures `max_tokens > thinking.budget_tokens`; normalizes string `tool_choice` (`"auto"` / `"none"`).
3. **Stateless `ReplayCache` Continuity (`replay_cache.py`):**
   - Bounded LRU cache (`max_entries=512`, `ttl=3600s`) keyed by `call_id` / `tool_use.id` rehydrates `reasoning.encrypted_content` (Responses) and `thinking` / `signature` / `redacted_thinking` blocks (Messages) when dropped by stateless clients (such as n8n Agent JSON serialization).
4. **Multi-Round Tool Call ID Deduplication (`reused_tool_ids` / `multiround_followup`):**
   - Enforces per-batch tool ID uniqueness and renames reused IDs across closed rounds (`call_0` &rarr; `call_0_r2`).
5. **1M+ Token Context & Compression Bounds (`app.py`):**
   - Proxy defaults `PROXY_MAX_BODY = 32 MiB`, `PROXY_MAX_RESPONSE = 32 MiB`, `PROXY_DEADLINE = 600s`, `PROXY_SEND_TIMEOUT = 30s`, and `httpx.Timeout(180, connect=10, write=60, pool=5)`, while auxiliary context-compression calls on Responses pass `reasoning={"effort": "low", "summary": "auto"}`.
6. **Zero-Touch Promotion & Revocation (`promote_model.py`):**
   - Promote approved models via `scripts/promote_model.py` (`administrative-standard-v1`, 365-day validity) or revoke retired models via `scripts/promote_model.py --revoke` into the Registry stage inbox (`/inbox/`) for automatic ingestion within 30–60s without restarting services.
7. **Autonomous Daily Scouting (`daily_scout_and_promote.py` & `spcs_scout_worker.py`):**
   - Compares daily `SHOW MODELS IN ACCOUNT` snapshots against `MODEL_SNAPSHOT_HISTORY`, qualifies new `CORTEX_BASE` models, promotes passing profiles, revokes disappeared models, records every run in `MODEL_SCOUTING_RUNS` / `V_LATEST_MODEL_SCOUTING_REPORT`, and sends email notifications via `EMAIL_INTEGRATION` **strictly when `ACTION_TAKEN = TRUE`**.
