"""
paypal_client.py — PayPal Orders API client behind one clean interface.

Two implementations:

  MockOrdersClient     In-memory stand-in with the same contract. Local
                       runs and tests use this — no PayPal login exists
                       yet, and none is needed to prove the gate.

  SandboxOrdersClient  The real sandbox client. STUBBED: sandbox
                       credentials are founder-gated (the founder's
                       developer.paypal.com login creates the REST app;
                       readiness pack §2). It raises NotImplementedError
                       until credentials are plugged in at the TODO
                       markers. It does not pretend to work.

Contract (mirrors the Orders API create -> approve -> capture flow):
  create_order(...)  -> Order(status="CREATED")
  show_order(id)     -> Order
  capture_order(id)  -> CaptureResult(status="COMPLETED")

The client moves money-shaped data only inside the PayPal sandbox. In
this project it is only ever called by the payment runner AFTER the
verdict gate has allowed the attempt (see gate_wiring.py).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


class PayPalError(Exception):
    """A PayPal-side failure, typed so callers never parse raw responses."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass
class Order:
    id: str
    status: str                         # CREATED | APPROVED | COMPLETED
    amount_cents: int
    currency: str
    payee: str
    lines: tuple = ()
    capture_id: Optional[str] = None


@dataclass
class CaptureResult:
    order_id: str
    capture_id: str
    status: str                         # COMPLETED
    amount_cents: int
    currency: str


class OrdersClient(ABC):
    """Interface every Orders implementation satisfies."""

    @abstractmethod
    def create_order(self, *, amount_cents: int, currency: str, payee: str,
                     lines: tuple, idempotency_key: str) -> Order:
        """Create an order with intent CAPTURE. `idempotency_key` maps to
        the PayPal-Request-Id header: retrying with the same key must
        return the same order, never a duplicate."""

    @abstractmethod
    def show_order(self, order_id: str) -> Order:
        """Read an order back (the demo reconciles state against this)."""

    @abstractmethod
    def capture_order(self, order_id: str) -> CaptureResult:
        """Capture an approved order. Raises PayPalError on failure."""


# ---------------------------------------------------------------------------
# Mock implementation (local runs + tests)
# ---------------------------------------------------------------------------

class MockOrdersClient(OrdersClient):
    """In-memory Orders client. Deterministic ids (MOCK-ORDER-0001, ...)
    so tests can assert on them. `capture_calls` records every capture so
    tests can prove a held payment was never captured. Set
    `fail_capture_with` to a PayPal error code to rehearse the negative
    path (the S6 shape) at the client-contract level."""

    def __init__(self):
        self.orders: dict = {}
        self.capture_calls: list = []
        self.fail_capture_with: Optional[str] = None
        self._by_idempotency: dict = {}
        self._seq = 0

    def create_order(self, *, amount_cents, currency, payee, lines,
                     idempotency_key):
        if idempotency_key in self._by_idempotency:
            return self._by_idempotency[idempotency_key]
        self._seq += 1
        order = Order(
            id=f"MOCK-ORDER-{self._seq:04d}", status="CREATED",
            amount_cents=amount_cents, currency=currency, payee=payee,
            lines=tuple(lines))
        self.orders[order.id] = order
        self._by_idempotency[idempotency_key] = order
        return order

    def show_order(self, order_id):
        order = self.orders.get(order_id)
        if order is None:
            raise PayPalError("RESOURCE_NOT_FOUND",
                              f"no such order: {order_id}")
        return order

    def capture_order(self, order_id):
        order = self.show_order(order_id)
        self.capture_calls.append(order_id)
        if self.fail_capture_with is not None:
            raise PayPalError(self.fail_capture_with,
                              "mock-injected capture failure")
        if order.capture_id is not None:
            raise PayPalError("ORDER_ALREADY_CAPTURED",
                              f"order {order_id} was already captured")
        capture_id = f"MOCK-CAPTURE-{self._seq:04d}-{order_id[-4:]}"
        order.status = "COMPLETED"
        order.capture_id = capture_id
        return CaptureResult(order_id=order.id, capture_id=capture_id,
                             status="COMPLETED",
                             amount_cents=order.amount_cents,
                             currency=order.currency)


# ---------------------------------------------------------------------------
# Real sandbox client — STUB (founder-gated credentials)
# ---------------------------------------------------------------------------

class SandboxOrdersClient(OrdersClient):
    """PayPal sandbox Orders client.

    FOUNDER GATE: creating the REST app requires the founder's
    developer.paypal.com login (readiness pack §2). Credentials arrive via
    environment variables PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET — never
    in the repo (.env is gitignored; .env.example carries blanks only).

    TODO(credentials): once the founder provisions the sandbox app —
      1. __init__: read client_id/client_secret from env; fail fast with a
         clear message if unset.
      2. _access_token(): POST {base}/v1/oauth2/token with
         grant_type=client_credentials and HTTP Basic auth; cache the
         token until expiry.
      3. create_order(): POST {base}/v2/checkout/orders, intent CAPTURE,
         one purchase_unit (payee email_address, amount with CAD item
         breakdown), header PayPal-Request-Id = idempotency_key.
      4. capture_order(): POST {base}/v2/checkout/orders/{id}/capture.
      5. show_order(): GET {base}/v2/checkout/orders/{id}.
      Map non-2xx bodies to PayPalError using the body's name/message.
    Until then every method raises NotImplementedError via
    _not_wired() — an honest stub, never a silent fake success.
    """

    DEFAULT_BASE = "https://api-m.sandbox.paypal.com"

    def __init__(self, client_id: Optional[str] = None,
                 client_secret: Optional[str] = None,
                 base: str = DEFAULT_BASE):
        # TODO(credentials): default these from os.environ PAYPAL_CLIENT_ID
        # / PAYPAL_CLIENT_SECRET once the founder provisions the app.
        self.client_id = client_id
        self.client_secret = client_secret
        self.base = base

    def _not_wired(self):
        raise NotImplementedError(
            "SandboxOrdersClient is a stub: PayPal sandbox credentials are "
            "founder-gated (developer.paypal.com login, readiness pack §2). "
            "Use MockOrdersClient for local runs.")

    def create_order(self, *, amount_cents, currency, payee, lines,
                     idempotency_key):
        self._not_wired()

    def show_order(self, order_id):
        self._not_wired()

    def capture_order(self, order_id):
        self._not_wired()
