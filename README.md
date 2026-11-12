# SiteBefore, settled by a verified agent

**An AI agent proposes the charge. A deterministic gate verifies it against the approved quote. Only then does PayPal settle it.**

SiteBefore is an agent-run website service: a client approves a quote (a website build, then a monthly care plan), and a billing agent drafts the charges. Agents are good at drafting and bad at being trusted — the failure mode is quiet. The agent doesn't steal; it *errs*. It re-charges last month's one-time build fee inside this month's care plan. It bundles an add-on nobody quoted. It sends the right amount to the wrong payee. In a normal agent stack, nothing checks the draft against the one document that defines what should be charged: **the approved quote**.

This project is the settlement layer that fixes that. It is **Claim Court** — the verdict gate at the commerce surface of the why-agent project — applied to SiteBefore's billing: every proposed charge is graded against the quote before PayPal ever sees it.

**The example client, disclosed.** The demo's job is the website redesign + care plan quoted for **Shenail Hair Salon & Nail Bar** (shenailhairlounge.ca), a real salon in Niagara Falls and SiteBefore's **family pilot client** — disclosed here, in the demo output, and in the submission. Only the salon's public facts (name, city, website) are used. The scenario built around it is **simulated end to end**: the quote is the demo's illustrative quote, every payment runs the mock/sandbox path below, and nothing shown is a real transaction, revenue, traction, or a live customer deployment. The salon has not paid through this system.

## What it does

1. **The agent proposes.** A payment draft arrives with payee, currency, total, and itemised lines.
2. **The comparator grades.** A deterministic grader (no model in the loop, integer cents end to end) compares every claim in the draft — amount, currency, payee, each line — against the approved quote and returns a verdict in a fixed vocabulary:
   - **CORROBORATED** — every claim matches the evidence.
   - **PARTIAL** — something in the draft is outside the evidence (e.g. an unquoted add-on).
   - **CONFLICTED** — the draft contradicts the evidence (wrong amount for this charge occasion, wrong payee).
3. **The gate decides.** CORROBORATED passes the decision-layer screen and the payment runner creates and captures the PayPal order. PARTIAL or CONFLICTED → the payment is **held in a human-approval queue**. No order is created, nothing is captured, and the agent cannot talk its way past the hold — a human rejects or approves the *record*, and a corrected payment is drafted and graded fresh.
4. **It fails closed.** No verdict, an unrecognised verdict, or an uncertain screen all end in the queue. The gate itself has no execute path: capture lives only in the payment runner, and only on an allowed verdict.

## The demo (under 3 minutes, runs anywhere)

```sh
python3 demo/demo_flow.py
```

Standard library only — no install, no credentials, no network. Four scenes, all driven by the same scenario builders the tests use:

- **S1 — clean release.** The salon's first payment, exactly as quoted: Website Build $900 + Care Plan $99 = **$999 CAD** → CORROBORATED → order created and captured.
- **S2 — the money shot.** Month 2 should be Care Plan only ($99), but the agent drafts the full $999 again, repeating the Build line → CONFLICTED → **held, with zero orders and zero captures**. The human rejects it; the corrected $99 re-draft grades CORROBORATED and settles.
- **S3 — wrong payee.** Right amount, right lines, wrong payee → CONFLICTED → held before any order exists.
- **S4 — unquoted add-on.** A month-2 charge bundles a $49 AI-Visibility Add-On that was never quoted → PARTIAL → held.

All amounts are **sandbox DEMO amounts in CAD** — candidate service pricing used as fixtures (see `fixtures.py`). They are labelled DEMO everywhere and are not published prices. The client is real and disclosed (SiteBefore's family pilot); the quote and amounts are the demo's illustrative fixtures, and every payment in the demo is simulated.

## Prove the live path is real (no credentials needed)

Requires Python 3.12 (the version the shipped counts below were observed on). One copy-pasteable line installs the dependencies in a venv and runs the full suite — including the 11 tests that exercise the live sandbox client against the vendored toolkit, with no credentials:

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python -m pytest -q
```

Expected tail (observed on the shipped code): `41 passed`. Then watch the live client refuse to run without credentials — it never fakes a success:

```sh
.venv/bin/python -c "from paypal_toolkit_client import ToolkitOrdersClient; ToolkitOrdersClient()"
# ValueError: ToolkitOrdersClient has no credentials: set PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET (founder-gated — …), or inject a transport for offline runs.
```

To run it live, create a sandbox REST app and set the two variables in `.env.example` (see `INTEGRATION.md`).

## Mock vs sandbox — stated plainly

The live PayPal sandbox client is implemented and tested (11 tests against the vendored toolkit); the demo runs the in-memory implementation of the same contract, so the gate's negative space is provable with no credentials. The payment runner talks to one interface (`OrdersClient` in `paypal_client.py`) with two implementations:

- **`ToolkitOrdersClient`** (`paypal_toolkit_client.py`): the live PayPal sandbox path, implemented on **PayPal's official agent toolkit** (vendored under `vendor/`, Apache-2.0, pinned — see `vendor/VENDOR.md` and `INTEGRATION.md`). It needs sandbox REST credentials in the environment (`PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET`, see `.env.example`) and fails fast without them — it never fakes a success. Known upstream limitations (the toolkit's USD-only create-order shortcut in the pinned version; its transport not sending a PayPal-Request-Id header) are documented in the module docstring and pinned by tests, not hidden.
- **`MockOrdersClient`** (what the demo and tests run): an in-memory implementation of the same create → capture contract. It exists so the gate can be proved end to end with no credentials, and so tests can assert the negative space — a held payment creates *no order* and is *never captured*.

## Run the tests

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
```

Observed on the shipped code (Python 3.12, dependencies installed): decision layer 8 passed · comparator 10 passed · scenarios (S1–S4 end to end) 7 passed · REST-client contract 5 passed · toolkit client 11 passed. In an environment without the two third-party packages, the toolkit test file cannot be collected and the remaining 30 tests still pass — the gate core is standard-library only by design.

## Files

| File | Role |
|---|---|
| `comparator.py` | The deterministic grader: payment claims vs quote → per-claim grades + verdict, each with a human-readable reason |
| `decision_layer.py` | The fleet's decision layer: typed decisions, rules decider, router, and the `ToolGate` with its human-approval queue |
| `gate_wiring.py` | Comparator → gate screen → `PaymentRunner` (the only place a capture can happen, and only on `allowed`) |
| `fixtures.py` | Demo data pack: pricing ladders (DEMO amounts), the approved quote, scenario builders S1–S4 |
| `paypal_client.py` | `OrdersClient` interface · `MockOrdersClient` · the historical hand-rolled sandbox stub |
| `paypal_toolkit_client.py` | `ToolkitOrdersClient` — the interface on PayPal's official agent toolkit |
| `vendor/` | PayPal agent toolkit, vendored verbatim at a pinned version (Apache-2.0) |
| `demo/demo_flow.py` | The end-to-end demo surface |
| `test_*.py` | The five test files described above |

## What's next

- The same scenes against the live PayPal sandbox — the credential-gated live run is the next verification step; the client itself is implemented and tested.
- A webhook-integrity scenario and signed verdict receipts, so a held payment's *why* stays auditable months later.
- The gate in front of SiteBefore's real billing — the demo's fixture business is the business it will actually serve.

## Licence

MIT (see `LICENSE`). The vendored PayPal agent toolkit under `vendor/` is Apache-2.0 and keeps its own licence file.
