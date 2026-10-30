# ProcureAI — Governed Agentic AI for Enterprise Procurement

**Principal AI Product Manager portfolio case study | V1 local proof of concept | October 2026**

> **Project boundary:** ProcureAI uses synthetic materials, suppliers, employees, contracts, budgets, and policies. It is a local portfolio prototype—not a production purchasing platform and not connected to SAP, Ariba, or Maximo. Product value hypotheses are not yet validated with real users or a conventional-workflow baseline.

## 1. Executive summary

ProcureAI explores a practical enterprise Agentic AI question: **Can a natural-language purchasing experience simplify requisition preparation while retaining deterministic financial controls, explicit employee confirmation, and accountable managerial approval?**

I developed a single-agent procurement proof of concept backed by an enterprise-style service layer. In the demonstrated scenario, an employee requested 40 industrial safety helmets, selected material `MAT-1001` and supplier offer `OFF-1002`, received a $940 budget/policy validation, confirmed the requisition, and obtained a separate manager approval. The final database record confirmed **40 units, $940.00, and `APPROVED` status** after the manager action.

The prototype also passed **20 automated backend regression tests** in an isolated test environment and **six focused manual agent behavior checks**. These are prototype verification results, not production reliability statistics or measured business ROI.

**Principal product decision:** Keep AI tool access read-only; let trusted application/backend services own transaction confirmation, procurement rules, budget reservation, approval decisions, and audit records.

## 2. Problem and opportunity

Enterprise employees often need to locate the right catalog material, identify eligible suppliers, compare contracted prices and lead times, check cost-center budgets, understand approval thresholds, and create requisitions. This process may require navigation across multiple systems and knowledge of procurement terminology.

**Opportunity hypothesis:** A governed conversational procurement experience could reduce the effort and ambiguity involved in preparing a valid request without weakening existing controls.

**What is known:** The prototype demonstrates one integrated synthetic workflow. **What is not yet known:** Whether it improves speed, satisfaction, error rates, or cost relative to an existing procurement UI. Those are explicit discovery hypotheses, not observed outcomes.

## 3. Users and jobs to be done

| Persona | Job to be done | V1 relevance |
|---|---|---|
| Employee / requester | Describe needs, find appropriate material, choose supplier, review and confirm requisition | Demonstrated in Streamlit |
| Procurement specialist | Ensure eligible materials, supplier offers and contracted prices are used | Represented through backend catalog/offer checks; no dedicated specialist workspace |
| Purchasing manager / approver | Review a policy-routed purchase and record a decision | Demonstrated via local manager screen |
| Finance / budget owner | Prevent inappropriate or excessive budget commitments | Represented through deterministic backend validation and reservation |
| IT / governance team | Inspect behavior, enforce boundaries, audit outcomes | Supported by backend controls, logs and tests; not a production operations console |

## 4. Discovery hypotheses and proposed value measures

The existing product discovery work frames four hypotheses:

- **H1 — Efficiency:** Reduce elapsed time to prepare a requisition.
- **H2 — Accuracy:** Improve material selection on ambiguous requests.
- **H3 — Compliance:** Prevent unauthorized purchases using deterministic rules and required approvals.
- **H4 — Experience:** Reduce reliance on procurement-specific terminology.

To evaluate these responsibly, compare the prototype with a conventional form-based workflow on the same synthetic scenarios. Measure:

| Metric | Proposed method | Current evidence |
|---|---|---|
| Request completion rate | Valid completed scenarios / attempted valid scenarios | One demonstrated end-to-end purchase; no representative rate |
| Catalog matching accuracy | Correct eligible matches / labeled evaluation requests | Focused manual checks only |
| Requisition preparation time | Median elapsed time, excluding manager wait | Not measured |
| Policy adherence | Prohibited actions blocked / tested prohibited actions | Selected backend negative tests and manual agent probes |
| Transaction correctness | Matching confirmed vs stored material, quantity, price, status | Verified for the 40-unit scenario |
| Model cost and latency | Tokens, spend and end-to-end timing per successful request | Not yet measured systematically |
| User confidence / usability | Task observation and feedback from target personas | Not yet collected |

**Go/no-go criterion for a pilot:** Establish a baseline, formal test set, acceptable risk thresholds, and actual user feedback before claiming business benefit.

## 5. Product scope and prioritization

### Implemented and demonstrated in V1

1. Conversational entry and guided selection of synthetic catalog materials.
2. Eligible contracted supplier-offer retrieval and price/lead-time comparison.
3. Backend budget validation and manager-approval policy checks.
4. Explicit employee confirmation and simulated purchase-requisition creation.
5. Manager approval or rejection flow with backend-controlled state transitions.
6. Idempotency, transactional budget commitment, audit records, and recovery-oriented regression tests.
7. Read-only AI agent tools for catalog search, supplier offers, and procurement validation.

### Important implementation nuance

The **Streamlit purchasing path is hybrid**: known catalog-keyword requests can trigger deterministic search and guided UI controls; other conversational questions can invoke the AI agent with its read-only tools. The successful Streamlit procurement demonstration should **not** be described as proof that an autonomous model executed every screen transition or write action.

### Not demonstrated / beyond V1

- Real SAP/Ariba/Maximo transactions or external purchase orders.
- Production SSO, authenticated manager sessions, and enterprise RBAC.
- Multi-line requisitions, delivery-location extraction, and all acceptance criteria in the original draft PRD.
- Distributed multi-instance write coordination, production monitoring, or broad adversarial evaluation.
- Comparative multi-agent architecture or quantified economic benefit.

These boundaries preserve a small, credible MVP rather than equating an extensive PRD wish list with delivered capability.

## 6. Core user journey — verified example

**Scenario:** A maintenance requester needs **40 industrial safety helmets**.

| Step | User or system activity | Evidence / outcome |
|---|---|---|
| 1 | Requester enters the purchasing need | Streamlit conversation captures request |
| 2 | Requester selects a material | `MAT-1001` — Industrial Safety Helmet, Type I |
| 3 | System retrieves contracted offers | `OFF-1002` IndustrialSource: **$23.50 / unit, 7 days**; `OFF-1001` SafeGuard Supplies: **$25.00 / unit, 5 days** |
| 4 | Requester selects offer and quantity | `OFF-1002`, 40 units |
| 5 | Backend validates financial/policy rules | **$940.00**; policy threshold **greater than $500**; `APPROVAL_REQUIRED` |
| 6 | Requester explicitly confirms | Requisition `PR-338AEFBBB88B46FA` created as `PENDING_APPROVAL` |
| 7 | Manager acts through local demo | Approval `APR-6E193D0B20154B92` assigned to synthetic manager `EMP-1002`; manager approved |
| 8 | Final record is checked | Requisition stored as **40 units, $940.00, `APPROVED`** |

These IDs are synthetic demonstration records. Validation budget values can change as test requisitions are created; do not present a past available-balance figure as a current invariant.

## 7. Solution and architecture decisions

**Logical flow:** Employee → Streamlit guided purchasing / read-only AI interaction → FastAPI domain services → Turso/libSQL synthetic records → policy-controlled requisition/approval state.

**AI layer:** An Azure-hosted GPT-5-mini model orchestrated with Microsoft Agent Framework. The AI-facing tools are `search_catalog`, `get_supplier_offers`, and `validate_procurement_request`. They do not expose requisition submission or manager approval.

**Trusted execution layer:** FastAPI controls request validation, authoritative price/budget/policy checks, transaction creation, idempotency, manager approval, state transitions, and audit events.

**Data model:** Synthetic catalog, supplier/contract offers, employees and cost centers, budgets and policies, requisitions, approvals, and audit logs. Development and isolated test APIs use separate Turso configurations.

### Product trade-offs

| Choice | Reason | Limitation |
|---|---|---|
| Single agent with narrow tools | Lower complexity; clearly bounded authority | Not proof of complex autonomous orchestration |
| Read-only AI tools; separate write controller | Prevents direct model-initiated financial action | Extra UI/controller steps |
| Deterministic policy and budget enforcement | Auditable and repeatable financial decisions | Backend still needs production identity and scale hardening |
| Guided material/offer selection | Clear employee confirmation, fewer assumptions | Less flexible than unrestricted autonomous shopping |
| Synthetic local setup | Safe, reproducible development | No live-enterprise integration or production claims |

## 8. Governance, reliability, and a critical defect discovered

The MVP deliberately distinguishes **user intent**, **explicit transaction confirmation**, and **manager authorization**. The $940 scenario crosses the configured $500 approval threshold, so confirmation creates a pending requisition; only the separate manager decision changes it to approved.

The project surfaced a meaningful UI defect: a review showed **40 units and $940**, while an earlier Streamlit submission sent **1 unit and $23.50**. The backend correctly applied the threshold to the amount it received, but the user's reviewed transaction and submitted transaction did not match. The application was corrected to preserve a reviewed purchase snapshot and verify the resulting transaction. The final scenario then created **40 units in `PENDING_APPROVAL`** and reached `APPROVED` only after the manager action.

**Product lesson:** Backend policy correctness is necessary but not sufficient. The user-facing confirmation must be bound to exactly what is submitted. Otherwise, an apparently compliant system can still execute a different transaction from the one the user intended.

Other controls exercised in development include idempotent requests, transactional updates to prevent budget overcommit, rollback/retry tests, invalid supplier-offer rejection, and policy-bypass resistance. A local single-process submission lock is **not** a substitute for production distributed concurrency control.

## 9. Verification evidence and limitations

- **20/20 automated backend tests passed** in the isolated test environment on the final reported regression run. Categories covered read-only catalog behavior, transaction integrity, negative governance cases, identity restrictions, concurrency, and recovery.
- **6/6 focused manual agent scenarios passed as observed**, including material discovery, supplier comparison, validation, an attempted policy bypass, an invented offer, and an ambiguous request. These are not a statistically representative accuracy benchmark.
- **End-to-end local demo verified**: 40 helmets → $940 validation → pending approval → manager approval → stored `APPROVED` requisition.

**Not yet evidenced:** A repeatable model-evaluation benchmark, production security, a user study, real system integration, workload/latency SLAs, and verified business ROI.

## 10. Roadmap and product decision gates

**V1 — Complete for local PoC:** Guided procurement, narrow read-only agent tools, deterministic validation, confirmed simulated write, manager decision, audit and backend regression evidence.

**Next — Evaluation and portfolio packaging:** Repeatable agent evaluation dataset and run logs, README/setup/dependency cleanup, screenshots, and measured usability/task timing if feasible.

**Potential pilot — Only after evidence:** Real identity and authorization, enterprise integration contracts, API access controls, distributed reliability, monitoring, formal security/governance review, and a pilot with measurable outcomes.

**Optional exploration — Not a prerequisite to publish:** Multi-agent catalog/sourcing specialists, comparative single- vs multi-agent evaluation, and more complex procurement workflows.

**Product gate:** Do not advance from prototype to pilot merely because the demo works. Require evidence of user value, grounded decisions, enforceable controls, transaction reliability, sustainable cost, and deployment readiness.

## 11. What I learned as a product leader

1. **Autonomy should follow verified authority.** Agent intelligence cannot replace trusted enterprise permissions and financial controls.
2. **Integration readiness shapes AI value.** An agent can reason well and still fail without reliable material, supplier, contract, and budget information.
3. **Confirmation is a product contract.** The submitted request must match the user's reviewed details, not merely pass a backend threshold.
4. **Reliability is part of the product promise.** Concurrency, idempotency, recovery, and accurate status are user outcomes, not just backend implementation details.
5. **Claims need evidence.** Passing tests and a successful demonstration support prototype readiness; they do not establish production readiness or measurable economic benefit.

## 12. Related project artifacts

- [Product Vision](Product-Vision.md)
- [Product Discovery](Product-Discovery.md)
- [Product Requirements Document](PRD.md) — **initial draft**; includes requirements not implemented in V1
- [ProcureAI README](../README.md)
- [Setup and Demonstration Guide](../SETUP.md)
- [Architecture](../docs/Architecture.md)
- [AI Governance](../docs/AI-Governance.md)
- [Test Scenarios](../docs/Test-Scenarios.md)
- [Development Log](../docs/Development-Log.md)

**Portfolio positioning:** ProcureAI is a governed enterprise Agentic AI **proof of concept**, intended to demonstrate product judgment and applied architecture through real prototype evidence—not to claim autonomous procurement operations at production scale.
