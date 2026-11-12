"""
fixtures.py — demo data pack for the Claim Court PayPal gate (shared core).

ALL AMOUNTS IN THIS FILE ARE SANDBOX DEMO AMOUNTS. They are the candidate
SiteBefore pricing ladders from the pricing decision pack, used ONLY so the
demo and tests have concrete numbers. They are not published prices, and
nothing in this project puts them on any public surface.

Source: ~/workspace/intel/2026-11-04-paypal-build-readiness-pack.md §3.
Ladder pick is a founder gate; the default here is Ladder C (the pack's
recommendation). Changing ladders changes this file only — no code changes.

Money is integer cents everywhere in this project (no floats near money).
"""

from __future__ import annotations

from dataclasses import dataclass

from comparator import ChargeEvidence, ProposedLine, ProposedPayment, Quote, QuoteLine


def cad(dollars: float) -> int:
    """Dollars -> integer cents."""
    return int(round(dollars * 100))


# Line names, as they appear on quotes and payment drafts.
BUILD_LINE = "Website Build"
CARE_LINE = "Care Plan"
ADDON_LINE = "AI-Visibility Add-On"

# Demo identities. The payee is a sandbox fixture, not a real account.
# The client is a REAL business — Shenail Hair Salon & Nail Bar in
# Niagara Falls (shenailhairlounge.ca), SiteBefore's family pilot
# client, named with disclosure wherever it appears. The scenario
# built around it is simulated end to end: the quote in this file is
# the demo's illustrative quote, and no payment in this project is a
# real transaction, revenue, or a live deployment.
DEMO_PAYEE = "SiteBefore (sandbox business)"
DEMO_CLIENT = "Shenail Hair Salon & Nail Bar — Niagara Falls (shenailhairlounge.ca)"
WRONG_PAYEE = "Northgate Studio (demo — wrong payee)"


@dataclass(frozen=True)
class Ladder:
    """One candidate pricing ladder. All fields are DEMO amounts in cents."""
    name: str
    build_cents: int
    care_cents: int
    addon_cents: int
    currency: str = "CAD"

    @property
    def first_payment_cents(self) -> int:
        return self.build_cents + self.care_cents


LADDERS = {
    # A — Match-the-anchor
    "A": Ladder("A", build_cents=cad(790), care_cents=cad(99),
                addon_cents=cad(49)),
    # B — Premium-build
    "B": Ladder("B", build_cents=cad(1650), care_cents=cad(149),
                addon_cents=cad(99)),
    # C — Hybrid (recommended in the pricing pack; default for the demo)
    "C": Ladder("C", build_cents=cad(900), care_cents=cad(99),
                addon_cents=cad(49)),
}

DEFAULT_LADDER = "C"


def quote_for(ladder: Ladder) -> Quote:
    """The founder-approved quote = the evidence every payment is graded
    against. The demo quote contains the Build and the Care plan; the
    AI-visibility add-on is priced in the ladder but deliberately NOT in
    the demo quote (that is what makes scenario S4 a PARTIAL)."""
    return Quote(
        id=f"QUOTE-DEMO-{ladder.name}-001",
        payee=DEMO_PAYEE,
        currency=ladder.currency,
        lines=(
            QuoteLine(BUILD_LINE, ladder.build_cents),
            QuoteLine(CARE_LINE, ladder.care_cents),
        ),
    )


def evidence_payment_1(ladder: Ladder) -> ChargeEvidence:
    """First charge occasion: Build + Care month 1 are chargeable."""
    return ChargeEvidence(quote=quote_for(ladder), occasion="payment_1",
                          chargeable=(BUILD_LINE, CARE_LINE))


def evidence_month_2(ladder: Ladder) -> ChargeEvidence:
    """Month-2 occasion: only the Care plan is chargeable. The Build line
    is in the quote but NOT in evidence for this charge — the S2 conflict."""
    return ChargeEvidence(quote=quote_for(ladder), occasion="month_2_care",
                          chargeable=(CARE_LINE,))


# ---------------------------------------------------------------------------
# Scenario case builders (readiness pack §2). Each returns
# (evidence, proposed_payment) so tests and, later, the demo surface drive
# the exact same cases.
# ---------------------------------------------------------------------------

def scenario_s1(ladder: Ladder):
    """S1 — happy path: first payment exactly as quoted -> CORROBORATED."""
    payment = ProposedPayment(
        payee=DEMO_PAYEE, currency=ladder.currency,
        amount_cents=ladder.first_payment_cents,
        lines=(
            ProposedLine(BUILD_LINE, ladder.build_cents),
            ProposedLine(CARE_LINE, ladder.care_cents),
        ),
        note="S1 happy-path checkout (demo payment 1)",
    )
    return evidence_payment_1(ladder), payment


def scenario_s2(ladder: Ladder):
    """S2 — the money shot: the agent drafts the month-2 care charge at the
    full first-payment amount, Build line repeated -> CONFLICTED, held."""
    payment = ProposedPayment(
        payee=DEMO_PAYEE, currency=ladder.currency,
        amount_cents=ladder.first_payment_cents,
        lines=(
            ProposedLine(BUILD_LINE, ladder.build_cents),
            ProposedLine(CARE_LINE, ladder.care_cents),
        ),
        note="S2 agent error: month-2 charge repeats the whole first payment",
    )
    return evidence_month_2(ladder), payment


def scenario_s2_corrected(ladder: Ladder):
    """S2 follow-up: after the founder rejects the held draft, the agent
    re-drafts the month-2 charge correctly -> CORROBORATED, releases."""
    payment = ProposedPayment(
        payee=DEMO_PAYEE, currency=ladder.currency,
        amount_cents=ladder.care_cents,
        lines=(ProposedLine(CARE_LINE, ladder.care_cents),),
        note="S2 corrected re-draft after founder rejection",
    )
    return evidence_month_2(ladder), payment


def scenario_s3(ladder: Ladder):
    """S3 — payee conflict: correct amount and lines, wrong payee ->
    CONFLICTED, held before it ever reaches buyer approval."""
    payment = ProposedPayment(
        payee=WRONG_PAYEE, currency=ladder.currency,
        amount_cents=ladder.first_payment_cents,
        lines=(
            ProposedLine(BUILD_LINE, ladder.build_cents),
            ProposedLine(CARE_LINE, ladder.care_cents),
        ),
        note="S3 payee conflict",
    )
    return evidence_payment_1(ladder), payment


def scenario_s4(ladder: Ladder):
    """S4 — unquoted add-on: month-2 charge = Care + an AI-visibility line
    that is not in the quote -> PARTIAL, held (generates the queue-history
    line shown in video scene 3)."""
    total = ladder.care_cents + ladder.addon_cents
    payment = ProposedPayment(
        payee=DEMO_PAYEE, currency=ladder.currency,
        amount_cents=total,
        lines=(
            ProposedLine(CARE_LINE, ladder.care_cents),
            ProposedLine(ADDON_LINE, ladder.addon_cents),
        ),
        note="S4 unquoted add-on bundled into the month-2 charge",
    )
    return evidence_month_2(ladder), payment
