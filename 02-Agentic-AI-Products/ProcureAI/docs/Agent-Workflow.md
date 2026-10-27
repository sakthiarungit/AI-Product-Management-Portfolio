# ProcureAI — Agent and Procurement Workflow

## Current agent tools

The Microsoft Agent Framework agent exposes three read-only tools:

1. `search_catalog(query)` — locate active materials by terms/synonyms.
2. `get_supplier_offers(material_id)` — retrieve supplier offers that pass backend eligibility rules.
3. `validate_procurement_request(offer_id, quantity)` — request authoritative budget/policy validation without creating a requisition.

The agent is **not authorized to write directly**. It may explain options and request users to follow the confirmed application flow.

## Workflow stages

| Stage | Employee action | System action | Status |
|---|---|---|---|
| 1. Discover | Describe needed material | Agent searches backend catalog | Working |
| 2. Select material | Choose a specific active material | Streamlit stores selected material ID | Working (workspace controls) |
| 3. Compare offers | Review supplier, price and lead time | Backend checks supplier/contract eligibility | Working |
| 4. Select offer/quantity | Choose supplier offer and quantity | Streamlit saves structured selections | Working |
| 5. Validate | Request budget/policy check | Backend supplies authoritative outcome | Working |
| 6. Confirm purchase | Explicitly confirm displayed transaction | CLI controller revalidates, then calls write API | Working in CLI only |
| 7. Record requisition | — | Backend transaction commits budget and writes PR/audit, maybe creates approval | Working in API |
| 8. Approve/reject | Assigned manager decides | Backend updates approval and PR; rejection releases commitment | Working in API |
| 9. Unified chat journey | Make selections/confirm in conversational cards | Structured chat orchestration | Planned |

## Procurement policy behavior

- Active, eligible materials and offers are required.
- Server obtains offer price and requester/cost-center context from trusted records, not model-generated values.
- A request exceeding the demonstration's $500 approval threshold routes to a manager if an eligible approver is available.
- Budget validation is non-reserving; the write operation rechecks and conditionally commits against the budget.
- Requests carry an idempotency key; repeating the same request with the same key returns the earlier result instead of charging budget twice. Reusing a key for a different payload is rejected.
- The rejection path releases committed budget. The approved path records approval status; downstream purchase-order creation is **not** part of the implemented scope.

## Essential conversation design rule

Conversation history does not establish business authority. Store `material_id`, `offer_id`, `quantity`, latest validation result and requisition/approval identifiers in application-controlled state. Any selection change invalidates validation. Show employee a server-derived final summary and require a deliberate confirmation. Repeat authoritative checks at submission to prevent stale approvals or price/budget drift.

## Example (synthetic)

> Employee: I need 10 industrial safety helmets.  
> ProcureAI: I found MAT-1001 and available eligible offers.  
> Employee: Compare suppliers.  
> ProcureAI: IndustrialSource OFF-1002, $23.50 / unit, seven-day lead time; SafeGuard OFF-1001, $25.00 / unit, five days.  
> Employee: Select IndustrialSource.  
> ProcureAI: Ten units would total $235.00. I will validate the budget and policy.  
> Employee: Confirm.  
> ProcureAI: *Only the controlled submission workflow creates the PR; model speech alone is never an approval.*

This is the **target chat experience**. The working Stage 2 Streamlit UI makes selections in a separate structured workspace.
