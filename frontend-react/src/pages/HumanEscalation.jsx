import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import {
  Badge,
  Conversation,
  ErrorMsg,
  Panel,
  Spinner,
  SuccessMsg,
  Table,
  fmtDate,
} from "../components.jsx";

const EMPTY_VERDICT = {
  verdict: "",
  resolution: "",
  action: "resolve",
  operator: "Human Support",
};

export default function HumanEscalation() {
  const [statusFilter, setStatusFilter] = useState("");
  const [escalations, setEscalations] = useState([]);
  const [selected, setSelected] = useState(null);
  const [messages, setMessages] = useState([]);
  const [logs, setLogs] = useState([]);
  const [verdict, setVerdict] = useState(EMPTY_VERDICT);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = async (status = statusFilter) => {
    setLoading(true);
    try {
      const rows = await api.escalations(status ? { status } : undefined);
      setEscalations(rows);
      setError("");
    } catch (exc) {
      setError(exc.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load("");
  }, []);

  const openEscalation = async (escalation) => {
    setSelected(escalation);
    setMessages([]);
    setLogs([]);
    setNotice("");
    try {
      const [conversation, agentLogs] = await Promise.all([
        api.conversation(escalation.ticket_id),
        api.logs({ ticket_id: escalation.ticket_id, limit: 100 }),
      ]);
      setMessages(conversation);
      setLogs(agentLogs);
    } catch (exc) {
      setError(exc.message);
    }
  };

  const update = (key) => (event) =>
    setVerdict((current) => ({ ...current, [key]: event.target.value }));

  const submitVerdict = async (event) => {
    event.preventDefault();
    if (!selected) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api.verdict(selected.id, verdict);
      setNotice("Human verdict recorded. Ticket updated and customer notified.");
      setVerdict(EMPTY_VERDICT);
      await load(statusFilter);
      const [conversation, agentLogs] = await Promise.all([
        api.conversation(selected.ticket_id),
        api.logs({ ticket_id: selected.ticket_id, limit: 100 }),
      ]);
      setMessages(conversation);
      setLogs(agentLogs);
    } catch (exc) {
      setError(exc.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <Panel
        title="Escalation Queue"
        subtitle="Tickets the AI could not safely resolve on its own"
        actions={
          <div className="btn-row">
            <select
              value={statusFilter}
              onChange={(event) => {
                setStatusFilter(event.target.value);
                load(event.target.value);
              }}
            >
              <option value="">all</option>
              <option value="pending">pending</option>
              <option value="resolved">resolved</option>
            </select>
            <button className="btn btn-secondary btn-small" onClick={() => load()}>
              Refresh
            </button>
          </div>
        }
      >
        <ErrorMsg message={error} />
        {loading ? (
          <Spinner label="Loading escalations…" />
        ) : (
          <Table
            rows={escalations}
            selectedId={selected?.id}
            onRowClick={openEscalation}
            columns={[
              { key: "created_at", label: "Created", render: (row) => <span className="cell-muted">{fmtDate(row.created_at)}</span> },
              { key: "customer_name", label: "Customer" },
              { key: "subject", label: "Subject", render: (row) => <span className="cell-strong">{row.subject || "—"}</span> },
              { key: "priority", label: "Priority", render: (row) => <Badge status={row.priority} /> },
              { key: "category", label: "Category", render: (row) => <Badge status={row.category || "unclassified"} /> },
              { key: "status", label: "Status", render: (row) => <Badge status={row.status} /> },
              { key: "assigned_to", label: "Queue" },
            ]}
            empty="No escalations for this filter. The AI resolved everything."
          />
        )}
      </Panel>

      {selected && (
        <div className="grid-side">
          <div>
            <Panel
              title="Escalation Detail"
              subtitle={selected.id}
              actions={<Badge status={selected.status} />}
            >
              <div className="kv" style={{ marginBottom: 14 }}>
                <dt>Customer</dt>
                <dd>
                  {selected.customer_name || "—"}{" "}
                  <span className="cell-muted">
                    {selected.customer_email ? `· ${selected.customer_email}` : ""}
                  </span>
                </dd>
                <dt>Subject</dt>
                <dd>{selected.subject || "—"}</dd>
                <dt>Ticket status</dt>
                <dd><Badge status={selected.ticket_status || "escalated"} /></dd>
                <dt>AI category</dt>
                <dd><Badge status={selected.category || "unclassified"} /></dd>
                <dt>AI confidence</dt>
                <dd>
                  {selected.confidence == null
                    ? "—"
                    : `${Math.round(selected.confidence * 100)}%`}
                </dd>
                <dt>Priority</dt>
                <dd><Badge status={selected.priority} /></dd>
              </div>

              <div className="mini-label">Customer message</div>
              <div className="message-box" style={{ marginBottom: 14 }}>
                {selected.message || "—"}
              </div>

              <div className="mini-label">Why it was escalated</div>
              <div className="message-box" style={{ marginBottom: 14 }}>
                {selected.reason}
              </div>

              {selected.human_verdict && (
                <>
                  <div className="mini-label">Human verdict</div>
                  <div className="reply-box">{selected.human_verdict}</div>
                </>
              )}
            </Panel>

            <Panel title="Agent Logs" subtitle="How the AI reached the escalation">
              <Table
                rows={logs}
                columns={[
                  { key: "agent_name", label: "Agent" },
                  { key: "action", label: "Action" },
                  { key: "execution_status", label: "Status", render: (row) => <Badge status={row.execution_status} /> },
                  { key: "duration_ms", label: "ms", render: (row) => row.duration_ms ?? "—" },
                ]}
                empty="No logs."
              />
            </Panel>
          </div>

          <div>
            <Panel title="Human Verdict" subtitle="Close the loop with a real decision">
              {selected.status === "resolved" ? (
                <div className="empty">
                  This escalation is already resolved. Select a pending escalation to
                  issue a verdict.
                </div>
              ) : (
                <form onSubmit={submitVerdict}>
                  <label>Verdict</label>
                  <textarea
                    required
                    minLength={3}
                    value={verdict.verdict}
                    onChange={update("verdict")}
                    placeholder="What did you decide after reviewing the case?"
                    style={{ minHeight: 80 }}
                  />
                  <div style={{ marginTop: 12 }}>
                    <label>Resolution note (sent to customer)</label>
                    <textarea
                      value={verdict.resolution}
                      onChange={update("resolution")}
                      placeholder="We refunded the duplicate charge and confirmed by email."
                      style={{ minHeight: 80 }}
                    />
                  </div>
                  <div className="form-grid" style={{ marginTop: 12 }}>
                    <div>
                      <label>Action</label>
                      <select value={verdict.action} onChange={update("action")}>
                        <option value="resolve">resolve</option>
                        <option value="reject">reject</option>
                        <option value="reassign">reassign</option>
                      </select>
                    </div>
                    <div>
                      <label>Operator</label>
                      <input value={verdict.operator} onChange={update("operator")} />
                    </div>
                  </div>
                  <div className="btn-row" style={{ marginTop: 14 }}>
                    <button className="btn" type="submit" disabled={busy}>
                      {busy ? "Submitting…" : "Submit verdict"}
                    </button>
                  </div>
                </form>
              )}
              <SuccessMsg message={notice} />
            </Panel>

            <Panel title="Conversation" subtitle="Full shared memory for this ticket">
              <Conversation messages={messages} />
            </Panel>
          </div>
        </div>
      )}
    </div>
  );
}
