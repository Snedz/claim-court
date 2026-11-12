"""
End-to-end scenario tests — run: python3 -m unittest -v

The readiness pack's scenarios (§2) driven through the full shared core:
comparator -> decision-layer ToolGate -> PaymentRunner -> MockOrdersClient.

  S1  clean payment           -> CORROBORATED -> released and captured
  S2  tampered month-2 draft  -> CONFLICTED   -> held, NEVER captured;
      founder rejects; corrected re-draft -> CORROBORATED -> captured
  S3  payee conflict          -> CONFLICTED   -> held, no order created
  S4  unquoted add-on         -> PARTIAL      -> held in the queue

Plus the fail-closed contract: an attempt carrying no recognisable
verdict is queued, and the gate exposes no execute path.
"""

import unittest

import fixtures
from comparator import CONFLICTED, CORROBORATED, PARTIAL
from decision_layer import ToolCall
from gate_wiring import PaymentRunner, build_payment_gate
from paypal_client import MockOrdersClient

LAD = fixtures.LADDERS["C"]          # DEMO amounts: P1 $999, Care $99


def make_runner():
    gate = build_payment_gate(quote_currency=LAD.currency)
    client = MockOrdersClient()
    return PaymentRunner(gate=gate, client=client), gate, client


class ScenarioTests(unittest.TestCase):

    def test_s1_clean_payment_released_and_captured(self):
        runner, gate, client = make_runner()
        result = runner.attempt(*fixtures.scenario_s1(LAD))

        self.assertEqual(result.verdict.verdict, CORROBORATED)
        self.assertEqual(result.status, "captured")
        self.assertTrue(result.gate.allowed)
        self.assertIsNotNone(result.capture)
        self.assertEqual(result.capture.status, "COMPLETED")
        self.assertEqual(result.capture.amount_cents, 99900)
        self.assertEqual(client.capture_calls, [result.order.id])
        self.assertEqual(gate.pending(), [])       # nothing held

    def test_s2_tampered_payment_held_then_corrected_releases(self):
        runner, gate, client = make_runner()

        # The agent repeats the whole first payment for month 2.
        held = runner.attempt(*fixtures.scenario_s2(LAD))
        self.assertEqual(held.verdict.verdict, CONFLICTED)
        self.assertEqual(held.status, "held")
        self.assertFalse(held.gate.allowed)
        self.assertIsNotNone(held.queue_id)
        # The money shot: no order, no capture — the hold is total.
        self.assertEqual(client.orders, {})
        self.assertEqual(client.capture_calls, [])
        pending = gate.pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].id, held.queue_id)

        # The founder rejects the held draft. Approval machinery changes
        # only the record — nothing executes on the back of it.
        entry = gate.reject(held.queue_id)
        self.assertEqual(entry.status, "rejected")
        self.assertEqual(client.capture_calls, [])

        # The agent re-drafts at the correct $99; graded fresh, it passes.
        fixed = runner.attempt(*fixtures.scenario_s2_corrected(LAD))
        self.assertEqual(fixed.verdict.verdict, CORROBORATED)
        self.assertEqual(fixed.status, "captured")
        self.assertEqual(fixed.capture.amount_cents, 9900)
        self.assertEqual(len(client.capture_calls), 1)

    def test_s3_payee_conflict_held_before_any_order(self):
        runner, gate, client = make_runner()
        result = runner.attempt(*fixtures.scenario_s3(LAD))
        self.assertEqual(result.verdict.verdict, CONFLICTED)
        self.assertEqual(result.verdict.claim("payee").status, CONFLICTED)
        self.assertEqual(result.status, "held")
        self.assertEqual(client.orders, {})
        self.assertEqual(client.capture_calls, [])
        self.assertEqual(len(gate.pending()), 1)

    def test_s4_unquoted_addon_partial_held(self):
        runner, gate, client = make_runner()
        result = runner.attempt(*fixtures.scenario_s4(LAD))
        self.assertEqual(result.verdict.verdict, PARTIAL)
        self.assertEqual(result.status, "held")
        self.assertEqual(client.capture_calls, [])
        self.assertEqual(len(gate.pending()), 1)

    def test_currency_mismatch_is_denied_by_policy_not_queued(self):
        # Defence in depth: a non-quote currency never reaches the screen.
        runner, gate, client = make_runner()
        evidence, pay = fixtures.scenario_s1(LAD)
        from dataclasses import replace
        result = runner.attempt(evidence, replace(pay, currency="USD"))
        self.assertEqual(result.status, "denied")
        self.assertEqual(gate.pending(), [])
        self.assertEqual(client.capture_calls, [])

    def test_unrecognised_verdict_fails_closed_into_queue(self):
        # A capture call whose args carry no comparator verdict must not
        # pass the screen: zero-confidence -> queued, never allowed.
        runner, gate, client = make_runner()
        result = gate.check(ToolCall(
            tool="paypal.capture",
            args={"amount_cents": 100, "currency": "CAD",
                  "payee": fixtures.DEMO_PAYEE},
            context="hand-built call with no verdict attached"))
        self.assertEqual(result.status, "queued")
        self.assertFalse(result.allowed)
        self.assertFalse(hasattr(gate, "execute"))  # no execute path, ever

    def test_paypal_side_failure_is_recorded_not_swallowed(self):
        # The S6 shape at contract level: gate allows, PayPal refuses —
        # the attempt reports capture_failed, state stays consistent.
        runner, gate, client = make_runner()
        client.fail_capture_with = "INSTRUMENT_DECLINED"
        result = runner.attempt(*fixtures.scenario_s1(LAD))
        self.assertEqual(result.status, "capture_failed")
        self.assertEqual(result.error.code, "INSTRUMENT_DECLINED")
        self.assertIsNone(result.capture)


if __name__ == "__main__":
    unittest.main()
