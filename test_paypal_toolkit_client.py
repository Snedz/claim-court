"""
Toolkit client tests — run: python3 -m unittest -v

Everything runs offline: the toolkit's handlers and payload builder are
real (vendored, vendor/VENDOR.md), the HTTP transport is a fake with the
same .post/.get contract as the toolkit's PayPalClient. No credentials,
no network.

Two tests pin upstream v1.11.0 behaviours ON PURPOSE — if a future
toolkit upgrade changes them, these fail and INTEGRATION.md gets updated:
  * CreateOrderParameters pins currency_code to Literal["USD"].
  * The toolkit transport sends no PayPal-Request-Id header (the adapter
    retains the idempotency key; it cannot transmit it).
"""

import os
import unittest
from unittest import mock

import fixtures
from gate_wiring import PaymentRunner, build_payment_gate
from paypal_client import PayPalError
from paypal_toolkit_client import ToolkitOrdersClient, \
    build_create_order_params, build_create_order_payload

LAD = fixtures.LADDERS["C"]          # DEMO amounts: P1 $999, Care $99, CAD

ORDER_ID = "5RK10452AB6789012"       # matches PayPal's ^[A-Z0-9]{17,32}$
CAPTURE_ID = "4CF12345DE6789012"


class FakeTransport:
    """Duck-typed stand-in for the toolkit's PayPalClient: records every
    call and answers with Orders-API-shaped dicts, like the real
    transport returns after response.json()."""

    def __init__(self):
        self.posts = []
        self.gets = []
        self.fail_post_with = None
        self._order = None

    def post(self, uri, payload):
        self.posts.append((uri, payload))
        if self.fail_post_with is not None:
            raise self.fail_post_with
        if uri == "/v2/checkout/orders":
            unit = payload["purchase_units"][0]
            self._order = {
                "id": ORDER_ID, "status": "CREATED",
                "amount": unit["amount"],
            }
            return {"id": ORDER_ID, "status": "CREATED",
                    "purchase_units": [{"amount": unit["amount"]}]}
        if uri == f"/v2/checkout/orders/{ORDER_ID}/capture":
            amount = self._order["amount"]
            self._order["status"] = "COMPLETED"
            return {
                "id": ORDER_ID, "status": "COMPLETED",
                "purchase_units": [{
                    "amount": amount,
                    "payments": {"captures": [{
                        "id": CAPTURE_ID, "status": "COMPLETED",
                        "amount": {"value": amount["value"],
                                   "currency_code":
                                       amount["currency_code"]},
                    }]},
                }],
            }
        raise AssertionError(f"unexpected POST {uri}")

    def get(self, uri):
        self.gets.append(uri)
        assert uri == f"/v2/checkout/orders/{ORDER_ID}"
        unit = {"amount": self._order["amount"]}
        if self._order["status"] == "COMPLETED":
            unit["payments"] = {"captures": [{
                "id": CAPTURE_ID, "status": "COMPLETED",
                "amount": {"value": self._order["amount"]["value"],
                           "currency_code":
                               self._order["amount"]["currency_code"]},
            }]}
        return {"id": ORDER_ID, "status": self._order["status"],
                "purchase_units": [unit]}


def make_client():
    transport = FakeTransport()
    return ToolkitOrdersClient(transport=transport), transport


class ParamsMappingTests(unittest.TestCase):
    """The request-shape mapping: verdict-approved capture arguments ->
    the toolkit's tool arguments, from the S1 fixture payment."""

    def setUp(self):
        _, self.payment = fixtures.scenario_s1(LAD)

    def test_params_shape(self):
        params = build_create_order_params(
            amount_cents=self.payment.amount_cents,
            currency=self.payment.currency, lines=self.payment.lines)
        self.assertEqual(params["currency_code"], "CAD")
        self.assertEqual(len(params["items"]), 2)
        build, care = params["items"]
        self.assertEqual(build["name"], fixtures.BUILD_LINE)
        self.assertEqual(build["item_cost"], 900.00)
        self.assertEqual(build["item_total"], build["item_cost"])
        self.assertEqual(build["quantity"], 1)
        self.assertEqual(build["tax_percent"], 0)
        self.assertEqual(care["item_cost"], 99.00)

    def test_params_refuse_lines_total_mismatch(self):
        with self.assertRaises(PayPalError) as ctx:
            build_create_order_params(
                amount_cents=self.payment.amount_cents + 100,
                currency="CAD", lines=self.payment.lines)
        self.assertEqual(ctx.exception.code, "AMOUNT_MISMATCH")

    def test_payload_shape_is_toolkit_built(self):
        payload = build_create_order_payload(
            amount_cents=self.payment.amount_cents,
            currency=self.payment.currency, lines=self.payment.lines)
        self.assertEqual(payload["intent"], "CAPTURE")
        unit = payload["purchase_units"][0]
        self.assertEqual(unit["amount"]["value"], "999.00")
        self.assertEqual(unit["amount"]["currency_code"], "CAD")
        breakdown = unit["amount"]["breakdown"]
        self.assertEqual(breakdown["item_total"]["value"], "999.00")
        self.assertEqual([i["name"] for i in unit["items"]],
                         [fixtures.BUILD_LINE, fixtures.CARE_LINE])
        self.assertEqual(unit["items"][0]["unit_amount"]["value"],
                         "900.00")


class UpstreamSchemaPinTests(unittest.TestCase):
    """Pin the toolkit v1.11.0 USD-only tool schema (see INTEGRATION.md):
    the handler's parameter model accepts USD and rejects CAD, which is
    why create_order goes through the toolkit's payload builder instead
    of its handler."""

    def test_usd_params_validate_cad_params_do_not(self):
        from pydantic import ValidationError
        from paypal_agent_toolkit.shared.orders.parameters import \
            CreateOrderParameters

        _, payment = fixtures.scenario_s1(LAD)
        usd = build_create_order_params(
            amount_cents=payment.amount_cents, currency="USD",
            lines=payment.lines)
        CreateOrderParameters(**usd)            # must not raise
        cad = build_create_order_params(
            amount_cents=payment.amount_cents, currency="CAD",
            lines=payment.lines)
        with self.assertRaises(ValidationError):
            CreateOrderParameters(**cad)


class ClientBehaviourTests(unittest.TestCase):

    def test_create_posts_toolkit_payload_and_returns_order(self):
        client, transport = make_client()
        _, payment = fixtures.scenario_s1(LAD)
        order = client.create_order(
            amount_cents=payment.amount_cents, currency=payment.currency,
            payee=payment.payee, lines=payment.lines,
            idempotency_key="Q-1:payment_1:attempt-1")
        self.assertEqual(order.id, ORDER_ID)
        self.assertEqual(order.status, "CREATED")
        self.assertEqual(order.amount_cents, 99900)
        self.assertEqual(order.currency, "CAD")
        self.assertEqual(order.payee, fixtures.DEMO_PAYEE)
        uri, payload = transport.posts[0]
        self.assertEqual(uri, "/v2/checkout/orders")
        self.assertEqual(payload["intent"], "CAPTURE")
        # Retained for the audit trail; NOT transmitted (upstream limit).
        self.assertEqual(client.last_idempotency_key,
                         "Q-1:payment_1:attempt-1")

    def test_capture_via_toolkit_handler(self):
        client, transport = make_client()
        _, payment = fixtures.scenario_s1(LAD)
        order = client.create_order(
            amount_cents=payment.amount_cents, currency=payment.currency,
            payee=payment.payee, lines=payment.lines,
            idempotency_key="k")
        capture = client.capture_order(order.id)
        self.assertEqual(capture.status, "COMPLETED")
        self.assertEqual(capture.capture_id, CAPTURE_ID)
        self.assertEqual(capture.amount_cents, 99900)
        self.assertEqual(capture.currency, "CAD")
        self.assertEqual(transport.posts[-1][0],
                         f"/v2/checkout/orders/{ORDER_ID}/capture")

    def test_show_order_reads_back_state(self):
        client, _ = make_client()
        _, payment = fixtures.scenario_s1(LAD)
        order = client.create_order(
            amount_cents=payment.amount_cents, currency=payment.currency,
            payee=payment.payee, lines=payment.lines,
            idempotency_key="k")
        before = client.show_order(order.id)
        self.assertEqual(before.status, "CREATED")
        self.assertIsNone(before.capture_id)
        client.capture_order(order.id)
        after = client.show_order(order.id)
        self.assertEqual(after.status, "COMPLETED")
        self.assertEqual(after.capture_id, CAPTURE_ID)
        self.assertEqual(after.amount_cents, 99900)

    def test_transport_failure_maps_to_paypal_error(self):
        client, transport = make_client()
        _, payment = fixtures.scenario_s1(LAD)
        order = client.create_order(
            amount_cents=payment.amount_cents, currency=payment.currency,
            payee=payment.payee, lines=payment.lines,
            idempotency_key="k")
        transport.fail_post_with = RuntimeError("connection reset")
        with self.assertRaises(PayPalError) as ctx:
            client.capture_order(order.id)
        self.assertEqual(ctx.exception.code, "TOOLKIT_TRANSPORT_ERROR")

    def test_missing_credentials_fail_fast(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as ctx:
                ToolkitOrdersClient()
        self.assertIn("PAYPAL_CLIENT_ID", str(ctx.exception))


class GateIntegrationTests(unittest.TestCase):
    """The gate is unchanged and still in front: the toolkit client is
    only ever reached on an allowed attempt."""

    def make_runner(self):
        gate = build_payment_gate(quote_currency=LAD.currency)
        client, transport = make_client()
        return PaymentRunner(gate=gate, client=client), gate, transport

    def test_s1_releases_and_captures_through_toolkit(self):
        runner, gate, transport = self.make_runner()
        result = runner.attempt(*fixtures.scenario_s1(LAD))
        self.assertEqual(result.status, "captured")
        self.assertEqual(result.capture.status, "COMPLETED")
        self.assertEqual(result.capture.amount_cents, 99900)
        self.assertEqual(len(transport.posts), 2)   # create + capture
        self.assertEqual(gate.pending(), [])

    def test_s2_hold_never_touches_the_toolkit(self):
        runner, gate, transport = self.make_runner()
        held = runner.attempt(*fixtures.scenario_s2(LAD))
        self.assertEqual(held.status, "held")
        self.assertEqual(transport.posts, [])       # zero toolkit calls
        self.assertEqual(transport.gets, [])
        corrected = runner.attempt(*fixtures.scenario_s2_corrected(LAD))
        self.assertEqual(corrected.status, "captured")
        self.assertEqual(corrected.capture.amount_cents, 9900)


if __name__ == "__main__":
    unittest.main()
