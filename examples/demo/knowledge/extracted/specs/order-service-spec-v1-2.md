---
title: Order service specification v1.2
type: spec
status: checked
status_note: "checked 2026-01-21: ok (demo stand-in for a Docling extraction)"
origin: extracted
evidence: primary-doc
domain: orders
source: source/specs/order-service-spec-v1.2.docx
extracted: 2026-01-21
updated: 2026-01-21
tags: []
---

> Auto-extracted by Docling from `source/specs/order-service-spec-v1.2.docx`.
> The body is immutable: corrections and syntheses go to `knowledge/curated/`.

# Order service specification v1.2

## 1. Scope

The order service records every customer order in the operational table ORDERS_RAW.
Orders move through the states NEW, PAID, SHIPPED, DELIVERED, RETURNED and CANCELLED.

## 2. Data hand-off to reporting

| Step | Job | Reads | Writes | Schedule |
|---|---|---|---|---|
| Load | JOB_ORDERS_LOAD | ORDERS_RAW, CUSTOMER_MASTER | ORDERS_DAILY | daily 02:00 |
| Aggregate | JOB_SALES_AGG | ORDERS_DAILY | SALES_SUMMARY | daily 04:00 |
| Publish | JOB_REPORT_PUBLISH | SALES_SUMMARY | SALES_REPORT | daily 06:00 |

ORDERS_DAILY is rebuilt as a full snapshot every night; it is not incremental.

## 3. Retention

Cancelled orders are purged from ORDERS_RAW after 90 days. Delivered orders are kept
for seven years.
