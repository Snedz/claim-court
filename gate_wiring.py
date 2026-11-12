"""
gate_wiring.py — wire the comparator into the decision layer's ToolGate.

Reuse contract (readiness pack §4, against decision_layer.py as it
actually exists):

  * The comparator grades the payment first — deterministically, no model.
  * The payment attempt becomes a ToolCall(tool="paypal.capture", ...) whose
    args carry the comparator's verdict and per-claim grades.
  * A RulesDecider rule answers the gate's Bool screen FROM the comparator
    output: confident True only when the overall verdict is CORROBORATED.
    CONFLICTED / PARTIAL get a confident False, which the gate treats as
    "screen did not clear" -> the attempt is HELD in the human-approval
    queue. A verdict the rules don't recognise gets zero confidence ->
    also queued. The gate fails closed at every step.
  * Capture executes ONLY here, in PaymentRunner, and only when
    GateResult.allowed. The gate itself has no execute path, and neither
    does this module's wiring — approval of a queued entry changes only
    the queue record; the founder then has the agent re-draft, and the
    corrected draft is graded fresh (scenario S2's second half).

Policy layer on top of the screen:
  * "paypal.capture" is NEVER allow-listed — it must pass the screen.
  * A deny-arg pattern hard-denies any capture whose currency is not the
    quote's currency, before the screen is even consulted (defence in
    depth behind the comparator's own currency claim).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from comparator import CONFLICTED, CORROBORATED, PARTIAL, ComparisonResult, \
    grade_payment
from decision_layer import Bool, Router, RulesDecider, ToolCall, ToolGate, \
    GateResult
from paypal_client import CaptureResult, Order, OrdersClient, PayPalError

CAPTURE_TOOL = "paypal.capture"


def _screen_rules() -> RulesDecider:
    """Bool screen driven by the comparator verdict in the call args.

    ToolGate renders the screen context as `tool=... args={json} ...`, so
    the rules match the exact JSON fragment for the overall verdict key —
    never a bare substring, because individual CLAIMS inside a CONFLICTED
    verdict can themselves be CORROBORATED."""
    rules = RulesDecider()
    rules.add_rule(
        lambda r: f'"overall_verdict": "{CORROBORATED}"'
                  in (r.question + " " + r.context),
        lambda r: Bool(value=True, confidence=0.99),
        kinds={"bool"},
    )
    rules.add_rule(
        lambda r: (f'"overall_verdict": "{CONFLICTED}"'
                   in (r.question + " " + r.context))
                  or (f'"overall_verdict": "{PARTIAL}"'
                      in (r.question + " " + r.context)),
        lambda r: Bool(value=False, confidence=0.99),
        kinds={"bool"},
    )
    return rules


def build_payment_gate(quote_currency: str = "CAD",
                       router_log_path: Optional[str] = None,
                       queue_path: Optional[str] = None) -> ToolGate:
    """The gate every payment attempt must pass. The Router's JSONL log
    (router_log_path) doubles as the demo's audit-trail panel data."""
    router = Router(cheap=_screen_rules(), strong=None, threshold=0.8,
                    log_path=router_log_path)
    currency_deny = r'"currency":\s*"(?!' + re.escape(quote_currency) + r'")'
    return ToolGate(
        screen_router=router,
        allow_tools=(),                       # capture is never allow-listed
        deny_tools=(),
        deny_arg_patterns=[(CAPTURE_TOOL, currency_deny)],
        queue_path=queue_path,
    )


@dataclass
class AttemptResult:
    """Outcome of one payment attempt through the gate."""
    status: str                     # captured | held | denied | capture_failed
    verdict: ComparisonResult
    gate: GateResult
    order: Optional[Order] = None
    capture: Optional[CaptureResult] = None
    error: Optional[PayPalError] = None

    @property
    def queue_id(self) -> Optional[str]:
        return self.gate.queue_id


class PaymentRunner:
    """The runner OUTSIDE the gate: the only place a capture can happen,
    and only on GateResult.allowed. Held attempts create no order and no
    capture — the agent cannot talk its way past the hold."""

    def __init__(self, gate: ToolGate, client: OrdersClient):
        self.gate = gate
        self.client = client
        self._attempt_seq = 0

    def attempt(self, evidence, payment) -> AttemptResult:
        verdict = grade_payment(evidence, payment)
        call = ToolCall(
            tool=CAPTURE_TOOL,
            args={
                "amount_cents": payment.amount_cents,
                "currency": payment.currency,
                "payee": payment.payee,
                "lines": [f"{line.name}:{line.amount_cents}"
                          for line in payment.lines],
                "overall_verdict": verdict.verdict,
                "claims": [f"{g.claim}={g.status}" for g in verdict.claims],
                "quote_id": evidence.quote.id,
                "occasion": evidence.occasion,
            },
            context=(f"Claim Court verdict gate: payment proposed against "
                     f"quote {evidence.quote.id} ({evidence.occasion}). "
                     f"{payment.note}"),
        )
        result = self.gate.check(call)

        if not result.allowed:
            status = "held" if result.status == "queued" else "denied"
            return AttemptResult(status=status, verdict=verdict, gate=result)

        # Allowed: the gate has screened, the runner executes. The order is
        # created and captured in one flow; if PayPal itself refuses, the
        # failure is recorded, never silently swallowed as a success.
        self._attempt_seq += 1
        try:
            order = self.client.create_order(
                amount_cents=payment.amount_cents,
                currency=payment.currency,
                payee=payment.payee,
                lines=payment.lines,
                idempotency_key=(
                    f"{evidence.quote.id}:{evidence.occasion}:"
                    f"attempt-{self._attempt_seq}"),
            )
            capture = self.client.capture_order(order.id)
        except PayPalError as exc:
            return AttemptResult(status="capture_failed", verdict=verdict,
                                 gate=result, error=exc)
        return AttemptResult(status="captured", verdict=verdict, gate=result,
                             order=order, capture=capture)
