# Qualification contract v1

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

## Missing coverage

Vision, audio, embeddings, cache-hit validation, forced/required tool choice,
model quality benchmarks, concurrency/load, proxy disconnect/backpressure,
service token natural rotation, durable memory, full application E2E and SQL
inference are NOT TESTED by this release. OAuth token files are reread per request;
that behavior alone is not a natural rotation certification.

The optional SDK stage covers Chat only. Actual n8n, Hermes and Langflow versions,
providers, saved workflows and UI selection must be verified independently.
This public kit does not claim to reproduce every private historical test.

## Gate semantics

PASS: the exact fixture and protocol assertions held. FAIL: the request or its
assertions failed. BLOCKED: prerequisite/budget prevents execution. NOT TESTED:
outside the selected suite. Three complete passing runs qualify only that profile.
Reasoning/profile differences require separate campaigns. No model aliases,
HTTP retries, parameter downgrades or protocol conversions occur automatically.

## Release checklist (manual, not implemented automation)

1. Exact model/protocol profile qualified; all required evidence recent and reviewed.
2. Positive control and harness issues distinguished from actual model errors.
3. SDK and packaged proxy tested with their actual versions and service identity.
4. Immutable image/catalog, dependency lock, SBOM and vulnerability gate reviewed.
5. Isolated canary, actual client tests, state preservation and rollback verified.
6. Human approves promotion; update Next only, retain Legacy and existing defaults.
7. Post-deployment verification and periodic bounded retesting.

No report from this package automatically authorizes any of these writes.