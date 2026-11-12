"""
paypal_toolkit_client.py — OrdersClient backed by PayPal's OFFICIAL
agent toolkit instead of a hand-rolled sandbox REST client.

Toolkit: paypal/agent-toolkit (Python), Apache-2.0, vendored verbatim
under vendor/paypal_agent_toolkit/ at package version 1.11.0 — see
vendor/VENDOR.md for the pin, the file list, and the upgrade path. The
toolkit is PayPal's own code for exactly the surface this project needs:

  create_order   -> shared/orders/tool_handlers + payload_util
  pay_order      -> shared/orders/tool_handlers.capture_order
  get_order      -> shared/orders/tool_handlers.get_order_details
  transport      -> shared/paypal_client.PayPalClient (OAuth2 client
                    credentials; sandbox vs live is the Context flag)

How this adapter uses it — honestly, including where it cannot:

  * capture_order / show_order call the toolkit's handler functions
    verbatim. They validate the order id against PayPal's id pattern and
    shape the response; this module only parses what comes back.
  * create_order builds the toolkit's parameter dict
    (build_create_order_params), builds the Orders payload with the
    toolkit's own payload builder (payload_util.parse_order_details),
    and posts it through the toolkit's transport. It does NOT route
    through the toolkit's create_order handler, because in v1.11.0 that
    handler validates against CreateOrderParameters, whose currency_code
    is pinned to Literal["USD"] — the toolkit's agent tool is USD-only,
    while this entry is CAD (fixtures + the gate's currency deny rule).
    The payload builder itself is currency-agnostic. The USD pin is
    pinned by a test (test_paypal_toolkit_client) so an upstream fix is
    noticed the day it lands.
  * Payee: the toolkit's create-order surface has no payee field — the
    authenticated sandbox account IS the payee. The adapter records the
    gate-approved payee on the returned Order; it cannot route an order
    to a different payee account.
  * Idempotency: the toolkit's transport does not send a
    PayPal-Request-Id header (Context.request_id exists upstream but is
    unused by PayPalClient.post in v1.11.0). create_order accepts the
    interface's idempotency_key and retains it on
    `last_idempotency_key` for the audit trail, but it is NOT transmitted
    — duplicate-create protection rests on the gate (one allowed attempt
    -> one create) until upstream wires the header.

Credentials: PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET from the
environment (see .env.example) — founder-gated, never in the repo.
PAYPAL_SANDBOX=false is the only switch needed to go live later; it is
the toolkit's Context flag, not a code change. No credentials are needed
when a transport is injected (tests do exactly that).
"""

from __future__ import annotations

import json
import os
import sys
from typing import Optional

_VENDOR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "vendor")
if os.path.isdir(_VENDOR_DIR) and _VENDOR_DIR not in sys.path:
    sys.path.insert(0, _VENDOR_DIR)

try:
    from paypal_agent_toolkit.shared.configuration import Context
    from paypal_agent_toolkit.shared.orders import tool_handlers
    from paypal_agent_toolkit.shared.orders.payload_util import \
        parse_order_details
    from paypal_agent_toolkit.shared.paypal_client import PayPalClient
except ImportError as exc:  # vendored tree or pydantic missing
    raise ImportError(
        "paypal_toolkit_client needs the vendored PayPal agent toolkit "
        "(vendor/paypal_agent_toolkit/, see vendor/VENDOR.md) and "
        f"pydantic>=2.10. Original error: {exc}") from exc

from paypal_client import CaptureResult, Order, OrdersClient, PayPalError

CREATE_ORDER_URI = "/v2/checkout/orders"   # the URI the toolkit handler posts to


# ---------------------------------------------------------------------------
# Request-shape mapping: our verdict-approved payment -> toolkit arguments
# ---------------------------------------------------------------------------

def build_create_order_params(*, amount_cents: int, currency: str,
                              lines: tuple) -> dict:
    """Map a gate-approved payment to the toolkit's create_order
    parameter shape (the dict its handler validates and its payload
    builder consumes). Our lines are quantity-1, tax-0 demo lines, and
    integer cents become the toolkit's float dollars exactly once, here.
    A lines/total mismatch is refused before anything is built — the
    comparator already guarantees this, and the client re-checks rather
    than trusting the caller."""
    lines_total = sum(line.amount_cents for line in lines)
    if lines_total != amount_cents:
        raise PayPalError(
            "AMOUNT_MISMATCH",
            f"line items sum to {lines_total} cents but the approved "
            f"amount is {amount_cents} cents; refusing to build a "
            "toolkit create_order call from inconsistent claims")
    return {
        "currency_code": currency,
        "items": [
            {
                "name": line.name,
                "quantity": 1,
                "item_cost": line.amount_cents / 100.0,
                "item_total": line.amount_cents / 100.0,
                "tax_percent": 0,
            }
            for line in lines
        ],
    }


def build_create_order_payload(*, amount_cents: int, currency: str,
                               lines: tuple) -> dict:
    """The exact Orders API payload the toolkit builds from those
    parameters — exposed so tests (and the demo) can assert the request
    shape without any network or credentials."""
    params = build_create_order_params(
        amount_cents=amount_cents, currency=currency, lines=lines)
    return parse_order_details(params)


def _to_cents(value) -> int:
    return int(round(float(value) * 100))


# ---------------------------------------------------------------------------
# The client
# ---------------------------------------------------------------------------

class ToolkitOrdersClient(OrdersClient):
    """OrdersClient whose Orders calls run on PayPal's agent toolkit.

    The default (no `transport` injected) builds the toolkit's own
    PayPalClient from env credentials and fails fast in __init__ if they
    are absent — an honest error at wiring time, not a fake success at
    capture time.
    """

    def __init__(self, client_id: Optional[str] = None,
                 client_secret: Optional[str] = None,
                 sandbox: Optional[bool] = None,
                 transport=None):
        if sandbox is None:
            sandbox = os.environ.get(
                "PAYPAL_SANDBOX", "true").strip().lower() != "false"
        self.sandbox = sandbox
        self.last_idempotency_key: Optional[str] = None
        self._payees: dict = {}
        self._lines: dict = {}
        if transport is not None:
            self._transport = transport
            return
        client_id = client_id or os.environ.get("PAYPAL_CLIENT_ID")
        client_secret = client_secret or os.environ.get(
            "PAYPAL_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise ValueError(
                "ToolkitOrdersClient has no credentials: set "
                "PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET (founder-gated — "
                "the founder's developer.paypal.com login creates the "
                "sandbox REST app; see .env.example), or inject a "
                "transport for offline runs.")
        context = Context(sandbox=sandbox, source="CLAIM-COURT")
        self._transport = PayPalClient(client_id, client_secret, context)

    # -- OrdersClient interface -------------------------------------------

    def create_order(self, *, amount_cents, currency, payee, lines,
                     idempotency_key):
        payload = build_create_order_payload(
            amount_cents=amount_cents, currency=currency, lines=lines)
        self.last_idempotency_key = idempotency_key
        try:
            resp = self._transport.post(uri=CREATE_ORDER_URI,
                                        payload=payload)
        except PayPalError:
            raise
        except Exception as exc:
            raise PayPalError(
                "TOOLKIT_TRANSPORT_ERROR",
                f"toolkit create_order POST failed: {exc}") from exc
        if not isinstance(resp, dict) or not resp.get("id"):
            raise PayPalError(
                "MALFORMED_RESPONSE",
                f"toolkit create_order returned no order id: {resp!r}")
        unit = (resp.get("purchase_units") or [{}])[0]
        amount = (unit.get("amount") or {})
        order = Order(
            id=resp["id"],
            status=resp.get("status", "CREATED"),
            amount_cents=_to_cents(amount["value"])
            if "value" in amount else amount_cents,
            currency=amount.get("currency_code", currency),
            payee=payee,
            lines=tuple(lines),
        )
        self._payees[order.id] = payee
        self._lines[order.id] = tuple(lines)
        return order

    def show_order(self, order_id):
        try:
            data = json.loads(tool_handlers.get_order_details(
                self._transport, {"order_id": order_id}))
        except PayPalError:
            raise
        except Exception as exc:
            raise PayPalError(
                "TOOLKIT_TRANSPORT_ERROR",
                f"toolkit get_order failed: {exc}") from exc
        raw = data.get("raw") or {}
        unit = (raw.get("purchase_units") or [{}])[0]
        amount = (unit.get("amount") or {})
        captures = ((unit.get("payments") or {}).get("captures") or [])
        return Order(
            id=order_id,
            status=raw.get("status", data.get("status", "")),
            amount_cents=_to_cents(amount["value"])
            if "value" in amount else 0,
            currency=amount.get("currency_code", ""),
            payee=self._payees.get(order_id, ""),
            lines=self._lines.get(order_id, ()),
            capture_id=captures[0].get("id") if captures else None,
        )

    def capture_order(self, order_id):
        try:
            data = json.loads(tool_handlers.capture_order(
                self._transport, {"order_id": order_id}))
        except PayPalError:
            raise
        except Exception as exc:
            raise PayPalError(
                "TOOLKIT_TRANSPORT_ERROR",
                f"toolkit pay_order (capture) failed: {exc}") from exc
        raw = data.get("raw") or {}
        unit = (raw.get("purchase_units") or [{}])[0]
        captures = ((unit.get("payments") or {}).get("captures") or [])
        if not captures:
            raise PayPalError(
                "MALFORMED_RESPONSE",
                f"toolkit capture for {order_id} returned no capture "
                f"record: {data!r}")
        capture = captures[0]
        amount = (capture.get("amount") or {})
        status = data.get("status") or capture.get("status", "")
        if status != "COMPLETED":
            raise PayPalError(
                "CAPTURE_NOT_COMPLETED",
                f"toolkit capture for {order_id} ended in status "
                f"{status!r}, not COMPLETED")
        return CaptureResult(
            order_id=order_id,
            capture_id=capture.get("id", ""),
            status=status,
            amount_cents=_to_cents(amount["value"])
            if "value" in amount else 0,
            currency=amount.get("currency_code", ""),
        )
