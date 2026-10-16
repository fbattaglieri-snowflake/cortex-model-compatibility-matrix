# Qualification contract v2

## REST coverage (each selected protocol, each run)

- Exact text response and valid completion/stop status.
- SSE framing, completion, text and tool reconstruction.
- Conversation history fixture.
- Single and parallel function calls with distinct identities, strict synthetic
  arguments and correct tool-result pairing; final sums must match.
- Parallel streaming tool calls and streaming result roundtrip.
- Explicit synthetic tool failure; model must return UNAVAILABLE, not fabricate.
- Structured output matching a fixed schema, including a prompt requesting a
  forbidden field. This is a fixture-specific validator, not a general schema engine.

No tool executes arbitrary code, network operations or user data access.
Unknown tool names/arguments fail before dispatch. Messages signed thinking
blocks and Responses output/reasoning are preserved for followup requests.
Responses streams use the completed response as authoritative output; function
argument delta-by-delta parity is not yet separately validated. SSE is reconstructed
after a bounded read: not a latency/backpressure/real-time incremental transport test.
Usage events are recorded individually, never summed into a billing estimate.

The Responses decoder accepts one optional `[DONE]` sentinel only AFTER a valid
`response.completed`. The sentinel alone, a duplicate sentinel, any later JSON
payload, failure or incomplete terminal still fail. This matches the observed
Cortex framing and the Standard validator; it never manufactures completion.
Decoder ValueErrors retain bounded raw response metadata in private case evidence.
Earlier campaigns remain unchanged; offline replay does not qualify unrun cases.

## Missing coverage

Vision, audio, embeddings, cache-hit validation, forced/required tool choice,
model quality benchmarks, concurrency/load, proxy disconnect/backpressure,
service token natural rotation, durable memory, full application E2E and SQL
inference are NOT TESTED by this release. OAuth token files are reread per request;
that behavior alone is not a natural rotation certification.

The optional SDK stage covers Chat only. Actual n8n, Hermes and Langflow versions,
providers, saved workflows and UI selection must be verified independently.
This public kit does not claim to reproduce every private historical test.
The campaign deadline is checked between requests, not enforced by a process-wide
watchdog. Messages thinking profiles are not parametrized by the Chat reasoning
flag. No proxy parameter-override engine or transformation tests are supplied.

## Gate semantics

PASS: the exact fixture and protocol assertions held. FAIL: the request or its
assertions failed. BLOCKED: prerequisite/budget prevents execution. NOT TESTED:
outside the selected suite. Three complete passing runs qualify only that profile.
Reasoning/profile differences require separate campaigns. No model aliases,
HTTP retries, parameter downgrades or protocol conversions occur automatically.

## Capability-scoped campaigns

Declare `--capabilities` before execution; omission preserves the full v1 suite.
`text` is mandatory. The manifest (schema 2) persists the normalized selection,
derived required cases, source hashes, destination policy and profile SHA-256
before any inference. The profile hash covers model/protocol/reasoning/selection,
not the full release artifact: it is not a signature or human approval record.

| Capability | Required cases |
| --- | --- |
| text | text, history |
| tools | single, single_roundtrip, error_setup, error_roundtrip |
| parallel_tools | parallel, parallel_roundtrip; requires tools |
| streaming | stream_text; with parallel_tools also stream_parallel and its roundtrip |
| structured_output | structured, structured_negative |

The current suite has parallel-stream tool fixtures, not an independent single-tool
stream suite: `tools + streaming` requires `parallel_tools`. Do not infer untested
combinations. Excluded cases are recorded for every repeat as NOT TESTED without
making their requests. Required prerequisites/budget failures remain BLOCKED.
All required cases must pass three times; excluded cases must be NOT TESTED, and
missing, duplicate or unexpected rows fail the gate. A failure cannot be ignored
by relabeling its capability optional after execution. Keep old evidence and run
a new explicitly scoped campaign for a narrower profile. Missing capability is
not proven unsupported: it simply is not qualified here.

Summary `qualified_capabilities` is populated only on whole-profile success.
`release_eligible` stays false. Human approval and a separate publisher are still
required; no registry schema integration or publication controller is implemented.
The optional SDK stage still requires the FULL direct Chat suite: narrower
profiles intentionally do not unlock SDK tests of capabilities they did not prove.

## Proxy destination policy

Direct/service REST retains the existing HTTPS/path checks. For proxy scope,
`--expected-base-url` is explicit approval of the exact base scheme/host/port/path;
it enables safe custom prefixes without changing the three native endpoint suffixes.
Credentials, query strings, fragments, whitespace, encoded paths, dot segments and
empty internal path segments are rejected. Redirects and environment proxies remain
disabled. No arbitrary destination is discovered or approved by the runner.

`--internal-proxy` permits HTTP only for an exact approved `*.svc.spcs.internal`
base URL and prohibits token sources. It must run in a network that can resolve
and reach that service; it neither proves private routing nor creates network access.
Authenticated internal endpoints must use an appropriate separately designed secure
path, not send credentials with this option. Local loopback remains an independent
explicit mode. HTTPS authentication remains the existing Bearer/Snowflake-header
transport, not generic public-ingress or x-api-key authentication support.

## Release checklist (manual, not implemented automation)

1. Exact model/protocol profile qualified; all required evidence recent and reviewed.
2. Positive control and harness issues distinguished from actual model errors.
3. SDK and packaged proxy tested with their actual versions and service identity.
4. Immutable image/catalog, dependency lock, SBOM and vulnerability gate reviewed.
5. Isolated canary, actual client tests, state preservation and rollback verified:
   - Validate universal `ProfileV2` client normalization (`normalize_client_options=True`,
     token range `1..128000`, `response_stream="ordered-items"` on Responses, automatic
     `store=false`, removal of empty `"text": {}` objects, `reasoning_effort` normalization
     on Chat, and `thinking` vs `temperature`/`top_p` normalization on Messages).
   - Verify `ReplayCache` rehydration for stateless clients (such as unpatched n8n Agent
     engine serialization) that drop `reasoning.encrypted_content` (Responses) or
     `thinking`/`signature`/`redacted_thinking` blocks (Messages) across tool turns.
   - Verify multi-round tool call ID handling (`reused_tool_ids` / `multiround_followup`):
     models that emit per-response sequential tool IDs (`call_0..call_N` on every round)
     require history validators to enforce uniqueness per open pending batch and automatic
     cross-round deduplication (`call_0` -> `call_0_r2`) so round 2+ does not fail.
   - Verify output-token and reasoning-budget interaction on long contexts: the 2048-token
     budget used by short synthetic probes must not be hardcoded into client requests on
     Responses/Chat when optional, because Responses `max_output_tokens` counts
     `reasoning_tokens + output_tokens` and can truncate `function_call` JSON arguments
     mid-string after long reasoning blocks (`status="incomplete"`).
6. Human approves the precise profile/evidence revision; publish to the authorized
   Standard Registry using `scripts/promote_model.py` from
   `snowflake-proxy-cortexrestapi` (`administrative-standard-v1`, 365-day validity,
   automatic stage-inbox ingestion within 30s without service restarts), retaining
   Legacy, existing Next and client defaults. No automatic promotion from test PASS
   without explicit human approval.
7. Post-deployment verification and periodic bounded retesting.

No report from this package automatically authorizes any of these writes.