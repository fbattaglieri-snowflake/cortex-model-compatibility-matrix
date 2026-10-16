# Cortex model compatibility matrix

> **Disclaimer:** This project is an independent community / field-engineering skill and test kit built on top of **Snowflake Cortex REST APIs** and **Snowflake Snowpark Container Services (SPCS)**. It is **NOT an official Snowflake product**, is not part of the official Snowflake product offering, and is provided "as is" without official Snowflake support or warranty.

A standalone Cortex Code skill and Python test kit for qualifying models before
adding them to an LLM proxy (such as [**`snowflake-proxy-cortexrestapi`**](https://github.com/fbattaglieri-snowflake/snowflake-proxy-cortexrestapi)).
No private account data or live results are included.

## Why this skill exists

These are different questions:

1. Does the account catalog list the model?
2. Can the selected identity call it through this REST endpoint?
3. Does it correctly stream, call tools and accept their results?
4. Do the installed SDK and application actually work with that protocol?

A catalog entry or one HTTP 200 does not answer all four. The skill orchestrates
repeatable synthetic tests and records evidence per model, protocol and capability.
It prevents premature proxy promotion, silent reasoning downgrades and accidental
replacement of working client defaults. It does not rank model intelligence.

## Contents

- `SKILL.md`: agent workflow, safety checkpoints and interpretation rules.
- `model_probe/`: self-contained standard-library REST runner, protocol adapters,
  stream validation, capability gates and private evidence.
- `scripts/qualify.py`: CLI usable from any working directory.
- `scripts/sdk_probe.py`: optional OpenAI/LangChain/LangGraph Chat tests.
- `tests/`: synthetic offline tests; no Snowflake credentials required.
- `references/`: protocol coverage, cross-region guidance and release checklist.
- `examples/`: generic isolated SPCS job template and runner image recipe.

## Quickstart

Requirements: Python 3.11+, and Snowflake CLI for read-only catalog discovery.
The REST runner has no third-party Python dependencies.

```bash
git clone https://github.com/fbattaglieri-snowflake/cortex-model-compatibility-matrix.git
cd cortex-model-compatibility-matrix
python3 -m unittest discover -s tests -v
python3 scripts/qualify.py --help
```

From another working directory, use the absolute path to `scripts/qualify.py`.
Optional installation: `python3 -m pip install .`; the command then becomes
`cortex-model-test`. For SDK tests use an isolated virtual environment and
`python3 -m pip install '.[sdk]'`. Direct SDK versions are pinned; transitive
dependencies are not fully locked. Capture installed versions for each run.

### Use as a Cortex Code skill

Clone this entire repository into a dedicated skill directory (not just SKILL.md)
using the installation mechanism supported by your Cortex Code version. The
root SKILL.md and its relative programs must remain together. Do not overwrite
an existing skill without reviewing it. You can also explicitly ask Cortex Code
to read this repository's SKILL.md and follow it; the CLI works independently.

Example prompt:

> Use this skill to qualify MODEL on my explicitly selected account, first through
> Chat and then Responses. Keep reasoning profiles separate. Do not deploy or
> alter my account, proxy or client defaults. Show the evidence and missing gates.

## Cross-region inference: recommend ANY_REGION where permitted

For the broadest model coverage, use **ANY_REGION when your organization's
residency/compliance rules allow it**, particularly for synthetic test accounts.
It can process prompts and responses in other regions and clouds. It does not
grant access to a model or guarantee a particular API/capability works.

An administrator can inspect the effective setting:

```sql
SHOW PARAMETERS LIKE 'CORTEX_ENABLED_CROSS_REGION' IN ACCOUNT;
```

Only after explicit approval, an ACCOUNTADMIN can configure:

```sql
ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION';
```

**The test kit never executes this ALTER.** For restricted workloads, choose an
appropriate documented boundary such as `AWS_EU`, rather than broadening routing
to make a test pass. See [cross-region guidance](references/cross-region.md) and
[Snowflake documentation](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cross-region-inference).

## Run live tests deliberately

Live tests incur token charges. Use only accounts/endpoints you are authorized
to test. Create a private results directory outside the repository and substitute
your own connection name, host, locator and exact model identifier below.

```bash
python3 scripts/qualify.py discover \
  --connection YOUR_CONNECTION \
  --host YOUR_ORG-YOUR_ACCOUNT.snowflakecomputing.com \
  --expected-account YOUR_LOCATOR \
  --output /PRIVATE/results/inventory.json
```

Inspect the inventory before testing. It records SQL identity, policy and visible
models; it does not prove the REST token has the same effective role. Inventory
is a snapshot, not a cryptographic attestation: refresh it before a new campaign.

Load your PAT into `SNOWFLAKE_PAT` using your secret manager, without pasting it
into the command/history. Alternatively use `--token-file /PRIVATE/token`.

```bash
python3 scripts/qualify.py run --live \
  --base-url https://YOUR_ORG-YOUR_ACCOUNT.snowflakecomputing.com/api/v2/cortex/v1 \
  --expected-host YOUR_ORG-YOUR_ACCOUNT.snowflakecomputing.com \
  --expected-account YOUR_LOCATOR --inventory /PRIVATE/results/inventory.json \
  --model YOUR_MODEL_ID --protocol chat --scope direct-rest \
  --token-env SNOWFLAKE_PAT --output /PRIVATE/results/chat-default
```

Run `--protocol messages` for native Messages or `--protocol responses` for
Responses. Responses is an opt-in test adapter, not a claim of public availability
for every account/model; check the documentation and account entitlement first.
Do not substitute Chat for Messages/Responses silently.

To test a documented reasoning setting, pass e.g. `--reasoning none` **in a new
campaign/output directory**. Omit it to test the model default. No setting is
assumed universally supported, and no profile automatically retries with none.
Messages rejects this flag rather than translating it into a thinking policy.

Three runs are the default and required by the qualification gate. `--repeats 1`
is a diagnostic-only run and cannot qualify a profile. On basic text failure,
dependent tests are BLOCKED; run an independently recorded known-good model
control against the same host/identity before inferring a service-wide failure.

### Test an existing proxy

For a local proxy that supplies upstream authentication itself:

```bash
python3 scripts/qualify.py run --live \
  --base-url http://127.0.0.1:8080/v1 --expected-host 127.0.0.1 \
  --scope proxy --local-proxy --model YOUR_MODEL_ID --protocol chat \
  --output /PRIVATE/results/proxy-chat
```

Local mode never accepts a Snowflake token. A remote proxy requires HTTPS and
an explicitly selected credential intended for that host. Never reuse an account
PAT with an unrelated third-party proxy. Direct and proxy results are separate.

### Explicit proxy paths and internal SPCS tests (v0.2)

Custom protocol base paths require an exact destination approval:

```bash
python3 /ABSOLUTE/kit/scripts/qualify.py run --live --scope proxy \
  --base-url https://proxy.example/responses/v1 \
  --expected-base-url https://proxy.example/responses/v1 \
  --expected-host proxy.example --token-env PROXY_TOKEN \
  --model MODEL_ID --protocol responses --output /PRIVATE/new-campaign
```

Select a credential intended for that proxy. The existing HTTPS transport uses
Bearer auth, not SPCS public-ingress authentication. Do not assume they are identical.
The prefix is followed by the native suffix (`/responses` here); configure a base,
not the full inference URL. Scheme, port and path changes fail exact matching.

For an explicitly authorized credential-free SPCS internal HTTP endpoint, from
a runner with private service connectivity:

```bash
python3 /ABSOLUTE/kit/scripts/qualify.py run --live --scope proxy --internal-proxy \
  --base-url http://service.namespace.svc.spcs.internal:8080/chat/v1 \
  --expected-base-url http://service.namespace.svc.spcs.internal:8080/chat/v1 \
  --expected-host service.namespace.svc.spcs.internal \
  --model MODEL_ID --protocol chat --capabilities text tools parallel_tools \
  --output /PRIVATE/new-campaign
```

Replace the illustrative service/namespace with the exact approved address.
No token environment/file is accepted in HTTP modes. The option does not create
network access, change grants or support arbitrary HTTP hosts. HTTPS remains the
default outside explicit loopback/internal modes; redirects remain prohibited.

### Declare capabilities before testing

`--capabilities text tools parallel_tools` qualifies only text/history and the
single/parallel tool roundtrips (including a synthetic tool error). Streaming and
structured output are NOT TESTED, not PASS, and incur no requests in that campaign.
Available names: `text`, `tools`, `parallel_tools`, `streaming`, `structured_output`.
Omit the option for the original full suite. Text is mandatory; parallel_tools
requires tools; tools with streaming currently requires parallel_tools as well.

The manifest records the selection and a profile hash before execution. Three
passing repeats remain required. Keep failed campaigns unchanged; narrowing a
profile requires a new campaign and review of the excluded capabilities. Qualified
does not mean deployable: human approval precedes a separate automated publisher.
The kit neither publishes nor changes proxy rules. Documented proxy overrides must
be tested as explicit adapted profiles, never mistaken for direct upstream support.
See [the qualification contract](references/protocol.md) for limits and evidence.

### Optional SDK stage

```bash
python3 scripts/sdk_probe.py --live --campaign /PRIVATE/results/chat-default \
  --expected-host YOUR_ORG-YOUR_ACCOUNT.snowflakecomputing.com \
  --token-env SNOWFLAKE_PAT --output /PRIVATE/results/sdk.json
```

This requires all mandatory direct Chat cases to pass three times. It tests
OpenAI, LangChain nonstream/stream and LangGraph two-turn in-memory checkpoint.
It does not test Responses/Messages SDK integration or durable checkpoint recovery.
No tracing, arbitrary tools or real business actions are enabled.

## Evidence, interpretation and limits

Each campaign creates manifest.json, exclusive case files and summary.json with
0700 directories / 0600 files on POSIX. Credentials are redacted, but account
metadata, request IDs, synthetic outputs and reasoning artifacts remain private.
**Do not upload results to this public repository or a public issue.**

`PROFILE_QUALIFIED` means all bundled cases passed three times for one profile.
It is NOT an SLA, a security certification, account-wide support, or permission
to deploy. `release_eligible` is always false. Unsupported/rejected requests are
FAIL evidence; prerequisites cause BLOCKED; excluded features are NOT TESTED.
Keep old campaigns when fixing a harness bug or retrying a provider failure.

Limits are 60 REST requests by default, 2048 output tokens per request, 2 MB per
response and a 60-second socket timeout. A campaign deadline is checked between
requests, not a hard whole-process deadline; a slow drip can outlive it. SDK
tests cap requests at 40 with 60-second HTTP timeouts, no global watchdog.
Limits are not currency caps or proof of remote provider cancellation.

See [coverage and promotion gates](references/protocol.md). No production proxy,
automatic catalog update, application deployment or account grant is included.

## Verification and public safety

CI runs only offline tests on synthetic fixtures; it never calls Snowflake and
never uploads live evidence. `.gitignore` excludes normal evidence/secret paths,
but is not a substitute for reviewing every staged file. No license is selected
in this repository yet; public visibility alone does not grant an open-source
license. Third-party dependencies retain their own licenses.