# ProcureAI — Test Scenarios and Evidence

## Evidence legend

- **Observed:** User confirmed result during manual local tests.
- **Pending:** Add a repeatable automated test and capture logs/HTTP assertions.
- Test records below are synthetic. Historic state of the shared development budget changes after submissions; reset only in a disposable database.

## Observed manual tests

| ID | Test | Observed outcome | Evidence / identifier |
|---|---|---|---|
| T01 | Material search for helmets | Three active helmet materials returned | Streamlit/chat test |
| T02 | Contracted supplier comparison for MAT-1001 | OFF-1002 ($23.50, 7 days) and OFF-1001 ($25.00, 5 days) eligible; expired/inactive excluded | API/agent test |
| T03 | Backend read-only validation | Budget and policy results returned, no PR created | API and Stage 2 UI |
| T04 | Stage 2 Streamlit form selections | Material, offer, quantity and validation display correctly | User confirmed all Stage 2 checks passed |
| T05 | Update quantity after validation | Previous validation disappears; new total can be validated | User confirmed Stage 2 tests passed |
| T06 | Create below-threshold PR | `PR-6640A9F2853A4195` APPROVED at $235 | Backend test |
| T07 | Retry same PR idempotency key | Original PR returned with `duplicate_request: true` | Backend test |
| T08 | Above-threshold requisition | `PR-53B9F17991AD4AF7` PENDING_APPROVAL at $940 | Backend test |
| T09 | Manager approves and retries | `APR-FB06C645B9834FC5` APPROVED; duplicate decision returned `already_decided: true` | Approval API test |
| T10 | Manager rejects | `PR-5F93C7DB28674F17` / `APR-9BEBFADA79354842` REJECTED; 94,000 cents released | Approval API test |
| T11 | CLI pre-submit cancellation | User answered No; no backend submission | Controller test |
| T12 | CLI confirmed submission | `PR-9A87C92ACAF1480B` APPROVED, qty 10 / $235 | User verified in Turso |

## Automated tests still required

| Priority | Scenario | Expected behavior |
|---|---|---|
| P0 | Invalid/nonexistent offer | Rejected; no budget or PR changes |
| P0 | Inactive supplier, expired contract, inactive material | Ineligible offer never purchasable |
| P0 | Insufficient budget | No write and authoritative rejection |
| P0 | Concurrent submissions to same budget | No over-commit, consistent results |
| P0 | Idempotency key reused for changed payload | HTTP 409; no new charge |
| P0 | Crash/exception inside transaction | No partial PR, approval or budget change |
| P0 | Wrong/unavailable manager or inactive requester | Rejected with no unauthorized state transition |
| P0 | Approval/rejection replay | State not changed twice |
| P0 | Prompt injection attempts | Cannot activate write tool or override policy |
| P1 | Stale offer/price between validate and confirm | Backend rechecks and prevents stale purchase |
| P1 | Streamlit agent session across reruns | History stable or safely recovered |
| P1 | Lost response after committed submission | Retry with same key recovers original result |
| P1 | Full audit coverage and actor attribution | All transitions traceable |
| P2 | Larger synthetic catalog (200–500 records) | Search quality and latency stay within defined goals |

## Suggested quality measures (targets not yet set)

Material retrieval precision, tool-call validity, validation accuracy, policy violation rate, confirmed-write success, duplicate write rate, API p95 latency, agent response time, token cost per completed request, and audit completeness.

**Do not publish '100% tested' or 'production-safe' based on the manual evidence above.**
