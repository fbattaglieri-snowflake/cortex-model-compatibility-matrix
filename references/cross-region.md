# Cross-region inference

Documentation checked on 2026-10-05:

- https://docs.snowflake.com/en/user-guide/snowflake-cortex/cross-region-inference
- https://docs.snowflake.com/en/release-notes/bcr-bundles/2026_06/bcr-2376
- https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-rest-api

Recommend `ANY_REGION` for maximum coverage where permitted by the workload's
data-residency and compliance requirements. Requests may be processed in any
supported Snowflake region and cloud. Snowflake documents transient transfer of
prompt/response payloads and no persistence in the processing region. This does
not mean the payload stays in the account's home region.

The parameter is account-level, not session/user-level; ACCOUNTADMIN changes it.
First inspect the effective value using SHOW PARAMETERS. Present any proposed
ALTER separately and require administrator approval. Testing never applies it.
Do not assume the default: it depends on account/organization creation and
deployment behavior changes. An explicit account value overrides defaults.

Alternative boundaries include cloud-specific AWS_GLOBAL/AZURE_GLOBAL/GCP_GLOBAL
and geography-specific choices such as AWS_EU. Select from current documentation.
Government/VPS or other restricted environments require their specific guidance;
do not apply commercial-account assumptions blindly.

ANY_REGION does not override privileges, provider eligibility, private-preview
enablement, endpoint availability or model tool/reasoning compatibility. A model
listed in metadata can still reject REST. Report the effective policy alongside
tests rather than promising ANY_REGION fixes all availability problems.

The harness does not add undocumented cross-region request headers or execute
AI_COMPLETE. REST and SQL inference remain distinct surfaces.