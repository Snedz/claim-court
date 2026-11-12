"""
Tests for comparator.py — run: python3 -m unittest -v

Covers the readiness pack's comparator case list (§4 task 4): exact match,
amount off, payee off, extra line, missing line, duplicate line, currency
mismatch — plus the occasion rule (quoted line not chargeable on this
charge), the PARTIAL aggregation (S4), and internal inconsistency.
All amounts are sandbox DEMO amounts (Ladder C unless stated).
"""

import unittest

import fixtures
from comparator import (CONFLICTED, CORROBORATED, PARTIAL, UNCORROBORATED,
                        ProposedLine, ProposedPayment, grade_payment)

LAD = fixtures.LADDERS["C"]          # Build $900, Care $99, add-on $49


def payment(**overrides):
    """The S1 payment, with any field overridden."""
    base = dict(
        payee=fixtures.DEMO_PAYEE, currency="CAD",
        amount_cents=LAD.first_payment_cents,
        lines=(ProposedLine(fixtures.BUILD_LINE, LAD.build_cents),
               ProposedLine(fixtures.CARE_LINE, LAD.care_cents)),
    )
    base.update(overrides)
    return ProposedPayment(**base)


class ComparatorTests(unittest.TestCase):

    def test_exact_match_is_corroborated(self):
        evidence, pay = fixtures.scenario_s1(LAD)
        result = grade_payment(evidence, pay)
        self.assertEqual(result.verdict, CORROBORATED)
        for grade in result.claims:
            self.assertEqual(grade.status, CORROBORATED, grade.claim)
        self.assertEqual(result.expected_total_cents, 99900)
        self.assertEqual(result.proposed_total_cents, 99900)

    def test_amount_off_is_conflicted(self):
        # Build line drafted $50 high; total follows the lines.
        pay = payment(
            amount_cents=LAD.first_payment_cents + 5000,
            lines=(ProposedLine(fixtures.BUILD_LINE, LAD.build_cents + 5000),
                   ProposedLine(fixtures.CARE_LINE, LAD.care_cents)))
        result = grade_payment(fixtures.evidence_payment_1(LAD), pay)
        self.assertEqual(result.verdict, CONFLICTED)
        self.assertEqual(
            result.claim(f"line:{fixtures.BUILD_LINE}").status, CONFLICTED)
        self.assertEqual(result.claim("amount").status, CONFLICTED)

    def test_payee_off_is_conflicted(self):
        evidence, pay = fixtures.scenario_s3(LAD)
        result = grade_payment(evidence, pay)
        self.assertEqual(result.verdict, CONFLICTED)
        self.assertEqual(result.claim("payee").status, CONFLICTED)
        # Amount and lines are clean — the payee alone sinks it.
        self.assertEqual(result.claim("amount").status, CORROBORATED)

    def test_extra_unquoted_line_is_partial(self):
        evidence, pay = fixtures.scenario_s4(LAD)
        result = grade_payment(evidence, pay)
        self.assertEqual(result.verdict, PARTIAL)
        self.assertEqual(
            result.claim(f"line:{fixtures.ADDON_LINE}").status,
            UNCORROBORATED)
        self.assertEqual(
            result.claim(f"line:{fixtures.CARE_LINE}").status, CORROBORATED)
        self.assertEqual(result.claim("amount").status, UNCORROBORATED)

    def test_missing_line_is_not_corroborated(self):
        # Payment 1 drafted with the Care line forgotten.
        pay = payment(amount_cents=LAD.build_cents,
                      lines=(ProposedLine(fixtures.BUILD_LINE,
                                          LAD.build_cents),))
        result = grade_payment(fixtures.evidence_payment_1(LAD), pay)
        self.assertEqual(result.verdict, CONFLICTED)
        missing = result.claim(f"line:{fixtures.CARE_LINE}")
        self.assertEqual(missing.status, UNCORROBORATED)
        self.assertIn("missing", missing.detail)

    def test_duplicate_line_is_conflicted(self):
        pay = payment(
            amount_cents=LAD.first_payment_cents + LAD.care_cents,
            lines=(ProposedLine(fixtures.BUILD_LINE, LAD.build_cents),
                   ProposedLine(fixtures.CARE_LINE, LAD.care_cents),
                   ProposedLine(fixtures.CARE_LINE, LAD.care_cents)))
        result = grade_payment(fixtures.evidence_payment_1(LAD), pay)
        self.assertEqual(result.verdict, CONFLICTED)
        care_grades = [g for g in result.claims
                       if g.claim == f"line:{fixtures.CARE_LINE}"]
        self.assertIn(CONFLICTED, [g.status for g in care_grades])

    def test_currency_mismatch_is_conflicted(self):
        pay = payment(currency="USD")
        result = grade_payment(fixtures.evidence_payment_1(LAD), pay)
        self.assertEqual(result.verdict, CONFLICTED)
        self.assertEqual(result.claim("currency").status, CONFLICTED)

    def test_quoted_line_not_chargeable_this_occasion_is_conflicted(self):
        # The S2 core: Build is in the quote, but not in evidence for the
        # month-2 charge.
        evidence, pay = fixtures.scenario_s2(LAD)
        result = grade_payment(evidence, pay)
        self.assertEqual(result.verdict, CONFLICTED)
        build = result.claim(f"line:{fixtures.BUILD_LINE}")
        self.assertEqual(build.status, CONFLICTED)
        self.assertIn("not in evidence for this charge", build.detail)
        amount = result.claim("amount")
        self.assertEqual(amount.status, CONFLICTED)
        self.assertIn("expected $99.00", amount.detail)
        self.assertIn("attempted $999.00", amount.detail)

    def test_total_not_matching_its_own_lines_is_conflicted(self):
        pay = payment(amount_cents=LAD.first_payment_cents + 100)
        result = grade_payment(fixtures.evidence_payment_1(LAD), pay)
        self.assertEqual(result.verdict, CONFLICTED)
        self.assertEqual(result.claim("amount").status, CONFLICTED)
        self.assertIn("does not equal", result.claim("amount").detail)

    def test_verdicts_are_ladder_independent(self):
        # Same shapes, Ladder A numbers: S1 clean, S2 conflicted, S4 partial.
        lad_a = fixtures.LADDERS["A"]
        self.assertEqual(grade_payment(*fixtures.scenario_s1(lad_a)).verdict,
                         CORROBORATED)
        self.assertEqual(grade_payment(*fixtures.scenario_s2(lad_a)).verdict,
                         CONFLICTED)
        self.assertEqual(grade_payment(*fixtures.scenario_s4(lad_a)).verdict,
                         PARTIAL)


if __name__ == "__main__":
    unittest.main()
