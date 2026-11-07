# FM-001 — States an order id that did not come from a tool result

## Statement
When `get_order` returns nothing — a wrong id, a typo, an order belonging to someone else — the
system answers as though the order exists and states an order id it constructed itself. The user
then quotes that id back to support, where it does not resolve.

## Evidence
- TB-2026-09-10-001 / trace_8f2a1c — user gave a 6-digit id, tool returned empty, answer said
  "your order 881234 is out for delivery"
- TB-2026-09-10-001 / trace_b31e09 — no id in the message at all; answer invented one and gave
  a status for it
- TB-2026-09-10-001 / trace_44c7d2 — id belonged to another customer; tool refused; answer
  reported a plausible status anyway

## Frequency
4 of 100 coded traces. Weighted ≈ 1.1% of traffic (over-sampled stratum: not-found data state).

## Severity
blocking — the user is told something false about their own money and plans around it, and the
invented id sends support on a search that cannot succeed.

## Detector
assert:no-invented-ids — fully decidable in code: every id-shaped token in the output must appear
in some tool result. No judge needed, so no labels and no calibration.

## Status
open
