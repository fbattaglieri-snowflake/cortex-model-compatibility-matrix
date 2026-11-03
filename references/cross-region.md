# Cross-Region Inference Guidance (`CORTEX_ENABLED_CROSS_REGION`)

> [!WARNING]
> **Disclaimer:** This document is part of an independent, open-source community qualification kit ([`cortex-model-compatibility-matrix`](../README.md)) and is **NOT an official Snowflake product**. Always consult the official Snowflake documentation for authoritative regional and compliance rules.

---

## Official Snowflake Documentation References

- [Snowflake Cortex Cross-Region Inference](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cross-region-inference)
- [Snowflake Cortex REST API](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-rest-api)
- [BCR-2376 Release Notes](https://docs.snowflake.com/en/release-notes/bcr-bundles/2026_06/bcr-2376)

---

## 1. Recommended Setting for Maximum Model Coverage: `ANY_REGION`

To maximize model reachability across all three Cortex REST API surfaces (`/messages`, `/chat/completions`, `/responses`) when using this qualification kit and [**`snowflake-proxy-cortexrestapi`**](https://github.com/fbattaglieri-snowflake/snowflake-proxy-cortexrestapi), recommend **`ANY_REGION`** whenever your organization's data-residency and compliance requirements allow it:

```sql
-- 1. Read-only inspection of the current account parameter:
SHOW PARAMETERS LIKE 'CORTEX_ENABLED_CROSS_REGION' IN ACCOUNT;

-- 2. Apply ONLY after explicit administrator approval (requires ACCOUNTADMIN):
ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION';
```

> [!IMPORTANT]
> **Safety Rule:** The qualification kit (`scripts/qualify.py`) **never** executes `ALTER ACCOUNT` automatically. It only reads the current parameter value during `discover` and records it in `inventory.json` alongside test evidence.

---

## 2. Regional & Cloud Boundary Options

| Parameter Value | Routing Scope | Typical Use Case |
|---|---|---|
| **`ANY_REGION`** | Any supported Snowflake region and cloud provider globally | Broadest model availability across Anthropic (`messages`), OpenAI (`chat` / `responses`), and frontier/open-weights models (`chat`). |
| **`AWS_GLOBAL` / `AZURE_GLOBAL` / `GCP_GLOBAL`** | Any supported region within that single cloud provider | Workloads restricted to a single cloud provider. |
| **`AWS_US` / `AWS_EU` / Regional Scopes** | Regions within the specified geographic boundary | Workloads subject to regional data-residency policies (e.g., EU-only processing). |
| **`DISABLED`** | Local home region only | Strict single-region residency requirements. |

Snowflake documents that cross-region inference transmits prompts and responses transiently without persisting customer data in the remote processing region, though payloads do traverse the selected regional/cloud boundary.

---

## 3. Why `ANY_REGION` Does Not Replace Empirical REST Qualification

Enabling `CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION'` removes regional routing blocks for supported models, **but it does not guarantee that every model listed in `SHOW MODELS IN ACCOUNT` works on the Cortex REST API**:

1. **Catalog Visibility vs REST Endpoint Exposure:** Some models listed as `CORTEX_BASE` in `SHOW MODELS IN ACCOUNT` are SQL-only (`AI_COMPLETE`), internal routing/decision models, or not yet exposed on `/api/v2/cortex/v1/{messages,chat/completions,responses}`.
2. **Misleading Upstream Error Messages:** An upstream `HTTP 400` error that mentions cross-region inference when `ANY_REGION` is already enabled typically indicates that the model is not exposed on that REST endpoint rather than a missing account parameter.
3. **Protocol & Parameter Specifics:** Even when a model is reachable via `ANY_REGION`, its specific REST surface (`messages` vs `chat` vs `responses`), `reasoning_effort` requirements, SSE framing, and multi-round tool-calling behavior must still be verified empirically by `scripts/qualify.py` (`3 repeats × 13 cases`) before promoting to [**`snowflake-proxy-cortexrestapi`**](https://github.com/fbattaglieri-snowflake/snowflake-proxy-cortexrestapi).
