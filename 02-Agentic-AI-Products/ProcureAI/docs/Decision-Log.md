# ProcureAI — Architecture and Product Decision Record

Decisions recorded retrospectively from the working prototype. Dates are approximate rather than claiming contemporaneous approval records.

## ADR-001 — Build with synthetic procurement data

- **Decision:** Use a small six-material sandbox with suppliers, contracts, budgets and employees.
- **Why:** Tests can be repeatable and safe, without live enterprise data or ERP connections.
- **Trade-off:** Real-world catalog complexity and scale remain unproven.
- **Next:** Add larger synthetic catalog **after** end-to-end journey is complete.

## ADR-002 — Use LLM for language, backend for business authority

- **Decision:** Agent tools search/compare/validate; FastAPI governs writes.
- **Why:** The LLM should not dictate prices, authorizations or transaction success.
- **Trade-off:** More orchestration and state management are required.

## ADR-003 — Prefer explicit human confirmation to autonomous purchasing

- **Decision:** CLI controller requires `YES` before requisition creation; chat must eventually have an equivalent confirmed review card.
- **Why:** Purchase commitment is a consequential action; users must see authoritative context.
- **Trade-off:** One more step in workflow.

## ADR-004 — Enforce budget and idempotency in a transaction

- **Decision:** Revalidation, budget commitment, requisition/audit creation and approval routing use an atomic transaction. Repeated keys are compared to their original request fingerprint.
- **Why:** Avoid duplicate PRs and overspending after transient retries.
- **Trade-off:** Need transaction contention and recovery tests.

## ADR-005 — Streamlit for local UI prototyping

- **Decision:** Use Streamlit to integrate UI quickly with Python agent and existing APIs.
- **Why:** Accelerate learning and portfolio demonstration.
- **Trade-off:** Rerun/state/async lifecycle can complicate long-lived agent sessions.

## ADR-006 — Conversation-first final interaction

- **Decision:** Replace separate procurement form as the **primary** journey with chat-embedded material, offer, validation and confirmation cards.
- **Why:** Matches the product's agentic experience and simplifies requester interaction.
- **Trade-off:** Needs application-controlled structured state and more involved UI design.
- **Status:** Planned; Stage 2 workspace remains current implementation.

## ADR-007 — Single agent rather than premature multi-agent system

- **Decision:** Current MVP uses one procurement agent and deterministic services.
- **Why:** The use case is tractable and does not justify additional agent coordination overhead yet.
- **Review trigger:** Add clearly separable responsibilities, measurable benefits, or independent ownership boundaries.
