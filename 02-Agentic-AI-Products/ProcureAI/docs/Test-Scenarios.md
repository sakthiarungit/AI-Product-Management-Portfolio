# ProcureAI — Test Scenarios and Evidence

**Status:** Stage 5 validation completed in October 2026 for the local, single-process prototype. **20 automated tests passed in one full regression run**, as reported from `python -m pytest tests/ -v`. This is not a production-safety or regulatory-compliance certification.

## Evidence legend

- **Automated — passed:** Included in the full 20-test pytest run reported by the project owner.
- **Manual — observed:** Confirmed in earlier local demonstrations; identifiers are historical examples, not fixtures for repeated testing.
- **Pending:** Not yet validated by a specific repeatable test or complete evidence set.
- All sample procurement records are synthetic. Write tests must target the isolated `procureai-test` Turso database.

## Automated regression result

| Suite | Tests | Status | Coverage |
|---|---:|---|---|
| `tests/test_procurement_api.py` | 4 | Passed | Health, material search, supplier offers, budget/policy validation |
| `tests/test_transaction_integrity.py` | 5 | Passed | Seed/database check, idempotency, approvals, rejection and budget release, insufficient funds |
| `tests/test_negative_governance.py` | 6 | Passed | Confirmation, invalid/expired/inactive/unknown offers, invalid quantity, unknown approval |
| `tests/test_identity_governance.py` | 2 | Passed | Inactive requester, employee without assigned approval authority |
| `tests/test_concurrent_budget.py` | 1 | Passed | Two simultaneous competing requests, one HTTP 201 and one budget-related HTTP 409; budget restored |
| `tests/test_transaction_recovery.py` | 2 | Passed | Injected failure during PR insertion and approval insertion; rollback and safe retry |
| **Total** | **20** | **20 passed** | Current isolated prototype behavior |

### Representative assertions and evidence

| ID | Test case | Verified expectation |
|---|---|---|
| A01 | Backend health | API responds successfully |
| A02 | Material search | Active helmet catalog results returned |
| A03 | Supplier offers | Eligible offers returned for selected material |
| A04 | Budget validation | Read-only budget/policy check works |
| A05 | Seed database | Six expected synthetic materials present |
| A06 | Small purchase and idempotency | One $235 requisition; same key returns original; changed payload with same key rejected |
| A07 | Manager approval and replay | $940 PR pending; manager approves; repeat decision does not reapply |
| A08 | Manager rejection | Rejected PR releases its outstanding budget commitment |
| A09 | Insufficient budget | HTTP 409; no new PR or commitment |
| A10 | Missing confirmation | Write request blocked |
| A11 | Expired contract | Offer rejected |
| A12 | Inactive supplier | Offer rejected |
| A13 | Unknown offer | Offer rejected |
| A14 | Invalid quantity | Request rejected by schema |
| A15 | Unknown approval | Approval route returns not found |
| A16 | Inactive requester | Cannot create a requisition |
| A17 | Unassigned employee | Cannot approve another manager's request |
| A18 | Concurrent budget demand | Competing requests return 201 and budget 409, without overcommit; test artifacts cleaned up |
| A19 | Controlled failure at PR insertion (`PR-10`) | Transaction rolls back, then same idempotency key can safely succeed |
| A20 | Controlled failure at approval insertion (`APR-40`) | No partial PR/approval or leaked commitment; retry succeeds safely |

**Observed recovery output:** Two intentionally injected `RuntimeError` messages (`CONTROLLED_TEST_FAILURE_PR` and `CONTROLLED_TEST_FAILURE_APR`) were expected; both tests passed. The entire suite subsequently reported **20 passed** after the development API was started on port 8000 and the test API on port 8001.

## Manual scenarios previously observed

| ID | Scenario | Recorded outcome / historical evidence |
|---|---|---|
| T01 | Search helmets | Three active helmet materials returned in chat/Streamlit |
| T02 | Contracted offers for `MAT-1001` | `OFF-1002` at $23.50 / seven days and `OFF-1001` at $25 / five days returned as eligible; excluded stale/inactive offers |
| T03 | Read-only procurement validation | Budget/policy response; no PR created |
| T04 | Streamlit material, offer, quantity selection | Stage 2 selection and validation displayed |
| T05 | Quantity changed after validation | Earlier validation cleared before recalculation |
| T06 | Below-threshold purchase | Historical `PR-6640A9F2853A4195` approved for $235 |
| T07 | Reuse idempotency key | Existing PR returned with `duplicate_request: true` |
| T08 | Above-threshold purchase | Historical `PR-53B9F17991AD4AF7` pending approval for $940 |
| T09 | Manager approval replay | Historical `APR-FB06C645B9834FC5`; repeated action reported `already_decided: true` |
| T10 | Manager rejection | Historical `PR-5F93C7DB28674F17` / `APR-9BEBFADA79354842`; 94,000 cents released |
| T11 | CLI cancellation | User answered No; no submission |
| T12 | CLI confirmation | Historical `PR-9A87C92ACAF1480B`, approved for 10 units / $235 |

Historical identifiers above are documentation examples. Do not use them as cleanup targets or assume they exist in the current test database.

## How to reproduce the current suite

From the `ProcureAI` folder in Windows PowerShell, start **two separate server terminals**:

**Terminal 1 — development API (read-only catalog test suite):**

```powershell
$env:PROCUREAI_ENV = "development"
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

**Terminal 2 — isolated test API (write/transaction tests):**

```powershell
$env:PROCUREAI_ENV = "test"
python -m uvicorn api.main:app --host 127.0.0.1 --port 8001
```

In a **third terminal**, verify both environments before executing tests:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health  # environment: development
Invoke-RestMethod http://127.0.0.1:8001/health  # environment: test
python -m pytest tests/ -v
```

Use `.env.test` only for isolated write tests; do not publish it. Confirm the test database host begins with `procureai-test-`, demo writes are enabled only for the synthetic test environment, and no other test runner or user is modifying its budget during execution. Avoid rerunning a failed write test before verifying retained PR records and budget commitments.

## Concurrency incident and resolution

An earlier two-request run returned **HTTP 201 + HTTP 500** and preserved a $2,514.50 pending requisition, rather than the expected **201 + 409**. Its test record was inspected and cleaned up, reversing the matching $2,514.50 budget commitment. The requisition endpoint was then updated to serialize demo submissions **within a single Python process**, while retaining authoritative conditional database budget updates. A subsequent run returned **201 + budget 409**; the test verified no overcommitment and restored the original test budget.

**Important limitation:** A Python process-local lock does **not** coordinate multiple Uvicorn workers, machines or external writers. The passing test does not establish distributed transaction safety or resilience under arbitrary load.

## Remaining tests and evidence to collect

| Priority | Scenario | Why it remains open |
|---|---|---|
| P0 before external write access | Authenticated users / SSO and record-level RBAC | Current employee/approver identities are demo environment variables, not verified user claims |
| P0 before multi-instance deployment | Multiple workers or application instances competing on budget | Single-process lock cannot coordinate across workers; database contention/retry policy must be assessed |
| P0 | Prompt injection and malicious tool-output attempts | No dedicated adversarial agent evaluation completed |
| P1 | Offer/price/contract changes between validation and confirmation | Backend eligibility is rechecked, but a targeted stale-state automated scenario has not been evidenced |
| P1 | Lost HTTP response after committed submission | Idempotent replay tested; specific network-loss recovery simulation still pending |
| P1 | Full audit completeness and actor attribution | Audit writes exist; exhaustive end-to-end coverage and retention controls not established |
| P1 | Streamlit state recovery across reruns | End-to-end session recovery not systematically tested |
| P1 | Authenticated approval delegation and separation of duties | Demo checks exist but are not production-grade identity/authorization |
| P2 | Larger synthetic catalog and performance / p95 | Defined performance baselines and load testing pending |

## Proposed quality measures

Catalog retrieval precision; tool-call correctness; policy decision accuracy; unauthorized-write attempts blocked; confirmed-write success; duplicate-write rate; outstanding-budget invariant violations; API p95 latency; agent-response latency and token cost; audit event coverage; and successful recovery from transient failures. Set quantitative thresholds before describing these as service-level objectives.

**Portfolio claim:** “Implemented and verified 20 automated checks across procurement API, business rules, governance, authorization, single-process concurrency, and controlled rollback/retry behavior using synthetic test data.” **Do not claim** certified governance, full distributed safety, all AI risks tested, or production readiness.
