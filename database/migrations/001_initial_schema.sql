-- ============================================================
-- 001_initial_schema.sql
-- Enterprise Customer Support Triage and Resolution Desk (CSE476)
-- Single database: Supabase PostgreSQL
-- ============================================================

create extension if not exists "pgcrypto";   -- gen_random_uuid()
create extension if not exists vector;       -- pgvector (384-dim embeddings)

-- ------------------------------------------------------------
-- users
-- ------------------------------------------------------------
create table if not exists users (
    id          uuid primary key default gen_random_uuid(),
    name        text not null check (length(trim(name)) > 0),
    email       text not null unique check (position('@' in email) > 1),
    created_at  timestamptz not null default now()
);

-- ------------------------------------------------------------
-- tickets
-- ------------------------------------------------------------
create table if not exists tickets (
    id             uuid primary key default gen_random_uuid(),
    user_id        uuid not null references users(id) on delete cascade,
    subject        text not null,
    message        text not null,
    category       text check (category in ('billing', 'technical', 'account', 'other')),
    confidence     numeric(4, 3) check (confidence >= 0 and confidence <= 1),
    status         text not null default 'open'
                   check (status in ('open', 'processing', 'pending', 'resolved', 'escalated', 'failed')),
    assigned_agent text,
    resolution     text,
    priority       text not null default 'medium'
                   check (priority in ('low', 'medium', 'high', 'urgent')),
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now()
);

create index if not exists idx_tickets_status        on tickets (status);
create index if not exists idx_tickets_category      on tickets (category);
create index if not exists idx_tickets_user          on tickets (user_id);
create index if not exists idx_tickets_created_at    on tickets (created_at desc);

-- ------------------------------------------------------------
-- conversations (persistent shared memory)
-- ------------------------------------------------------------
create table if not exists conversations (
    id          uuid primary key default gen_random_uuid(),
    ticket_id   uuid not null references tickets(id) on delete cascade,
    user_id     uuid references users(id) on delete cascade,
    role        text not null check (role in ('customer', 'assistant', 'system', 'human_support')),
    message     text not null,
    created_at  timestamptz not null default now()
);

create index if not exists idx_conversations_ticket on conversations (ticket_id, created_at);
create index if not exists idx_conversations_user   on conversations (user_id);

-- ------------------------------------------------------------
-- agent_logs (append-only audit trail)
-- ------------------------------------------------------------
create table if not exists agent_logs (
    id               uuid primary key default gen_random_uuid(),
    ticket_id        uuid references tickets(id) on delete cascade,
    agent_name       text not null,
    action           text not null,
    input_data       jsonb not null default '{}'::jsonb,
    output_data      jsonb not null default '{}'::jsonb,
    execution_status text not null default 'success'
                     check (execution_status in ('success', 'error', 'skipped')),
    error_message    text,
    duration_ms      integer,
    created_at       timestamptz not null default now()
);

create index if not exists idx_agent_logs_ticket  on agent_logs (ticket_id, created_at);
create index if not exists idx_agent_logs_agent   on agent_logs (agent_name, created_at desc);

-- Enforce append-only behaviour for the audit log
create or replace function prevent_agent_log_update()
returns trigger language plpgsql as $$
begin
    raise exception 'agent_logs is append-only; updates are not allowed';
end;
$$;

drop trigger if exists trg_agent_logs_append_only on agent_logs;
create trigger trg_agent_logs_append_only
    before update on agent_logs
    for each row execute function prevent_agent_log_update();

-- ------------------------------------------------------------
-- knowledge_documents (RAG chunks + pgvector embeddings)
-- ------------------------------------------------------------
create table if not exists knowledge_documents (
    id          uuid primary key default gen_random_uuid(),
    title       text not null,
    content     text not null,
    category    text,
    embedding   vector(384),
    metadata    jsonb not null default '{}'::jsonb,
    created_at  timestamptz not null default now()
);

create index if not exists idx_knowledge_title    on knowledge_documents (title);
create index if not exists idx_knowledge_category on knowledge_documents (category);

-- ------------------------------------------------------------
-- escalations (human-in-the-loop queue)
-- ------------------------------------------------------------
create table if not exists escalations (
    id            uuid primary key default gen_random_uuid(),
    ticket_id     uuid not null references tickets(id) on delete cascade,
    reason        text not null,
    priority      text not null default 'high'
                  check (priority in ('low', 'medium', 'high', 'urgent')),
    assigned_to   text not null default 'Human Support Queue',
    status        text not null default 'pending'
                  check (status in ('pending', 'in_review', 'resolved', 'rejected', 'reassigned')),
    human_verdict text,
    created_at    timestamptz not null default now(),
    resolved_at   timestamptz
);

create index if not exists idx_escalations_status on escalations (status, created_at desc);
create index if not exists idx_escalations_ticket on escalations (ticket_id);

-- ------------------------------------------------------------
-- payment_records (mock billing data used by the Billing Specialist)
-- No real financial data is stored or processed.
-- ------------------------------------------------------------
create table if not exists payment_records (
    id              uuid primary key default gen_random_uuid(),
    user_id         uuid not null references users(id) on delete cascade,
    transaction_ref text not null unique,
    amount          numeric(12, 2) not null check (amount >= 0),
    currency        text not null default 'USD',
    status          text not null default 'completed'
                    check (status in ('completed', 'pending', 'failed', 'refunded')),
    description     text,
    created_at      timestamptz not null default now()
);

create index if not exists idx_payments_user on payment_records (user_id);
create index if not exists idx_payments_ref  on payment_records (transaction_ref);

-- ------------------------------------------------------------
-- updated_at maintenance
-- ------------------------------------------------------------
create or replace function set_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists trg_tickets_updated_at on tickets;
create trigger trg_tickets_updated_at
    before update on tickets
    for each row execute function set_updated_at();
