---
id: LRN-SYSTEM-INVENTED-ID
title: The system invents an order id when the user gives none
status: active
confidence: provisional
applies_to: [L2, task-example]
evidence: [taxonomy/FM-001-invented-order-id.md]
probe: Does the dataset still hold cases where the user names no order id?
created: 2026-10-26
updated: 2026-10-26
---

- **Do:** keep the no-id cases in every new dataset version; they are the ones FM-001 is seen on.
- **Why:** a dataset rebuilt from recent traces lost them once, and the suite reported FM-001 as fixed.
