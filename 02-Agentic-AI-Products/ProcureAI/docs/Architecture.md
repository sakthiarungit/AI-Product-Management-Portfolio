# ProcureAI — Solution Architecture

**Status:** As-built local prototype, documented October 2026. Features marked *planned* are not implemented.

## Design objective

Demonstrate a procurement assistant that separates natural-language understanding from trusted business execution. The model can invoke approved read-only tools. A controlled application or API path performs writes after explicit user confirmation and authoritative server validation.

## Component responsibilities

| Layer | Implemented technology | Responsibility |
|---|---|---|
| User interaction | Streamlit (`app.py`); Python CLI | Chat plus Stage 2 structured material/supplier/quantity/validation UI; CLI purchase confirmation |
| Agent reasoning | Microsoft Agent Framework; Azure-hosted GPT-5-mini | Interpret procurement questions, decide which read-only tool to call, return explanation |
| Agent tools | `search_catalog`, `get_supplier_offers`, `validate_procurement_request` | Call FastAPI; no direct DB mutation |
| Business/API layer | FastAPI (`api/main.py`, `api/requisitions.py`, `api/approvals.py`) | Catalog queries, eligibility filtering, budget/policy rules, transactions, approval lifecycle |
| Data layer | Turso/libSQL | Material, supplier, contract, budget, policy, request, approval and audit records |
| Authentication in demo | Azure CLI credential for model; environment-based demo identities for write APIs | **Developer-only mechanism, not production end-user identity enforcement** |

## Current flow

```mermaid
sequenceDiagram
  participant U as User
  participant UI as Streamlit / CLI
  participant A as AI Agent
  participant API as FastAPI
  participant DB as Turso
  U->>UI: Search for helmets
  UI->>A: Natural-language request
  A->>API: GET /api/v1/materials?search=helmet
  API->>DB: Read active catalog
  DB-->>API: Materials
  API-->>A: Material records
  A-->>UI: Material options
  U->>UI: Choose material and offer in workspace
  UI->>API: GET eligible supplier offers
  API->>DB: Check active suppliers/contracts
  API-->>UI: Verified offers
  U->>UI: Select quantity; validate
  UI->>API: POST /api/v1/procurement/validate
  API->>DB: Read budget and policy
  API-->>UI: Validation result (no write)
  Note over UI,DB: Current Streamlit flow stops after validation
```

## Transaction path — currently available through CLI or API

```mermaid
sequenceDiagram
  participant U as Employee (CLI / API demo)
  participant C as Confirmation controller
  participant API as FastAPI
  participant DB as Turso
  U->>C: Offer and quantity
  C->>API: Validate selection
  API-->>C: Verified price / budget / policy
  C->>U: Display transaction review
  U->>C: Explicit confirmation
  C->>API: POST /api/v1/requisitions + idempotency key
  API->>DB: BEGIN IMMEDIATE; recheck; reserve budget; insert PR and audit
  DB-->>API: Committed transaction
  API-->>C: Requisition status / identifier
  C-->>U: Result
```

## Core tables

`materials`, `suppliers`, `contracts`, `supplier_catalog`, `cost_centers`, `employees`, `budgets`, `procurement_policies`, `purchase_requisitions`, `approval_requests`, `audit_logs`.

Relationships: supplier catalog offers associate materials, suppliers and contracts. Requisitions reference requester, cost center, budget, offer and policy; approvals reference requisitions; audit logs capture actions and state transitions. See existing `database/create_tables.py` for exact schema; this document is not a substitute for executable DDL.

## API inventory

| Method and route | Purpose | Mutates data? |
|---|---|---|
| `GET /health` | Health endpoint | No |
| `GET /api/v1/materials?search=...` | Material discovery | No |
| `GET /api/v1/materials/{material_id}/supplier-offers` | Eligible supplier offers | No |
| `POST /api/v1/procurement/validate` | Budget/policy precheck | No |
| `POST /api/v1/requisitions` | Create requisition | **Yes** |
| `POST /api/v1/approvals/{approval_id}/approve` | Manager approves | **Yes** |
| `POST /api/v1/approvals/{approval_id}/reject` | Manager rejects and releases commitment | **Yes** |

## Nonfunctional requirements / known gaps

- Backend transactions and idempotency have passed basic manual tests; concurrency, rollback, and audit completeness require systematic tests.
- An approval threshold of $500 is configured in synthetic policy seed data.
- Currency is represented using integer cents in request/budget transaction paths; a supplier unit-price `REAL` column remains a known modeling limitation for strict financial systems.
- Authentication uses development identity environment variables rather than verified session claims; keep write endpoints private until real authentication/authorization is implemented.
- No demonstrated production monitoring, deployment, rate limits, or enterprise integration.

## Planned architecture evolution

Conversation-first Streamlit cards with a deterministic purchase state machine; chat intents converted into **proposals**, with selected IDs resolved from trusted API records, and mandatory fresh pre-submit validation. Optional later enhancements include real SSO/RBAC, tracing/evaluations, MCP connectors, multi-line PRs and ERP integrations. No multi-agent architecture is necessary for the present MVP.
