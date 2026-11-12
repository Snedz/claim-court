# PayPal agent toolkit — integration notes

**Verdict: INTEGRATED** (with one documented upstream limitation routed
around, see "The USD pin"). The hand-rolled sandbox path is replaced:
`ToolkitOrdersClient` in `paypal_toolkit_client.py` implements the
existing `OrdersClient` interface on PayPal's own toolkit code. The
architecture is unchanged — comparator, gate, queue, runner untouched;
`MockOrdersClient` is still the default everywhere; the original 30
tests are unmodified and green, plus 11 new toolkit tests (41 total).

## What the toolkit is

**paypal/agent-toolkit** — PayPal's official agent toolkit
(github.com/paypal/agent-toolkit), **Apache License 2.0**. It ships a
TypeScript package and a Python package (`paypal-agent-toolkit`, v1.11.0,
Python ≥3.11); this project uses the Python one. Its Orders surface is
three agent tools, gated by a `Configuration` actions map:

| Tool | Toolkit handler | Orders API call |
|---|---|---|
| `create_order` | `shared/orders/tool_handlers.create_order` | POST /v2/checkout/orders |
| `pay_order` | `shared/orders/tool_handlers.capture_order` | POST /v2/checkout/orders/{id}/capture |
| `get_order_details` | `shared/orders/tool_handlers.get_order_details` | GET /v2/checkout/orders/{id} |

Sandbox vs live is a **configuration flag**: `Context(sandbox=True)`
selects `https://api-m.sandbox.paypal.com`, `False` selects the live
base URL. Auth is OAuth2 client-credentials inside the toolkit's
`PayPalClient`. (The toolkit also covers invoices, subscriptions,
disputes, tracking, and insights — out of scope here.)

## Integration shape

- **Vendored, not pip-installed.** The toolkit's framework-free
  `shared/` subtree is vendored verbatim at `vendor/paypal_agent_toolkit/`
  (pin, file list, exclusions, and upgrade path: `vendor/VENDOR.md`).
  Installing from PyPI would drag `langchain`, `crewai-tools`, and
  `openai-agents` into the payment path as hard dependencies; the gate
  calls handlers directly and needs none of them. Vendoring also matches
  this project's existing pattern (`decision_layer.py`). Runtime deps of
  the integration: `pydantic>=2.10`, `requests` — nothing else.
- **Capture and show use the toolkit handlers verbatim** — they validate
  the order id against PayPal's id pattern and shape the response.
- **Create uses the toolkit's payload builder + transport** (see below).
- **Credentials are env-only**: `PAYPAL_CLIENT_ID` /
  `PAYPAL_CLIENT_SECRET` (already in `.env.example`), read at client
  construction; construction fails fast with a plain-language error if
  they're absent. `PAYPAL_SANDBOX` (default `true`) maps to the
  toolkit's Context flag. No login was attempted; no account exists yet.

## The USD pin (the one honest limitation)

In v1.11.0 the toolkit's `CreateOrderParameters.currency_code` is
`Literal["USD"]` — the *agent tool* only accepts USD. This entry is CAD
(the fixtures, the quote, and the gate's currency deny-rule all say CAD),
and the handler validates before building, so routing create through the
handler would reject every order this project makes. The toolkit's
payload builder (`parse_order_details`) is currency-agnostic, so create
goes: our params → toolkit payload builder → toolkit transport. Two
tests pin this behaviour: USD params pass the toolkit's own validation,
CAD params raise — the day upstream fixes the pin, a test fails and
create can move onto the handler verbatim.

Two smaller upstream gaps, both documented in the module docstring:

- **No per-order payee.** The toolkit's create surface has no payee
  field; the authenticated sandbox account is the payee. The adapter
  records the gate-approved payee on the returned `Order` but cannot
  route to a different account.
- **No idempotency header.** The toolkit transport never sends
  `PayPal-Request-Id` (v1.11.0). The adapter accepts and retains the
  key for the audit trail; duplicate-create protection rests on the
  gate allowing exactly one create per approved attempt.

## What changes when sandbox credentials arrive

1. Founder creates the sandbox REST app (developer.paypal.com login —
   the standing founder gate) and puts `PAYPAL_CLIENT_ID` /
   `PAYPAL_CLIENT_SECRET` in a local `.env` (gitignored).
2. Swap one line where the runner is wired: `PaymentRunner(gate,
   ToolkitOrdersClient())` instead of `MockOrdersClient()`. Nothing in
   the comparator, gate, or scenarios changes.
3. `SandboxOrdersClient` (the stub in `paypal_client.py`) is superseded
   — leave it as the historical marker or delete it then; the toolkit
   client is the sandbox path now.
4. Expect the live half of the S6 rehearsal (PayPal-side refusal) to
   become testable for real; failure mapping is already in place
   (transport errors surface as `PayPalError`, captures that don't end
   COMPLETED raise `CAPTURE_NOT_COMPLETED`).

## What Nov 8 / Nov 9 should now expect

- **Nov 8 branch pick:** unaffected. Both branches sit on the same
  `OrdersClient` interface; the demo surface swaps mock ↔ toolkit behind
  it. The pick still only skins the surface and selects the ladder.
- **Nov 9 go/no-go (S1 + S2 end-to-end):** S1 and S2 now also pass
  end-to-end through the toolkit client against a fake transport,
  including the money-shot property — an S2 hold makes **zero** toolkit
  calls. If sandbox credentials land before Nov 9, the same two
  scenarios run against the real sandbox with the one-line swap above;
  if they don't, the go/no-go proceeds on the mock + toolkit-fake runs
  exactly as planned, with the credentials gate unchanged.
