# ProcureAI — Development Log

**Last updated:** October 27, 2026  
**Project status:** Working local, synthetic-data Agentic AI procurement prototype. Stage 5 transaction and governance regression testing completed; production readiness has **not** been established.

## Milestones and evidence

| Milestone | Status | What was accomplished | Evidence / qualification |
|---|---|---|---|
| M1 — Product framing | Initiated | Product vision, discovery, and PRD work in `product/` | Existing product files; completeness not independently verified |
| M2 — Core technology | Demonstrated | Azure-hosted GPT-5-mini, Microsoft Agent Framework, FastAPI and Turso connected | Working agent/tool calls and backend responses in prior local demonstrations |
| M3 — Synthetic data model | Implemented | 11 procurement-domain tables and seeded synthetic materials, suppliers, contracts, employees, budgets, policies, requisitions, approvals and audit records | Schema/seed scripts and database-backed tests |
| M4 — Read-only agent tools | Demonstrated | Catalog search, eligible supplier offers and procurement validation | API tests and prior CLI/UI demonstrations |
| M5 — Governed requisition API | Implemented/tested | Server-side eligibility/policy enforcement, explicit confirmation, idempotency, budget commitment and audit entry | Transaction integrity and governance test suites |
| M6 — Manager decision API | Implemented/tested | Approval/rejection, replay-safe decision handling, budget release on rejection | Transaction integrity and identity/governance tests |
| M7 — CLI confirmation controller | Demonstrated | Explicit pre-submit confirmation and cancellation behavior | Prior user-verified manual examples |
| M8 — Streamlit Stage 1 | Demonstrated | Natural-language chat connected to AI agent | Prior user-confirmed catalog/supplier queries |
| M9 — Streamlit Stage 2 | Demonstrated | Deterministic purchase selection, quantity validation and invalidation when inputs change | Prior manual UI checks |
| M10 — Conversation-first purchasing flow | Implemented in local prototype | Natural-language discovery followed by selected material/offer, quantity, review, explicit confirmation, requisition status and manager-demo approval/rejection | Locally demonstrated in earlier development; no claim of production identity |
| M11 — Isolated test environment | Completed | `procureai-test` Turso database, `.env.test` checks, test API on port `8001`; development catalog API on port `8000` | Environment-specific `/health` responses and guarded test fixtures |
| M12 — Automated transaction/governance tests | Completed | API/catalog, transaction, negative-governance, demo-identity and manager-authorization tests | Existing suites under `tests/` |
| M13 — Concurrency and failure recovery | **Completed for single-process prototype** | Serialized in-process PR submissions; verified one competing request accepted (201), one insufficient-budget rejection (409), no overspend and budget restoration; injected post-reservation/PR-path failures and confirmed rollback/safe retry | `test_concurrent_budget.py`, `test_transaction_recovery.py`; commit `feb460d` |
| M14 — Full regression validation | **Passed** | All six automated test groups passed together | **20 passed** on October 27, 2026, reported from local `python -m pytest tests/ -v` run |
| M15 — Documentation refresh | In progress | Updating architecture, governance, test scenarios and this development log to reflect Stage 5 | Documentation changes not yet committed at this entry |
| M16 — AI evaluation and portfolio demo | Pending | Prompt-injection, tool-use, groundedness and adversarial evaluations; walkthrough and interview-ready demo evidence | No passing AI-evaluation suite claimed |

## October 27, 2026 — Stage 5 concurrency and recovery closure

### Problem encountered

An early two-request concurrency run produced **HTTP 201** for one requisition and **HTTP 500** for the competing request, rather than the intended budget rejection. The test preserved the successful requisition for diagnosis. Its $2,514.50 commitment was subsequently identified and reversed with an explicitly checked cleanup against the isolated test database.

### Change made

The requisition route was updated to serialize submissions with a Python process-local lock, retaining the database transaction (`BEGIN IMMEDIATE`), conditional budget update, idempotency fingerprint and rollback logic as the authoritative financial safeguards. Error/cleanup handling was also adjusted. This is a **single-process demonstration control**, not a multi-worker/distributed lock.

### Validation

- **Concurrent requests:** one `201 Created`, one `409 Insufficient available budget`; only one requisition committed; original test budget restored after cleanup.
- **Controlled failure recovery:** two injected failure cases passed (`PR-10` and `APR-40`); test assertions verified rollback and safe retry behavior.
- **Regression:** 20 of 20 tests passed across six suites with development and test API instances on the expected ports.
- **Source control:** concurrency/recovery changes committed and pushed to `main` as **`feb460d`** (`test: complete procurement concurrency and recovery validation`).

### Evidence limitations

These results establish behavior **only for the tested local prototype and synthetic-data scenarios**. They do not establish distributed transaction safety, full security, regulatory compliance, performance at scale or operational readiness. Tests that inject exceptions verify specific rollback paths; they are not a substitute for crash/power-loss, network-partition or multi-instance resilience testing.

## Product and engineering decisions

1. **Business authority stays in FastAPI/database code.** The LLM interprets intent and calls approved read-only tools; generated text never becomes a price, purchase authorization or approval decision.
2. **Human confirmation is explicit.** The backend revalidates eligibility, policy and budget at submission time instead of trusting earlier UI validation.
3. **Atomic writes and idempotency protect financial state.** Budget reservation, requisition and audit data belong to one transaction; safe retries reuse the original key.
4. **A process-local lock addresses the observed local contention case.** For multiple workers or deployments, implement and verify database-coordinated contention handling rather than assuming the Python lock is sufficient.
5. **Demo identities are not authentication.** Environment-selected requester/approver values permit synthetic authorization tests, but production requires verified identities and record-level RBAC.
6. **Report test scope precisely.** Twenty passing automated tests is a prototype milestone, not a claim that all AI and security risks are covered.

## Remaining work before a portfolio-complete enterprise narrative

- Run dedicated **AI agent evaluations** for grounded material/offer selection, tool-call validity, ambiguous intents, prompt injection and unauthorized action requests.
- Perform **security/governance review** of authentication, authorization, secret handling, audit completeness and UI confirmation binding; document realistic production controls.
- Document the **multi-instance concurrency design**, retries/timeouts, observability, failure ownership and deployment approach as production gaps.
- Finish documentation refresh and create a separate documentation commit after review; inspect unrelated local changes (`app.py`, `SETUP.md`, repository `.gitignore`) before staging.
- Prepare a repeatable **end-to-end demo script**, screenshots and Principal AI Product Manager interview narrative with appropriate prototype limitations.
- **Voice input/output:** explicitly deferred and not in the current development scope.

## Maintenance rule

After each demonstrated milestone, update relevant architecture, workflow, governance, test and README/portfolio material, and record its commit. Do not mark a feature or test as completed without local evidence or repeatable assertions. Never commit `.env` files, tokens or real enterprise records.
