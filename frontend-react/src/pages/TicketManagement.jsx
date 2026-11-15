import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import {
  Badge,
  Conversation,
  ErrorMsg,
  Panel,
  Spinner,
  Table,
  fmtDate,
} from "../components.jsx";

const EMPTY_FILTERS = { category: "", status: "", priority: "", search: "" };

export default function TicketManagement() {
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [tickets, setTickets] = useState([]);
  const [selected, setSelected] = useState(null);
  const [messages, setMessages] = useState([]);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const loadTickets = async (nextFilters = filters) => {
    setLoading(true);
    try {
      setTickets(await api.tickets(nextFilters));
      setError("");
    } catch (exc) {
      setError(exc.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTickets(EMPTY_FILTERS);
  }, []);

  const openTicket = async (ticket) => {
    setSelected(ticket);
    setMessages([]);
    setLogs([]);
    try {
      const [conversation, agentLogs] = await Promise.all([
        api.conversation(ticket.id),
        api.logs({ ticket_id: ticket.id, limit: 100 }),
      ]);
      setMessages(conversation);
      setLogs(agentLogs);
    } catch (exc) {
      setError(exc.message);
    }
  };

  const reprocess = async () => {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      await api.processTicket(selected.id);
      const refreshed = await api.ticket(selected.id);
      setSelected(refreshed);
      await openTicket(refreshed);
      await loadTickets();
    } catch (exc) {
      setError(exc.message);
    } finally {
      setBusy(false);
    }
  };

  const update = (key) => (event) =>
    setFilters((current) => ({ ...current, [key]: event.target.value }));

  return (
    <div>
      <Panel
        title="Support Queue"
        subtitle="Filter by lifecycle state, category or free-text search"
        actions={
          <button
            className="btn btn-secondary btn-small"
            onClick={() => loadTickets()}
            disabled={loading}
          >
            Refresh
          </button>
        }
      >
        <div className="filter-row">
          <div>
            <label>Status</label>
            <select value={filters.status} onChange={update("status")}>
              <option value="">all</option>
              <option value="open">open</option>
              <option value="processing">processing</option>
              <option value="resolved">resolved</option>
              <option value="escalated">escalated</option>
              <option value="failed">failed</option>
            </select>
          </div>
          <div>
            <label>Category</label>
            <select value={filters.category} onChange={update("category")}>
              <option value="">all</option>
              <option value="billing">billing</option>
              <option value="technical">technical</option>
              <option value="account">account</option>
              <option value="other">other</option>
            </select>
          </div>
          <div>
            <label>Priority</label>
            <select value={filters.priority} onChange={update("priority")}>
              <option value="">all</option>
              <option value="low">low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
              <option value="urgent">urgent</option>
            </select>
          </div>
          <div className="filter-search">
            <label>Search</label>
            <input
              value={filters.search}
              onChange={update("search")}
              onKeyDown={(event) => event.key === "Enter" && loadTickets()}
              placeholder="Subject text… (Enter to search)"
            />
          </div>
          <div style={{ display: "flex", alignItems: "flex-end" }}>
            <button className="btn" onClick={() => loadTickets()} disabled={loading}>
              Apply filters
            </button>
          </div>
        </div>

        <ErrorMsg message={error} />
        {loading ? (
          <Spinner label="Loading tickets…" />
        ) : (
          <Table
            rows={tickets}
            selectedId={selected?.id}
            onRowClick={openTicket}
            columns={[
              { key: "subject", label: "Subject", render: (row) => <span className="cell-strong">{row.subject}</span> },
              { key: "category", label: "Category", render: (row) => <Badge status={row.category || "unclassified"} /> },
              { key: "status", label: "Status", render: (row) => <Badge status={row.status} /> },
              { key: "priority", label: "Priority", render: (row) => <Badge status={row.priority} /> },
              { key: "assigned_agent", label: "Agent", render: (row) => row.assigned_agent || "—" },
              { key: "confidence", label: "Conf.", render: (row) => (row.confidence == null ? "—" : `${Math.round(row.confidence * 100)}%`) },
              { key: "created_at", label: "Created", render: (row) => <span className="cell-muted">{fmtDate(row.created_at)}</span> },
            ]}
            empty="No tickets match these filters."
          />
        )}
      </Panel>

      {selected && (
        <div className="grid-side">
          <Panel
            title="Ticket Detail"
            subtitle={selected.id}
            actions={
              <button className="btn btn-small" onClick={reprocess} disabled={busy}>
                {busy ? "Reprocessing…" : "Reprocess with AI"}
              </button>
            }
          >
            <div className="kv" style={{ marginBottom: 14 }}>
              <dt>Subject</dt>
              <dd>{selected.subject}</dd>
              <dt>Status</dt>
              <dd><Badge status={selected.status} /></dd>
              <dt>Category</dt>
              <dd><Badge status={selected.category || "unclassified"} /></dd>
              <dt>Priority</dt>
              <dd><Badge status={selected.priority} /></dd>
              <dt>Assigned agent</dt>
              <dd>{selected.assigned_agent || "—"}</dd>
              <dt>Confidence</dt>
              <dd>{selected.confidence == null ? "—" : `${Math.round(selected.confidence * 100)}%`}</dd>
              <dt>Created</dt>
              <dd>{fmtDate(selected.created_at)}</dd>
            </div>
            <div className="mini-label">Customer message</div>
            <div className="message-box" style={{ marginBottom: 14 }}>{selected.message}</div>
            {selected.resolution && (
              <>
                <div className="mini-label">Resolution</div>
                <div className="reply-box">{selected.resolution}</div>
              </>
            )}
          </Panel>

          <div>
            <Panel title="Conversation" subtitle="Shared memory across turns">
              <Conversation messages={messages} />
            </Panel>
            <Panel title="Agent Logs" subtitle="Execution records for this ticket">
              <Table
                rows={logs}
                columns={[
                  { key: "agent_name", label: "Agent" },
                  { key: "action", label: "Action" },
                  { key: "execution_status", label: "Status", render: (row) => <Badge status={row.execution_status} /> },
                  { key: "duration_ms", label: "ms", render: (row) => row.duration_ms ?? "—" },
                ]}
                empty="No agent logs for this ticket."
              />
            </Panel>
          </div>
        </div>
      )}
    </div>
  );
}
