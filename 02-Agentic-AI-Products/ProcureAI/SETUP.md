# ProcureAI V1 — Local Setup, Demonstration, and Test Guide

> **Scope:** A local, synthetic-data Agentic AI procurement proof of concept. This is **not** a production purchasing service, an authenticated employee/manager portal, or a live SAP/Ariba/Maximo integration. Use only local loopback addresses. The application can write to its configured Turso database.

## 1. Prerequisites

- Windows PowerShell and Python with the project's `.venv` configured.
- A configured Turso **development** database and a **separate** synthetic-data test database.
- Existing `ProcureAI/.env` and `ProcureAI/.env.test` with the appropriate database URL/token and local demo identities. These files are ignored by Git and **must never be committed**.
- Microsoft Azure model credentials/configuration if testing conversational agent responses. Follow the project's existing agent configuration; the guided catalog and requisition workflow does not require a model call for every step.
- Installed project dependencies, including the components required for FastAPI, Streamlit, the Agent Framework, and pytest.

**Dependency note:** The current `requirements.txt` contains FastAPI, libSQL, python-dotenv, and Uvicorn, but does **not** list `streamlit`, `pytest`, or the Microsoft Agent Framework dependencies. Treat it as incomplete for a fresh installation until the dependency manifest is reconciled against the working virtual environment. Do not assume `pip install -r requirements.txt` alone is sufficient.

From the repository's **ProcureAI directory**:

```powershell
.\.venv\Scripts\Activate.ps1
```

If the virtual environment is already activated, leave it as is.

## 2. Start the development backend (Terminal 1)

```powershell
$env:PROCUREAI_ENV = "development"
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Leave the terminal running. In a separate PowerShell terminal, verify:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expect `status: ok` and `environment: development`. The API documentation is at `http://127.0.0.1:8000/docs`.

If port 8000 is already in use, **check `/health` first**. Do not start a second instance or kill an unidentified process. If the endpoint reports `test` or an unknown response, stop and investigate before writing data.

## 3. Start the Streamlit requester and manager demonstration (Terminal 2)

Open another PowerShell terminal in the same directory and activate `.venv` if necessary:

```powershell
$env:PROCUREAI_ENV = "development"
$env:CATALOG_API_BASE_URL = "http://127.0.0.1:8000"
python -m streamlit run app.py
```

Open `http://localhost:8501` in the browser. The sidebar should identify **ProcureAI V1 · Local PoC**.

To allow **synthetic local requisition/approval writes**, both the development backend and Streamlit process must have `ENABLE_DEMO_WRITES=true` in their respective loaded environment. Confirm the backend's `.env` and current process settings, restart the affected process if configuration changed, and never expose write-enabled demo services publicly. The sample flow below **changes your development database budget and requisition records**.

## 4. Walk through the product (development database only)

1. In **Requester chat**, start a new conversation and enter: `I need 40 industrial safety helmets.`
2. Select material **MAT-1001 — Industrial Safety Helmet, Type I**.
3. Compare contracted offers; select **IndustrialSource / OFF-1002**, at **$23.50 per unit**, with a **7-day** lead time.
4. Check that the selected **quantity is 40**; click **Check budget and policy**.
5. Review the backend result: expected purchase amount **$940.00**, with manager approval required by the synthetic policy for purchases **over $500**. The available budget is dynamic and must be sufficient; do not assume a fixed balance.
6. Only if the reviewed offer, quantity, amount, and approval requirement match, select **Confirm requisition** **once**. An expected successful response is **40 units / 94,000 cents / PENDING_APPROVAL**. Do not retry with a new request after a timeout or uncertain outcome; inspect the backend record first.
7. Locate the corresponding `APR-...` approval request in the development Turso `approval_requests` table (the requisition creation response does not necessarily return an approval ID). The approval links to its requisition by `requisition_id`.
8. Switch to **Manager demo**, enter the matching approval ID, select **Approve** or **Reject**, add a comment, check the explicit confirmation box, and submit **once**. The backend must validate the configured demo manager and pending status.
9. Verify the final requisition and approval status in Turso. For an approval, the requisition should become `APPROVED`; for rejection, it should become `REJECTED` with the budget commitment handled by the backend.

**Previously observed demo evidence (not a guaranteed fresh result):** `PR-338AEFBBB88B46FA` had 40 units totaling $940, transitioned from `PENDING_APPROVAL` to `APPROVED` after the manager approved `APR-6E193D0B20154B92`. Do not reuse these already-decided identifiers for a new manager action.

## 5. Run the isolated backend regression tests (Terminals 3 and 4)

**Never run write tests against the development database.** The isolated test database must be configured in `.env.test`, and its URL must meet the environment selector's test-database naming check.

Terminal 3:

```powershell
$env:PROCUREAI_ENV = "test"
python -m uvicorn api.main:app --host 127.0.0.1 --port 8001
```

In another terminal, verify *before running tests*:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/health
```

Proceed **only** when the response identifies `environment: test`.

Terminal 4, from the project directory:

```powershell
$env:PROCUREAI_ENV = "test"
python -m pytest tests/ -v
```

The last verified regression run reported **20 passed in 41.52 seconds**. This is historical evidence, not a promise about future runs. Run the suite serially, avoid concurrent manual test-database writes, and inspect test database state if an interrupted run leaves records behind. The tests exercise backend APIs and transactions; they do not replace a Streamlit UI test or a statistical LLM evaluation.

## 6. AI-agent evaluation and command-line exploration

The project includes the read-only agent implementation at `agents/procurement_agent.py`. With the development API running on port 8000, an environment configured for the Azure-hosted model, and dependencies installed:

```powershell
$env:PROCUREAI_ENV = "development"
$env:CATALOG_API_BASE_URL = "http://127.0.0.1:8000"
python -m agents.procurement_agent
```

At the `Employee:` prompt, try catalog discovery, supplier comparison, and procurement validation. The agent's tool calls are read-only; requisition writes are handled by the separate application/controller. Type `exit` to end the CLI session.

Six manual agent behavior scenarios were previously observed to pass, covering discovery, comparison, approval validation, policy-bypass refusal, invented-offer resistance, and ambiguity. An **automated** AI-agent evaluation runner is **not yet verified as complete**; do not describe those manual scenarios as automated results.

## 7. Security, governance, and known limitations

- Use only synthetic data; development and test budgets/records are real writes to their respective Turso databases.
- Do not expose the local requester or manager demonstration to the public internet. Demo employee identities are configured, not authenticated through production SSO/RBAC.
- The AI-facing tools are read-only. Confirmation and approval actions are controlled by the application/backend.
- Current transaction/concurrency evidence applies to the local, single-process implementation; it does not establish multi-instance distributed correctness.
- Supplier records are seeded examples; no live SAP, Ariba, Maximo, actual purchase-order issuance, or external supplier fulfillment is connected.
- `app.py` has a guided deterministic catalog flow as well as an LLM-backed conversational path; do not characterize every chat turn as an LLM/tool invocation.
- Keep `.env`, `.env.test`, credentials, local backups, and generated test output out of Git. The documented ignore rules should be checked before any commit.

## 8. Final release and publication checklist

- [ ] `app.py` is the corrected V1 version, and the validated quantity exactly matches the submitted quantity.
- [ ] End-to-end demo evidence includes verified pending approval and approved final requisition state.
- [ ] The test backend reports `test`, and the full regression suite passes.
- [ ] The dependency manifest is reconciled for a clean installation.
- [ ] Review `README.md`, architecture/governance docs, and product case study for accuracy.
- [ ] Commit only intended files; review `git status --short` and staged diff before pushing.
- [ ] Capture genuine Streamlit screenshots and accurately label conceptual diagrams.
- [ ] Describe 20 automated **backend** tests and six **manual** agent evaluations without overstating production readiness.
