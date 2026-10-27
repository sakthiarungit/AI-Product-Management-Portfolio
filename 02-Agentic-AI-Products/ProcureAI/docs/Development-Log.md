# ProcureAI — Development Log

## Completed milestones (through October 26, 2026)

| Milestone | What was accomplished | Evidence |
|---|---|---|
| M1 — Product framing | Product vision, discovery and PRD initiated in `product/` | Existing local documents (review before asserting their completeness) |
| M2 — Core technology | Azure-hosted GPT-5-mini, Microsoft Agent Framework, FastAPI and Turso connected | Working natural-language tool calls and backend responses |
| M3 — Synthetic data model | 11 tables created; six materials, suppliers, contracts, employees, budgets and policy seeded | Schema/seed scripts and database checks |
| M4 — Read tools | Material search, eligible offers and budget/policy validation endpoints integrated with agent | CLI and API tests |
| M5 — Governed write API | PR creation, idempotency, committed budget, audit log and above-threshold manager routing | Verified PR identifiers; retry tests |
| M6 — Manager decisions | Approval/rejection API, replay handling and committed-budget release on rejection | Verified approval and rejection identifiers |
| M7 — CLI controller | Explicit `YES` review/confirmation, fresh idempotency key, no submit on cancellation | User verified cancelled and approved examples |
| M8 — Streamlit Stage 1 | Natural-language chat connected to agent | User confirmed material/supplier queries worked; intermittent error observed |
| M9 — Streamlit Stage 2 | Separate purchasing workspace with dropdowns, quantity, validation and invalidation upon changes | User confirmed all steps worked |

## Decisions and lessons

1. Trusted enterprise data and eligibility should be verified in services, not inferred from AI-generated statements.
2. **Read-only agent tools** are a useful boundary while the application develops its authorization model.
3. High-impact actions require deliberate user confirmation and auditable state transitions.
4. Chat history is not enough to carry financial workflow state; deterministic state must hold current IDs and validation freshness.
5. Fast iteration is valuable, but security and testing gaps must be disclosed clearly in the portfolio.

## Next implementation milestones

- **M10:** Finish source review and check in documentation with reproducible setup and architecture diagrams.
- **M11:** Conversation-first chat cards for material, supplier and quantity selection.
- **M12:** Controlled in-chat review/confirmation, idempotent PR submission, approval status display.
- **M13:** Repeatable automated tests, failure recovery, safe-demo access restrictions.
- **M14:** Portfolio demo walkthrough, screenshots/recording and LinkedIn article.

## Maintenance rule

After each milestone update this log, any affected architecture/workflow/governance/test docs, README status, and the corresponding commit. Do not mark a feature as implemented until demonstrated by an actual local test or a reproducible automated assertion.
