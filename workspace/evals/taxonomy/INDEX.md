# Failure mode register

Ids are minted **here**, sequentially, and never reused or renumbered. `FM-003` appears in
dataset rows, evaluator definitions, CTRF tags, baselines, and every scorecard comparison for as
long as the system exists — renumbering breaks every historical comparison silently.

A failure mode that stops being relevant is `retired`. Its file stays.

| Id | Statement | Severity | Frequency | Detector | Status | First seen |
|---|---|---|---|---|---|---|
| FM-001 | States an order id that did not come from a tool result | blocking | 4% | assert:no-invented-ids | open | TB-2026-09-10-001 |

## Retired
| Id | Statement | Retired | Why |
|---|---|---|---|
