---
title: Reporting refresh design (draft)
type: design
status: draft
updated: 2026-02-05
---

# Reporting refresh design (draft)

**Intended.** SALES_SUMMARY keeps reading ORDERS_DAILY as a full snapshot (C-001), and
cancelled orders stay visible in it for 180 days (D-001).

**Assumption.** The order service will extend the purge of ORDERS_RAW to 180 days;
until OP-001 is resolved this rests on claim C-002, which is `conflicting`.
