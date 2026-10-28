# ProcureAI — AI Governance and Responsible Automation

**Status:** As-built synthetic-data prototype, updated October 2026. **Not production certified or a compliance attestation.**

## 1. Scope and governance objective

ProcureAI demonstrates a governed procurement assistant: an Azure-hosted GPT-5-mini agent, built with Microsoft Agent Framework, helps users discover materials and supplier offers, while Streamlit and FastAPI control the purchase workflow. The language model is not trusted to authorize financial commitments. Server-side business rules, explicit user confirmation, and manager decisions govern writes to the Turso/libSQL database.

This document distinguishes **implemented and tested** safeguards from **future production requirements**. The prototype uses synthetic materials, suppliers, employees, budgets, policies, purchase requisitions, approvals, and audit logs.

## 2. Responsibility and authority boundaries

| Actor or layer | Implemented responsibility | Boundary or limitation |
|---|---|---|
| AI agent | Interpret natural-language requests and use approved read-only catalog, offer, and validation tools | Does not directly write to the database or authorize spending; model text is not an authoritative price, role, or approval |
| Streamlit UI | Guide selection, show verified data, request explicit confirmation, and display requisition/approval results | UI state and `confirmed: true` are not substitutes for authenticated authorization |
| FastAPI | Check offer/contract/supplier eligibility, requester identity in demo records, price, active policy, manager route, and available budget; perform transactional writes | Demo identity is supplied through environment settings rather than verified user sessions |
| Requester | Select a verified offer, choose quantity, and confirm a requisition | Cannot independently grant the assigned manager's approval |
| Assigned manager | Approve or reject through a dedicated API workflow | Current demo manager identity is not production SSO or identity-provider integration |
| Database | Store transactional procurement state, commitments, approvals, and audit events | Distributed contention, immutable audit storage, and operational resilience have not been fully validated |

## 3. Governed purchase and approval sequence

1. The user describes a procurement need; the agent searches using **read-only** tools.
2. The user chooses a material and eligible supplier offer returned by trusted API records.
3. FastAPI validates quantity, authoritative price, contract dates, supplier status, policy, approval threshold, budget, and requester/manager routing.
4. The interface presents the transaction for **explicit human confirmation**.
5. The requisition endpoint independently checks current rules and funds again, then commits budget reservation, requisition, optional approval request, and audit event within a database transaction.
6. Above-threshold requests remain pending until the assigned manager approves or rejects. Rejection releases the reserved budget under the tested workflow.
7. The API returns the recorded state; the AI's description cannot change that state.

**Critical distinction:** The prototype's `confirmed: true` field records demo confirmation intent; it does **not** authenticate a human. Public write endpoints must remain disabled or restricted until proper identity and authorization are implemented.

## 4. Governance risk and control register

| Risk | Current implemented or tested safeguard | Remaining production requirement |
|---|---|---|
| Hallucinated price or nonexistent offer | Backend resolves offer IDs, validates eligibility, and obtains price from database records | Dedicated AI evaluation for factuality, tool choice, ambiguity, and malicious content |
| Invalid contract or supplier | Active status and effective contract date checks; negative tests pass | Broader policy coverage, ownership, and contract lifecycle rules |
| Unauthorized requester | Inactive requester is rejected in synthetic identity tests | SSO/OIDC, verified claims, server-side record-level RBAC, access reviews |
| Unauthorized manager | Unassigned employee cannot approve in synthetic identity tests | Verified approver identity, delegation, separation of duties, approval evidence |
| Spending without human consent | Requisition API rejects missing explicit confirmation | Bind a specific authenticated approval to reviewed transaction details; replay protection |
| Duplicate requisition | Idempotency key and payload fingerprint; repeated successful request tested | Retry policy, key retention/expiry, cross-service consistency, network-failure reconciliation |
| Insufficient budget | Conditional SQL budget update rejects transactions that lack available funds | Multi-worker/distributed contention strategy, load testing, operational monitoring |
| Concurrent budget requests | Single-process submission lock plus conditional budget update; simultaneous competing requests tested | Database-coordinated concurrency and failure handling across multiple API processes/instances |
| Partial transaction after failure | Controlled failure injection tests verify rollback and safe retry | Broader fault injection, crash/restart and uncertain-commit reconciliation tests |
| Missing traceability | Requisition and approval workflows write audit records | Audit completeness testing, correlation IDs, retention rules, tamper evidence and monitoring |
| Prompt injection | Agent tools are read-only; write paths have separate business controls | Explicit red-team tests, data/tool boundary validation, least-privilege tool credentials |
| Secret exposure | Local `.env` / `.env.test` excluded from committed source | Managed secret store, rotation, environment isolation, secret scanning, access controls |

## 5. Financial integrity: atomicity, concurrency, and recovery

The requisition service uses a database transaction (`BEGIN IMMEDIATE`) and an authoritative **conditional budget UPDATE**. The reservation only succeeds when enough uncommitted funds remain. The same transaction writes the requisition, optional approval task, and audit event; errors cause rollback.

A **process-local lock** serializes submissions inside the current single Uvicorn/Python process. This is a deliberately limited prototype safeguard: it does not synchronize multiple worker processes, instances, or external database writers. The conditional budget check remains necessary even with the lock.

Idempotency keys are bound to a requester, offer, and quantity fingerprint so an identical retry can return the existing requisition rather than commit the budget a second time; reuse of a key for different request data is rejected.

### Tested reliability scenarios

- Two simultaneous requests each fit independently but exceed available funds together: **one HTTP 201 created**, **one HTTP 409 insufficient budget**, and the budget restored after test cleanup.
- Controlled error during requisition creation: rollback and safe retry tested.
- Controlled error during approval-record creation: rollback and safe retry tested.
- Manager rejection releases budget, and repeated manager decisions are handled idempotently in existing transaction tests.

These are local/single-process test results, **not** proof of distributed serializability, exactly-once execution in every failure mode, or production reliability.

## 6. Test evidence and current coverage

**October 2026 milestone:** Full regression run reported **20 tests passed out of 20 collected**, across six suites.

| Test suite | Passed |
|---|---:|
| Catalog and API | 4 |
| Transaction integrity | 5 |
| Negative governance | 6 |
| Synthetic identity and authorization | 2 |
| Competing budget submissions | 1 |
| Transaction rollback and safe retry | 2 |
| **Total** | **20** |

The tests ran against a local development API for read-only catalog checks and a separately configured **`procureai-test`** database/API for mutation tests. See `docs/Test-Scenarios.md` and the repository's `tests/` directory for executable evidence. Results demonstrate the tested cases only.

## 7. AI risk-management alignment (illustrative)

The following is a **conceptual mapping**, not a formal AI risk assessment or certification:

- **Govern:** Clear ownership of agent tools, API writes, requester confirmation, manager authorization, and financial policy.
- **Map:** Risks of false catalog claims, unauthorized actions, inadequate funds, duplicate transactions, approval errors, and prompt injection.
- **Measure:** Automated negative, authorization, transaction, concurrency, and recovery tests; planned AI evaluation metrics for task success and tool accuracy.
- **Manage:** Deterministic backend validation, transaction rollback, idempotency, explicit approval, auditing, and documented production gaps.

## 8. Data and secret-handling expectations

Use **synthetic records only** in the public portfolio. Do not commit `.env`, `.env.test`, Turso tokens, cloud access tokens, live company information, or actual employee/purchase data. Review screenshots, console output, and logs before publishing. Ensure development and test databases remain distinct; the mutation-test suite must target only `procureai-test`.

## 9. Production-readiness gates — not yet implemented

Before exposing write APIs to real users or connecting to an enterprise purchasing system:

1. Replace environment-based demo identities with authenticated SSO/OIDC sessions, record-level RBAC, and separation-of-duties checks.
2. Bind user confirmation to immutable transaction details and enforce authorization again at execution.
3. Replace or supplement the process-local lock with verified database-coordinated contention handling, bounded retries, and uncertain-outcome reconciliation for multi-worker/multi-instance deployment.
4. Add comprehensive AI evaluations, prompt-injection/adversarial tests, and explicit tool-permission boundaries.
5. Add centralized audit retention, trace IDs, operational alerts, metrics, incident response, and recovery procedures.
6. Enforce secrets management, least-privilege database access, rate limits, secure deployment, and credential rotation.
7. Validate end-to-end integrations, performance, and business-owner acceptance before real financial transactions.

## 10. Portfolio claim

**Accurate claim:** "Built a synthetic-data Agentic AI procurement prototype with read-only AI tools, backend-enforced purchasing and approval controls, and 20 passing automated tests covering core API, authorization, negative governance, concurrency, and rollback/retry behavior."

**Do not claim:** Production-grade SSO, distributed transaction safety, certified AI governance compliance, or enterprise deployment readiness.
