-- ============================================================
-- 003_security_policies.sql
-- Row Level Security for Supabase PostgreSQL.
--
-- The FastAPI backend connects with the service-role connection string
-- (server side only) and therefore bypasses RLS. RLS protects the anon
-- and authenticated keys which are NEVER used by the backend.
-- ============================================================

alter table users               enable row level security;
alter table tickets             enable row level security;
alter table conversations       enable row level security;
alter table agent_logs          enable row level security;
alter table knowledge_documents enable row level security;
alter table escalations         enable row level security;
alter table payment_records     enable row level security;

-- Knowledge base is read-only for authenticated users (safe public content).
drop policy if exists "knowledge_read_authenticated" on knowledge_documents;
create policy "knowledge_read_authenticated"
    on knowledge_documents for select
    to authenticated
    using (true);

-- Customers may read only their own tickets, conversations and payments.
-- (The backend passes the service role, so API operations are unaffected.)
drop policy if exists "users_read_own_ticket" on tickets;
create policy "users_read_own_ticket"
    on tickets for select
    to authenticated
    using (auth.uid() = user_id);

drop policy if exists "users_read_own_conversation" on conversations;
create policy "users_read_own_conversation"
    on conversations for select
    to authenticated
    using (auth.uid() = user_id);

drop policy if exists "users_read_own_payments" on payment_records;
create policy "users_read_own_payments"
    on payment_records for select
    to authenticated
    using (auth.uid() = user_id);

-- Agent logs and escalations are internal: no anon/authenticated policies.
-- Only the service role (backend) can read/write them.

-- NOTE:
-- * Never expose the service role key to the browser or Streamlit client code.
-- * The app uses SUPABASE_SERVICE_ROLE_KEY only if you choose the supabase-py
--   client; this project talks to PostgreSQL directly through DATABASE_URL.
