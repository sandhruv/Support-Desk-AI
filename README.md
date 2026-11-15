# Enterprise Customer Support Triage and Resolution Desk

**CSE476 - Agentic AI and Intelligent Automation** · Multi-Agent AI System

A working multi-agent support desk: complaints are classified, routed to specialist
agents, answered with **RAG (Supabase pgvector)**, remembered across sessions and
escalated to a human when confidence is low. Built with **Semantic Kernel + Groq
(free tier) + Supabase PostgreSQL + FastAPI + Streamlit**.

---

## 1. Overview

```
Customer -> Classifier Agent -> Billing / Technical / Account Specialist
                                     |                  (low confidence / unresolved)
                                     v
                              Escalation Router -> Human Support -> Verdict
```

Every agent is a separate module with its own prompt, **two real Python tools**
registered as Semantic Kernel plugins, structured output, Supabase persistence and
append-only execution logging. The coordinator performs real routing/handoffs and
keeps a shared ticket state.

## 2. Agent roster

| Agent | File | Responsibilities | Tools |
|---|---|---|---|
| Classifier Agent | `agents/classifier_agent.py` | intent, category, confidence, specialist assignment | `keyword_classification_tool`, `classification_validation_tool` |
| Billing Specialist | `agents/billing_agent.py` | duplicate charges, refunds, invoices, policy questions | `lookup_payment_record`, `check_billing_policy` |
| Technical Specialist | `agents/technical_agent.py` | crashes, login errors, grounded troubleshooting | `search_knowledge_base`, `validate_technical_solution` |
| Account Specialist | `agents/account_agent.py` | access issues, password-reset guidance (never passwords) | `lookup_customer_account`, `validate_account_support_request` |
| Escalation Router | `agents/escalation_agent.py` | human queue, reasons, priorities, verdicts | `create_escalation_ticket`, `check_escalation_status` |

## 3. Why router-to-specialists?

A single generalist prompt cannot guarantee grounded billing actions *and*
citation-checked technical answers. Specialists give clear responsibility
boundaries, testable tools, cheaper prompts, and an explicit escalation path when
confidence < 70%. The classifier is deterministic-checked, so routing is
explainable during a viva.

## 4. Database design (Supabase PostgreSQL only)

| Table | Purpose |
|---|---|
| `users` | customer identity |
| `tickets` | state machine: open/processing/pending/resolved/escalated/failed |
| `conversations` | persistent shared memory (customer/assistant/human) |
| `agent_logs` | append-only audit trail (trigger blocks UPDATE) |
| `knowledge_documents` | RAG chunks + `vector(384)` embeddings |
| `escalations` | human-in-the-loop queue and verdicts |
| `payment_records` | **mock** billing data (no real transactions) |

Migrations: `database/migrations/001_initial_schema.sql`,
`002_vector_search.sql` (pgvector + `match_knowledge_chunks` cosine function),
`003_security_policies.sql` (RLS; service role stays server-side).

## 5. RAG pipeline

`knowledge_base/*.txt` → clean → overlapping word chunks → local
`sentence-transformers/all-MiniLM-L6-v2` 384-dim embeddings → Supabase
`knowledge_documents` → `match_knowledge_chunks` similarity search → top-k chunks
passed to the Technical Specialist → answer validated for grounding + citations.
If retrieval is insufficient or the answer is ungrounded, the ticket escalates.

## 6. Shared memory

`memory/conversation_memory.py` writes every message to `conversations` and reloads
history before each agent run (follow-up demo: "My payment failed." → "TXN1001.").

## 7. Installation

```powershell
cd E:\customer-support-ai
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 8. Configuration

```powershell
copy .env.example .env
```

Fill in `.env` (never commit it):

| Variable | Where to get it |
|---|---|
| `GROQ_API_KEY` | https://console.groq.com/keys |
| `GROQ_MODEL` | any free model available to your account (default `openai/gpt-oss-120b`; run `python run.py doctor` to list models) |
| `DATABASE_URL` | Supabase → Connect → Session pooler URI (port 5432, add `?sslmode=require`) |
| `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_SERVICE_ROLE_KEY` | Supabase → Project Settings → API (backend only) |
| `EMBEDDING_MODEL` | keep default |

**SQL migrations:** open Supabase → SQL Editor and run the three files in
`database/migrations/` in order (or `psql "$env:DATABASE_URL" -f ...`).

## 9. Run

```powershell
python run.py doctor        # verify config / Groq / DB
python run.py seed          # demo user + tickets + mock payments
python run.py ingest        # chunk + embed knowledge base into pgvector
python run.py api           # FastAPI  -> http://localhost:8000/docs
python run.py ui            # Streamlit -> http://localhost:8501
python run.py ui-react      # React (Vite) -> http://localhost:5173
python run.py demo          # runs billing / technical / escalation scenarios
python run.py test          # pytest suite
```

The **React dashboard** (`frontend-react/`, Vite + Recharts) is an optional
alternative UI with the same six pages, live charts and the full human-verdict
workflow. First run only: `cd frontend-react; npm install`. It talks to the
FastAPI backend on port 8000 (CORS origins for 5173 are pre-configured).

Pages: Overview · Customer Support · Ticket Management · Agent Monitoring ·
Knowledge Base · Human Escalation.

## 10. Tests

`python run.py test` - deterministic unit tests mock Groq and the DB layer
(classifier tools, billing, RAG grounding, routing, escalation, human verdicts,
API contracts, migrations). Live Supabase/Groq tests are **skipped** unless
credentials are set (never reported as passed when skipped). Heavy embedding
integration test: set `RUN_EMBEDDING_TESTS=1`.

## 11. Handled failure scenario

Groq free-tier **rate limit**: the client retries with exponential backoff, then
raises a friendly retryable error. The API returns HTTP 503 with
`ticket_preserved: true`, the ticket stays in the database and can be
re-processed later - no silent provider switch, no fabricated answer.

## 12. Project layout

```
agents/        five agent modules + base class
tools/         real Python tools / Semantic Kernel plugins
orchestration/ coordinator · shared_state · routing
llm/           Groq client · config · prompts · SK integration
rag/           loader · chunking · embeddings · retriever · ingestion
memory/        persistent conversation memory
database/      connection · repository · migrations · seed
api/           FastAPI app · routes · schemas · deps
frontend/      Streamlit app + six pages
tests/         unit + opt-in live integration tests
notebooks/     multi_agent_demo.ipynb
diagrams/      architecture.mmd
```
