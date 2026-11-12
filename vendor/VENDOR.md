# Vendored: PayPal Agent Toolkit (Python `shared` subtree)

**Source:** https://github.com/paypal/agent-toolkit — PayPal's official
agent toolkit.
**Pin:** package version 1.11.0 (`python/pyproject.toml`), repo commit
`a3aa963960caf32912691a759879a8ce7a6018b2` (main, fetched 2026-11-04).
**Licence:** Apache License 2.0 — full text at
`paypal_agent_toolkit/LICENSE` (verbatim from the repo root). Redistribution
in this form is permitted under that licence; this file is the attribution
and provenance record.

## What was taken (verbatim, unmodified)

Only the framework-free core — the parts the Orders path actually imports:

```
paypal_agent_toolkit/__init__.py            (empty upstream)
paypal_agent_toolkit/LICENSE                (Apache-2.0)
paypal_agent_toolkit/shared/__init__.py     (empty upstream)
paypal_agent_toolkit/shared/configuration.py  Context / Configuration
paypal_agent_toolkit/shared/constants.py      sandbox/live base URLs
paypal_agent_toolkit/shared/regex.py          resource-id patterns
paypal_agent_toolkit/shared/telemetry.py      User-Agent builder (stdlib only)
paypal_agent_toolkit/shared/logger_util.py    masked-payload logging
paypal_agent_toolkit/shared/paypal_client.py  OAuth + HTTP transport (requests)
paypal_agent_toolkit/shared/orders/__init__.py  (empty upstream)
paypal_agent_toolkit/shared/orders/parameters.py    pydantic tool schemas
paypal_agent_toolkit/shared/orders/payload_util.py  Orders payload builder
paypal_agent_toolkit/shared/orders/tool_handlers.py create/capture/get handlers
```

Runtime dependencies of this subtree: `pydantic>=2.10` and `requests`
only. No file was edited; if a file here differs from upstream at the pin
above, that is a defect — diff it and restore.

## What was deliberately NOT taken

The framework adapters (`langchain/`, `crewai/`, `openai/`, `bedrock/`)
and the other product areas (invoices, subscriptions, disputes,
tracking, transactions, insights). Installing the toolkit from PyPI would
pull `langchain`, `crewai-tools` and `openai-agents` in as hard
dependencies; none of that belongs in this project's payment path. The
gate never calls an LLM framework — it calls the toolkit's handlers
directly (see `../paypal_toolkit_client.py`).

Also excluded: `shared/tools.py` (the agent tool registry) and
`shared/orders/prompts.py` — prompt/registry material for LLM callers,
unused by the handlers.

## Upgrade path

`pip install paypal-agent-toolkit==<version>`, delete this `vendor/`
directory, and the imports in `paypal_toolkit_client.py` resolve to the
installed package unchanged (same package name, same module paths). Re-run
the full test suite after upgrading — the suite pins two upstream
behaviours on purpose (see `test_paypal_toolkit_client.py`).
