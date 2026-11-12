"""
comparator.py — the Claim Court claim comparator (deterministic grader).

Compares a proposed payment's claims (amount, currency, payee, line items)
against a founder-approved quote — the evidence — and grades every claim
individually before aggregating to one verdict, in the same vocabulary as
the existing why-agent gate work:

  CORROBORATED  every claim checks out against the evidence
  CONFLICTED    at least one claim contradicts the evidence
  PARTIAL       no contradiction, but at least one claim is uncorroborated
                (not in the evidence, or an expected line is missing)

No model is involved in a verdict: this is a deterministic comparison, so
the same payment against the same quote always grades the same way, and
every grade carries a human-readable reason (the demo's gate panel and the
founder's approval queue render these strings verbatim).

Grading rules (per claim):
  payee     equal to the quote's payee -> CORROBORATED, else CONFLICTED.
  currency  equal to the quote's currency -> CORROBORATED, else CONFLICTED.
  line      in the quote AND chargeable on this occasion AND amount equal
            -> CORROBORATED.
            in the quote, chargeable, amount differs -> CONFLICTED.
            in the quote but NOT chargeable on this occasion (e.g. the
            one-time Build line repeated on a month-2 charge)
            -> CONFLICTED ("not in evidence for this charge").
            not in the quote at all -> UNCORROBORATED (an unquoted add-on
            is not contradicted, it is simply not evidenced).
            a line name repeated in the proposal -> the repeat is
            CONFLICTED (duplicate).
            a chargeable line missing from the proposal -> UNCORROBORATED.
  amount    total != sum of the payment's own lines -> CONFLICTED
            (internally inconsistent draft).
            total == expected total for this occasion -> CORROBORATED.
            total above expected, with the excess exactly explained by
            uncorroborated (unquoted) lines and every quoted line clean
            -> UNCORROBORATED (this is the S4 shape).
            otherwise -> CONFLICTED ("expected $X, attempted $Y").

Aggregation: any CONFLICTED claim -> CONFLICTED; else any UNCORROBORATED
claim -> PARTIAL; else CORROBORATED.

Money is integer cents everywhere. Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

CORROBORATED = "CORROBORATED"
CONFLICTED = "CONFLICTED"
PARTIAL = "PARTIAL"
UNCORROBORATED = "UNCORROBORATED"   # per-claim grade only; never a verdict


def fmt_money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


# ---------------------------------------------------------------------------
# Evidence and proposal shapes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class QuoteLine:
    name: str
    amount_cents: int


@dataclass(frozen=True)
class Quote:
    """The founder-approved quote: the evidence. Approving the quote is
    the human act; payments are graded against it, never against an
    agent's say-so."""
    id: str
    payee: str
    currency: str
    lines: tuple

    def line(self, name: str) -> Optional[QuoteLine]:
        for line in self.lines:
            if line.name == name:
                return line
        return None


@dataclass(frozen=True)
class ChargeEvidence:
    """Which part of the quote is in evidence for one charge occasion.
    The quote authorises the Build once and the Care plan monthly; a
    month-2 charge may only claim the Care line."""
    quote: Quote
    occasion: str                       # e.g. "payment_1" | "month_2_care"
    chargeable: tuple                   # line names chargeable this occasion

    def expected_total_cents(self) -> int:
        total = 0
        for name in self.chargeable:
            line = self.quote.line(name)
            if line is None:
                raise ValueError(
                    f"chargeable line {name!r} is not in quote {self.quote.id}")
            total += line.amount_cents
        return total


@dataclass(frozen=True)
class ProposedLine:
    name: str
    amount_cents: int


@dataclass(frozen=True)
class ProposedPayment:
    """A payment an agent proposes to make. Claims, nothing more — the
    comparator grades it; it does not execute anything."""
    payee: str
    currency: str
    amount_cents: int
    lines: tuple
    note: str = ""


# ---------------------------------------------------------------------------
# Result shapes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClaimGrade:
    claim: str                          # "payee" | "currency" | "amount" | "line:<name>"
    status: str                         # CORROBORATED | CONFLICTED | UNCORROBORATED
    detail: str                         # human-readable reason


@dataclass(frozen=True)
class ComparisonResult:
    verdict: str                        # CORROBORATED | PARTIAL | CONFLICTED
    claims: tuple                       # tuple[ClaimGrade, ...]
    expected_total_cents: int
    proposed_total_cents: int

    def claim(self, name: str) -> Optional[ClaimGrade]:
        for grade in self.claims:
            if grade.claim == name:
                return grade
        return None

    def summary(self) -> str:
        parts = "; ".join(f"{g.claim}: {g.status} ({g.detail})"
                          for g in self.claims)
        return f"{self.verdict} — {parts}"


# ---------------------------------------------------------------------------
# The grader
# ---------------------------------------------------------------------------

def grade_payment(evidence: ChargeEvidence,
                  payment: ProposedPayment) -> ComparisonResult:
    """Grade every claim of `payment` against `evidence`. Deterministic."""
    quote = evidence.quote
    grades = []

    # -- payee -------------------------------------------------------------
    if payment.payee == quote.payee:
        grades.append(ClaimGrade(
            "payee", CORROBORATED, f"payee is {quote.payee!r}, as quoted"))
    else:
        grades.append(ClaimGrade(
            "payee", CONFLICTED,
            f"payment names {payment.payee!r}; quote payee is {quote.payee!r}"))

    # -- currency ------------------------------------------------------------
    if payment.currency == quote.currency:
        grades.append(ClaimGrade(
            "currency", CORROBORATED, f"currency {quote.currency}, as quoted"))
    else:
        grades.append(ClaimGrade(
            "currency", CONFLICTED,
            f"payment is in {payment.currency}; quote is in {quote.currency}"))

    # -- line items ----------------------------------------------------------
    seen = set()
    unknown_lines_total = 0
    for proposed in payment.lines:
        claim_name = f"line:{proposed.name}"
        if proposed.name in seen:
            grades.append(ClaimGrade(
                claim_name, CONFLICTED,
                f"{proposed.name!r} appears more than once in the payment"))
            continue
        seen.add(proposed.name)
        quoted = quote.line(proposed.name)
        if quoted is None:
            unknown_lines_total += proposed.amount_cents
            grades.append(ClaimGrade(
                claim_name, UNCORROBORATED,
                f"{proposed.name!r} ({fmt_money(proposed.amount_cents)}) "
                f"is not in the quote"))
        elif proposed.name not in evidence.chargeable:
            grades.append(ClaimGrade(
                claim_name, CONFLICTED,
                f"{proposed.name!r} is in the quote but not in evidence "
                f"for this charge ({evidence.occasion})"))
        elif proposed.amount_cents != quoted.amount_cents:
            grades.append(ClaimGrade(
                claim_name, CONFLICTED,
                f"{proposed.name!r} is {fmt_money(proposed.amount_cents)}; "
                f"quote says {fmt_money(quoted.amount_cents)}"))
        else:
            grades.append(ClaimGrade(
                claim_name, CORROBORATED,
                f"{proposed.name!r} {fmt_money(proposed.amount_cents)}, "
                f"as quoted"))

    # -- expected lines missing from the proposal ----------------------------
    for name in evidence.chargeable:
        if name not in seen:
            grades.append(ClaimGrade(
                f"line:{name}", UNCORROBORATED,
                f"{name!r} is chargeable on this occasion but missing "
                f"from the payment"))

    # -- amount (total) --------------------------------------------------------
    expected = evidence.expected_total_cents()
    lines_sum = sum(line.amount_cents for line in payment.lines)
    line_statuses = [g.status for g in grades if g.claim.startswith("line:")]
    if payment.amount_cents != lines_sum:
        grades.append(ClaimGrade(
            "amount", CONFLICTED,
            f"total {fmt_money(payment.amount_cents)} does not equal the "
            f"sum of its line items {fmt_money(lines_sum)}"))
    elif payment.amount_cents == expected:
        grades.append(ClaimGrade(
            "amount", CORROBORATED,
            f"total {fmt_money(expected)} matches the quoted charge for "
            f"{evidence.occasion}"))
    elif (payment.amount_cents > expected
          and payment.amount_cents - expected == unknown_lines_total
          and unknown_lines_total > 0
          and CONFLICTED not in line_statuses):
        grades.append(ClaimGrade(
            "amount", UNCORROBORATED,
            f"total {fmt_money(payment.amount_cents)} exceeds the quoted "
            f"{fmt_money(expected)} only by unquoted lines "
            f"({fmt_money(unknown_lines_total)})"))
    else:
        grades.append(ClaimGrade(
            "amount", CONFLICTED,
            f"expected {fmt_money(expected)}, "
            f"attempted {fmt_money(payment.amount_cents)}"))

    # -- aggregate -------------------------------------------------------------
    statuses = [g.status for g in grades]
    if CONFLICTED in statuses:
        verdict = CONFLICTED
    elif UNCORROBORATED in statuses:
        verdict = PARTIAL
    else:
        verdict = CORROBORATED

    return ComparisonResult(
        verdict=verdict, claims=tuple(grades),
        expected_total_cents=expected,
        proposed_total_cents=payment.amount_cents)
