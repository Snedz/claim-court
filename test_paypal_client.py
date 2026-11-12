"""
Tests for paypal_client.py — run: python3 -m unittest -v

The mock's contract (create -> show -> capture, idempotency, typed
errors) and the sandbox stub's honesty (it raises until the founder
provisions credentials — it never fakes a success).
"""

import unittest

from paypal_client import (MockOrdersClient, PayPalError,
                           SandboxOrdersClient)


def create(client, key="k-1", amount=99900):
    return client.create_order(amount_cents=amount, currency="CAD",
                               payee="SiteBefore (sandbox business)",
                               lines=(), idempotency_key=key)


class MockClientTests(unittest.TestCase):

    def test_create_show_capture_lifecycle(self):
        client = MockOrdersClient()
        order = create(client)
        self.assertEqual(order.status, "CREATED")
        self.assertEqual(client.show_order(order.id).id, order.id)
        capture = client.capture_order(order.id)
        self.assertEqual(capture.status, "COMPLETED")
        self.assertEqual(capture.amount_cents, 99900)
        self.assertEqual(client.show_order(order.id).status, "COMPLETED")

    def test_create_is_idempotent_on_key(self):
        client = MockOrdersClient()
        first = create(client, key="same-key")
        second = create(client, key="same-key")
        self.assertEqual(first.id, second.id)
        self.assertEqual(len(client.orders), 1)

    def test_unknown_order_raises_typed_error(self):
        client = MockOrdersClient()
        with self.assertRaises(PayPalError) as ctx:
            client.show_order("MOCK-ORDER-9999")
        self.assertEqual(ctx.exception.code, "RESOURCE_NOT_FOUND")

    def test_double_capture_raises_typed_error(self):
        client = MockOrdersClient()
        order = create(client)
        client.capture_order(order.id)
        with self.assertRaises(PayPalError) as ctx:
            client.capture_order(order.id)
        self.assertEqual(ctx.exception.code, "ORDER_ALREADY_CAPTURED")


class SandboxStubTests(unittest.TestCase):

    def test_stub_raises_until_credentials_are_wired(self):
        client = SandboxOrdersClient()
        with self.assertRaises(NotImplementedError):
            create(client)
        with self.assertRaises(NotImplementedError):
            client.capture_order("anything")
        with self.assertRaises(NotImplementedError):
            client.show_order("anything")


if __name__ == "__main__":
    unittest.main()
