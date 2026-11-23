# PropertyOpsAI

PropertyOpsAI is a standalone agentic AI prototype for residential maintenance. It helps tenants report issues with text and photos, helps property managers coordinate repairs, and tracks each request through tenant-verified resolution.

**Current status.** The Intake & Triage Agent has been tested manually in the Microsoft Foundry playground. The next milestone is to call the saved agent from Postman and validate its response. The web application, dispatch, resolution, and additional intake channels are planned.

## Problem

When tenants report maintenance issues by phone, they may have to wait for the assigned property manager to answer. The manager then gathers the issue details, identifies the unit, decides who should handle the work, and coordinates the repair. Tenants may also need to call back for updates.

PropertyOpsAI explores how AI can reduce those manual handoffs, give tenants visibility into their requests, and help property managers focus on exceptions.

## Product vision

Give tenants a way to report maintenance issues at any time and follow each request through resolution. Use AI to clarify incomplete reports and adapt when vendor offers expire or a repair fails. Before confirming an external booking, require the tenant to approve the specific vendor and visit window.

## Planned MVP workflow

1. **Identify the unit.** The application loads the units linked to the signed-in tenant. It preselects a single authorized unit or asks the tenant to choose among multiple units. The backend verifies unit access on submission.
2. **Capture the issue.** The tenant submits a description and an optional photo. The application creates a request reference and notifies the assigned property manager. The public demo simulates notifications.
3. **Triage the request.** The Intake & Triage Agent reviews the report and any photo, then recommends a maintenance trade and a next step. It asks one focused question when the answer could change the recommendation. The backend applies triage rules and routes uncertain cases to the manager for review.
4. **Handle requests that need no repair.** If the tenant confirms a one-time spill and no remaining issue, the agent can recommend `no_maintenance_needed`. The application skips vendor matching and asks the tenant to confirm closure.
5. **Route the work.** The Dispatch Coordination Agent checks whether the internal maintenance team can help. If external help is needed, it uses a tool to find approved, active vendors who match the trade and cover the property's service area.
6. **Propose and confirm a booking.** Eligible vendors can offer a visit window. If an offer expires, the agent looks for another option or escalates to the manager. The tenant approves the specific vendor and visit window. The backend validates the approval, confirms one assignment, and withdraws outstanding invitations.
7. **Verify the repair.** The vendor or internal team records completion. The tenant confirms the fix or reports that the issue persists. If the issue persists, the application reopens the original request and the Resolution Agent summarizes the repair history for the manager.
8. **Close and collect feedback.** The application closes the request after tenant confirmation. When an external vendor completed the repair, the tenant can leave an optional rating.

## Agents and models

| Agent | Planned model | Responsibility |
| --- | --- | --- |
| Intake & Triage | Vision-capable model | Interpret tenant text and photos, ask a focused follow-up question, and recommend a trade and next step. |
| Dispatch Coordination | Text model with tool calling | Check internal availability, find eligible vendors, and respond to expired offers or stalled outreach. |
| Resolution | Same text model as Dispatch, with its own tools | Use the original report, repair notes, and tenant feedback to prepare a manager handoff when an issue persists. |

The planned prototype uses three agents and two model roles. The application saves structured results and case events so work can resume when a tenant replies, a vendor responds, or an offer expires.

## Triage output and application behavior

The Triage Agent returns four fields:

| Field | Purpose |
| --- | --- |
| `suggested_trade` | Proposed maintenance trade. It can be provisional while the agent waits for clarification. |
| `evidence` | Details from the tenant's report, photo, or follow-up that support the recommendation. |
| `recommended_next_step` | Recommendation the backend evaluates to determine how the case should proceed. |
| `follow_up_question` | A focused question for the tenant, or `null` when none is needed. |

| Recommended next step | Planned application behavior |
| --- | --- |
| `ready_for_policy_check` | Apply triage rules before advancing to dispatch. |
| `ask_tenant` | Present the question and attach the tenant's reply to the same request. |
| `manager_review` | Route the request and its evidence to the assigned property manager. |
| `no_maintenance_needed` | Skip vendor matching and ask the tenant to confirm closure. |

## Planned architecture

- **Next.js** provides the tenant, property manager, and vendor demo views. The application backend runs in Next.js server routes. The initial `POST /api/maintenance-requests` route receives the web form submission, verifies unit access, creates the request, calls the Triage Agent, and validates its response before updating the case.
- **Supabase Postgres and Storage** hold fictional units, maintenance requests, private attachments, vendor offers, approvals, and case events in a dedicated prototype project.
- **Microsoft Foundry** provides the agent and model environment. The initial triage experiments used `model-router` in the Foundry playground.

The backend enforces authorization, approval, and workflow rules. A shared request timeline records triage decisions, offers, approvals, and changes in status. The public demo will use fictional records, isolated visitor sessions, and simulated vendor notifications.

A future Sethu Properties integration could reuse the workflow with Sethu's sign-in, managed-unit records, and live notification channels.

## Multichannel maintenance intake

The web form will be the first intake channel. WhatsApp, phone, and an in-app virtual assistant are planned to use the same intake workflow. Each channel supplies the issue description and available evidence. The application verifies the requester and unit and keeps the case ID, attachments, status, and follow-up history together.

For example, a tenant could send a photo of a puddle beside the kitchen sink through WhatsApp. The Triage Agent could ask whether the puddle returns when the tap runs. The tenant could then sign in to the web portal and answer that question on the same case.

Later, sensor alerts could provide the device and location as another source of evidence. Personal assistant integrations such as Alexa and Siri are candidates for future exploration.

## What the triage tests showed

The initial Foundry playground tests covered a clear sink leak, an ambiguous report, a tenant clarification that supported plumbing, and a case that needed manager review. In the photo test, the agent recognized a puddle near the sink and asked a question before advancing.

In the spill scenario, the tenant clarified that the water came from a dropped jug and there was no leak. The agent understood the explanation but still recommended `general_maintenance`. Adding `no_maintenance_needed` gave the agent a way to recommend stopping the workflow. The same scenario passed on retest, with no trade or follow-up question.

**Clear sink-leak regression passed.** In the Foundry playground, the revised instructions returned `plumbing` and `ready_for_policy_check`, with `follow_up_question` set to `null`. The agent cited the tenant's report that water pools under the sink when the tap runs.

Application integration testing is pending. The spill integration test will verify that the application creates zero vendor invitations or assignments and closes the request only after the tenant confirms.

## Evaluation and learning goals

| Area | What to evaluate |
| --- | --- |
| Product strategy | Validate where managers spend time today and which handoffs the prototype can reduce. |
| Multimodal triage | Compare text-only and photo-assisted results. Check that the agent cites supplied evidence and preserves uncertainty when a photo does not establish the cause. |
| Multi-agent coordination | Compare a single-agent baseline with the three-agent workflow on the same scenarios. Test tool calls, handoffs, expired offers, and reopened requests. |
| Human approval and authorization | Verify unit access, approval of the specific vendor and visit window, and a maximum of one confirmed assignment per request. |
| Evaluation and monitoring | Track routing accuracy, appropriate escalations, recovery outcomes, latency, and model usage. |

A future live pilot would measure time to confirmed assignment, active property manager minutes per request, and the share of completed repairs that tenants verify as resolved.

## Implementation roadmap

1. **Validate the Foundry API call.** Send the known kitchen-leak scenario from Postman. Verify all four triage fields. For the clear leak, expect `plumbing`, `ready_for_policy_check`, and a `null` follow-up question.
2. **Build the first web demo.** Submit a text description through the Next.js form and display the validated triage result. Then add optional photos and support follow-up replies on the same request.
3. **Demonstrate dispatch and resolution.** Simulate vendor offers, capture tenant approval of the specific vendor and visit window, and verify closure or reopening based on the tenant's response.
4. **Add WhatsApp.** Reuse the shared intake workflow. Demonstrate a request started in WhatsApp and continued in the web portal.
5. **Expand intake options.** Add phone and an in-app virtual assistant. Explore sensor alerts and personal assistants later.