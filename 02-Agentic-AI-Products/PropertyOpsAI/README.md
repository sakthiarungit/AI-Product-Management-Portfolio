# PropertyOpsAI

PropertyOpsAI is a standalone agentic AI prototype for residential
maintenance. It helps tenants report issues using text and photos,
helps property managers coordinate repairs, and tracks each request
through tenant-verified resolution.

**Current status:** Intake & Triage Agent tested manually in Microsoft
Foundry. Application integration, dispatch, and resolution are planned.

## Problem

When tenants report maintenance issues by phone, they may have to wait
for the assigned property manager to answer. The manager then gathers
the issue details, identifies the unit, decides who should handle the
work, and coordinates the repair.

PropertyOpsAI explores how AI can reduce those manual handoffs while
giving tenants visibility into their requests and keeping property
managers in control of exceptions.

## Vision

Give tenants a way to report maintenance issues at any time and follow
them through resolution. Use AI to clarify reports and adapt when plans
change. Require the tenant to approve the specific external vendor and
visit window before the application confirms a booking.

## Planned MVP workflow

1. **Identify the unit.** The application loads the units linked to the
   tenant. It preselects a single authorized unit or asks the tenant to
   choose among multiple units. The backend verifies unit access on
   submission.
2. **Capture the issue.** The tenant submits a description and an
   optional photo. The application creates a request reference and
   notifies the assigned property manager.
3. **Triage the request.** The Intake & Triage Agent uses the report
   and photo to recommend a maintenance trade. It asks one focused
   question when more information could change the recommendation.
   The backend applies triage rules, and uncertain cases go to the
   manager for review.
4. **Handle requests that need no repair.** If the tenant confirms a
   one-time spill and no remaining issue, the agent recommends
   `no_maintenance_needed`. The application skips vendor matching
   and asks the tenant to confirm closure.
5. **Route the work.** The Dispatch Coordination Agent checks whether
   the internal maintenance team can help. If external help is needed,
   it uses a tool to find approved, active vendors who match the trade
   and cover the property's service area.
6. **Propose and confirm a booking.** Eligible vendors can offer a
   visit window. If an offer expires, the agent looks for another
   option or escalates to the manager. The tenant approves the exact
   vendor and visit window. The backend confirms one assignment and
   withdraws the remaining invitations.
7. **Verify the repair.** The vendor or internal team records completion.
   The tenant confirms the fix or reports that the issue persists.
   If it persists, the application reopens the original request and
   the Resolution Agent summarizes the repair history for the manager.
8. **Close and collect feedback.** The application closes the repair
   request after tenant confirmation and offers an optional vendor rating.

## Agents and models

| Agent | Planned model | Responsibility |
| --- | --- | --- |
| Intake & Triage | Vision-capable model | Interpret tenant text and photos, ask for clarification, and recommend the next triage step. |
| Dispatch Coordination | Separate text model with tool calling | Check internal availability, find eligible vendors, and respond to expired offers or stalled outreach. |
| Resolution | Same text model as Dispatch, with a different set of tools | Use the original report, repair notes, and tenant feedback to prepare a manager handoff when an issue persists. |

The planned prototype uses three agents and two models. Intake accepts
both text and images. The workflow saves structured results so it can
resume when a tenant replies, a vendor responds, or an offer expires.

## Triage output and application behavior

The triage response includes `suggested_trade`, `evidence`,
`recommended_next_step`, and `follow_up_question`. The backend uses
`recommended_next_step` to decide which path to take. A suggested trade
can be provisional while the agent is waiting for clarification.

| Recommended next step | Planned application behavior |
| --- | --- |
| `ready_for_policy_check` | Apply triage rules before advancing to dispatch. |
| `ask_tenant` | Show the question and wait for a reply on the same request. |
| `manager_review` | Route the request and its evidence to the assigned manager. |
| `no_maintenance_needed` | Skip vendor matching and ask the tenant to confirm closure. |

## Planned architecture

- **Next.js** provides tenant, property manager, and vendor demo views
  with a shared request timeline.
- **Python and FastAPI** expose application APIs, validate agent outputs,
  execute tools, and enforce authorization, approval, and workflow rules.
- **Supabase Postgres and Storage** hold fictional units, maintenance
  requests, private attachments, vendor offers, approvals, and events
  in a dedicated prototype project.
- **Microsoft Foundry** provides the agent and model environment. The
  initial triage experiments used the Foundry playground with
  `model-router`.

The public demo will use fictional records, isolated visitor sessions,
and simulated vendor notifications. A future Sethu Properties
integration can reuse the workflow while connecting Sethu's sign-in,
managed-unit records, and live notification channels.

## What the triage tests showed

The initial Foundry tests covered a clear sink leak, an ambiguous report,
a tenant clarification that supported plumbing, and a case that needed
manager review. The photo test showed that the agent could recognize a
puddle near the sink and ask a question before advancing.

In the spill scenario, the tenant clarified that the water came from
a dropped jug and there was no leak. The agent understood that evidence
but still recommended `general_maintenance`. Adding
`no_maintenance_needed` gave it a way to recommend stopping the workflow.
The same scenario passed on retest with no trade or follow-up question.

The clear sink-leak regression test with the revised instructions is
pending. FastAPI integration testing is also pending, including verifying
that the spill path creates no vendor invitation or assignment and
closes only after the tenant confirms.

## Evaluation and learning goals

- **Product strategy** — Validate the maintenance bottleneck, scope
  the MVP, and define measurable user outcomes.
- **Multimodal AI** — Compare text-only and photo-assisted triage and
  check that recommendations cite evidence supplied by the tenant.
- **Multi-agent coordination** — Test tool calls, handoffs, offer expiry,
  and reopening. Compare a single-agent baseline with the multi-agent
  design on the same scenarios.
- **Human approvals and authorization** — Verify unit access, approval
  of the specific vendor offer, and one confirmed assignment per request.
- **Evaluation and monitoring** — Track routing accuracy, appropriate
  escalations, recovery outcomes, latency, and model usage.

A future live pilot would measure time to confirmed assignment, active
manager minutes per request, and the share of completed repairs that
tenants verify as resolved.

## Next milestone

Rerun the clear sink-leak case with the revised instructions. Then
connect the triage agent to FastAPI, validate its structured response,
and test that a confirmed spill skips dispatch and waits for the
tenant's closure confirmation.