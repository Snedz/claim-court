#!/usr/bin/env python3
"""
demo_flow.py — the Option A demo surface: "SiteBefore, settled by a
verified agent", end to end in one terminal run (stdlib only, no
credentials, no network).

The story a judge can follow in under three minutes:

  A billing agent for SiteBefore (an agent-run website service) proposes
  charges for a client job. Every proposal is graded by a deterministic
  comparator against the ONE document that defines what may be charged —
  the client-approved quote — and passes through the decision-layer gate
  before the payment runner may touch PayPal.

  The example client is Shenail Hair Salon & Nail Bar
  (shenailhairlounge.ca), a real salon in Niagara Falls and SiteBefore's
  family pilot client, disclosed as such here and in the run output.
  The job is the salon's website redesign + care plan under the demo's
  illustrative quote. The scenario is simulated end to end: every
  payment below is a sandbox/mock scenario — not a real transaction,
  not revenue, not a live customer deployment.

  Scene 1  The job's first payment, exactly as quoted -> CORROBORATED
           -> the PayPal order is created and captured.
  Scene 2  Month 2: the agent drafts the FULL first payment again,
           repeating the one-time Website Build line (the classic silent
           agent error) -> CONFLICTED -> HELD. No order exists. Nothing
           was captured. The human rejects the held draft; the agent
           re-drafts correctly and the corrected charge settles.
  Scene 3  Two more failure shapes, fast: right amount to the WRONG
           payee -> held; an unquoted add-on bundled in -> held.

Payment client: MockOrdersClient — an in-memory implementation of the
same OrdersClient contract the live client satisfies. The live path
(ToolkitOrdersClient, PayPal's official agent toolkit) needs sandbox
REST credentials, which are founder-gated; this demo states that
plainly instead of faking a sandbox call. Swap one line in main() when
credentials exist and every scene runs against the real sandbox.

All amounts are sandbox DEMO amounts in CAD (fixtures.py, Ladder C).
Run:  python3 demo/demo_flow.py        (from the project root)
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fixtures
from comparator import fmt_money
from gate_wiring import PaymentRunner, build_payment_gate
from paypal_client import MockOrdersClient

LAD = fixtures.LADDERS[fixtures.DEFAULT_LADDER]

RULE = "=" * 72
THIN = "-" * 72


def banner(title: str) -> None:
    print(f"\n{RULE}\n{title}\n{RULE}")


def show_verdict(result) -> None:
    v = result.verdict
    print(f"  Comparator verdict: {v.verdict}")
    for grade in v.claims:
        print(f"    - {grade.claim:<10} {grade.status:<14} {grade.detail}")
    print(f"  Gate outcome:       {result.status.upper()}", end="")
    if result.queue_id:
        print(f"  (human-approval queue entry {result.queue_id})")
    elif result.capture is not None:
        print(f"  (order {result.order.id} -> capture "
              f"{result.capture.capture_id}, {result.capture.status})")
    else:
        print()


def main() -> int:
    gate = build_payment_gate(quote_currency=LAD.currency)
    client = MockOrdersClient()
    runner = PaymentRunner(gate=gate, client=client)

    banner("SITEBEFORE, SETTLED BY A VERIFIED AGENT")
    print("An AI billing agent proposes charges for a website job.")
    print("A deterministic gate grades each proposal against the")
    print("client-approved quote. Only a verified charge reaches PayPal.")
    print(f"\nExample client: {fixtures.DEMO_CLIENT}")
    print("SiteBefore's family pilot client. The job: the salon's")
    print("website redesign plus a monthly care plan, under the")
    print("approved quote below.")
    print("SIMULATED scenario — every payment is a sandbox demo; no")
    print("real money moves. Not revenue, not traction, not a live")
    print("deployment, and the salon has not paid through this system.")
    print(f"\nApproved quote {fixtures.quote_for(LAD).id} "
          f"(payee: {fixtures.DEMO_PAYEE}, currency {LAD.currency}):")
    for line in fixtures.quote_for(LAD).lines:
        print(f"    {line.name:<22} {fmt_money(line.amount_cents)} CAD")
    print("DEMO amounts — sandbox fixtures, not published prices.")

    banner("SCENE 1 — the first payment, exactly as quoted")
    ev, pay = fixtures.scenario_s1(LAD)
    print(f"Agent proposes the salon's first payment: "
          f"{fmt_money(pay.amount_cents)} CAD ({pay.note})")
    r1 = runner.attempt(ev, pay)
    show_verdict(r1)
    assert r1.status == "captured"

    banner("SCENE 2 — month 2: the agent repeats the whole first payment")
    ev, pay = fixtures.scenario_s2(LAD)
    print("Month 2 of the salon's care plan should be the Care Plan")
    print(f"only ($99.00). The agent drafts {fmt_money(pay.amount_cents)}")
    print("CAD again, repeating the one-time Website Build line:")
    r2 = runner.attempt(ev, pay)
    show_verdict(r2)
    print(f"\n  Orders created so far: {len(client.orders)}  |  "
          f"captures so far: {len(client.capture_calls)}")
    print("  The hold is total: no order, no capture, and the agent")
    print("  cannot talk its way past it. The human reviews the queue:")
    entry = gate.reject(r2.queue_id)
    print(f"    queue entry {entry.id}: REJECTED by the human.")
    print("  The agent re-drafts the month-2 charge correctly:")
    ev, pay = fixtures.scenario_s2_corrected(LAD)
    r2b = runner.attempt(ev, pay)
    show_verdict(r2b)
    assert r2.status == "held" and r2b.status == "captured"

    banner("SCENE 3 — two more ways an agent draft goes wrong")
    ev, pay = fixtures.scenario_s3(LAD)
    print(f"S3: right amount, WRONG payee ({fixtures.WRONG_PAYEE}):")
    r3 = runner.attempt(ev, pay)
    show_verdict(r3)
    ev, pay = fixtures.scenario_s4(LAD)
    print(f"\nS4: month-2 charge bundles an unquoted add-on "
          f"({fixtures.ADDON_LINE}):")
    r4 = runner.attempt(ev, pay)
    show_verdict(r4)
    assert r3.status == "held" and r4.status == "held"

    banner("LEDGER — what PayPal actually saw")
    print(f"  Orders created:  {len(client.orders)}")
    for order in client.orders.values():
        print(f"    {order.id}: {fmt_money(order.amount_cents)} "
              f"{order.currency} to {order.payee} — {order.status}")
    print(f"  Captures:        {len(client.capture_calls)} "
          f"(all from verified charges; every held draft captured $0)")
    print(f"  Drafts held:     3 (1 rejected by the human, "
          f"{len(gate.pending())} still in the queue — human decisions, "
          f"not the agent's)")
    print("\nThe gate has no execute path. Capture lives only in the")
    print("runner, and only on an allowed verdict. That is the product.")
    print("\nBoth settled charges belong to the Shenail example job, and")
    print("both were simulated: the client relationship is real (family")
    print("pilot, disclosed); the money in this demo is not.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
