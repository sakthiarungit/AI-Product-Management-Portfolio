# ProcureAI — AI Governance and Responsible Automation

## Scope and governance claim

ProcureAI is a **synthetic-data proof of concept**, not a certified governance solution. The design demonstrates how AI-assisted actions can be bounded by deterministic business controls. It is **not** evidence of compliance with a specific regulation or framework.

## Responsibility boundaries

| Actor/system | Permitted responsibilities | Not permitted / outstanding controls |
|---|---|---|
| LLM agent | Understand intent, choose approved read-only tools, present choices/explanations | Must not independently create requisitions, override budgets, claim employee authority or grant approval |
| Streamlit application | Hold selected IDs, show verified options, capture deliberate interaction | Must not trust generated text as approval or price source |
| FastAPI service | Resolve price and context from database; enforce eligibility, policy, budget, transaction and audit controls | Current demo-user environment variables do not provide production SSO/RBAC |
| Requester | Choose purchase intent and explicitly confirm | Cannot self-grant manager approval |
| Assigned manager | Approve or reject via the approval API | Approver identity must be real/verified before deployment |

## Key risks and mitigations

| Risk | Prototype safeguard | Remaining gap |
|---|---|---|
| Hallucinated price or nonexistent offer | API resolves IDs and supplier prices from trusted records | Need adversarial/evaluation suite |
| Unauthorized purchasing | Demo requester/approver checks in API | Replace environment identities with authenticated principals and role/record permissions |
| Duplicate transactions | Idempotency key + stored request fingerprint | Network retry and concurrency automation |
| Double budget commitment | Atomic `BEGIN IMMEDIATE` workflow and conditional update | Load/concurrency tests and database contention handling |
| Invalid contract/supplier | Backend eligibility filtering | More policy dimensions, date-edge tests |
| Unapproved high-value request | Manager threshold and approval request creation | Full delegation, hierarchy, separation of duties |
| No transaction trace | Audit log insertions for documented actions | Immutable/exportable audit retention, correlation IDs, completeness tests |
| Exposed credentials | Local `.env` and explicit no-secret repo practice | Secret rotation, vault, least privilege, automated secret scanning |
| Prompt injection or instruction override | AI tool calls are read-only | Threat-model and red-team tests; tools must remain least-privileged |

## Critical human-in-the-loop sequence

1. User selects the material and supplier offer from backend records.
2. API returns verified amount, budget and approval requirement.
3. UI displays a complete purchase review.
4. User explicitly confirms a specific transaction.
5. Backend **revalidates** policy and available budget and commits atomically.
6. For above-threshold requests, assigned manager independently approves/rejects.
7. API logs events and returns authoritative state.

A simple `confirmed: true` JSON field is **not** sufficient authorization on a public endpoint. A production system needs authenticated user identity, binding of review/confirmation to the transaction, authorization at execution, replay defenses and robust audit evidence.

## Data handling

Only synthetic catalog, user, and transaction data are intended for the portfolio. Do not publish `.env`, access tokens, keys, live employee records, enterprise purchases or real business data. When sharing demo screenshots, check that terminals, URLs and logs contain no secrets.

## AI risk-management alignment (aspirational mapping)

- **Govern:** Defined roles, approval policy, ownership of write actions.
- **Map:** Catalog errors, unauthorized writes, stale budgets, inappropriate approval routing.
- **Measure:** Planned tool accuracy, unauthorized-write attempts, duplicate protection, trace coverage.
- **Manage:** Server-side validation, human confirmation, manager approval, rollback/rejection testing.

This is a conceptual organization of risks, **not a formal assessment or certification**.

## Before any publicly accessible demo

Use read-only mode or disable write endpoints; add authentication/RBAC before enabling writes; restrict CORS/network exposure and rate-limit requests; use isolated low-privilege credentials and synthetic data; validate audit, error handling and cost ceilings.
