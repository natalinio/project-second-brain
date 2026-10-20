---
title: ORDERS_DAILY
type: data-object
status: draft
origin: curated
evidence: [primary-doc, verbal]
evidence_note: "grain and schedule from the specification; late-arrival behaviour from the kickoff"
domain: orders
defines: ORDERS_DAILY
updated: 2026-02-04
---

# ORDERS_DAILY

## Purpose

Nightly snapshot of all orders with customer attributes, the input of every sales report.

## Grain and keys

- One row per order (`order_id`), full snapshot rebuilt daily by JOB_ORDERS_LOAD
  — `knowledge/extracted/specs/order-service-spec-v1-2.md` (§2).
- Orders arriving after 02:00 appear the next day (verbal, kickoff 2026-01-28).

## Columns

Observed in the sample (`SELECT * FROM orders_sample`):

| Column | Type | Description |
|---|---|---|
| order_id | integer | Order identifier |
| customer_id | text | Key to CUSTOMER_MASTER |
| order_date | date | Order creation date |
| status | text | DELIVERED, SHIPPED, CANCELLED, RETURNED |
| amount | decimal | Order value |
| currency | text | ISO currency |

## Open questions

- Retention of cancelled orders: OP-001, claim C-002.
