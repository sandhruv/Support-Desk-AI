import React, { useState } from "react";
import { api } from "../api.js";
import {
  Badge,
  Conversation,
  ErrorMsg,
  Panel,
  Spinner,
  SuccessMsg,
} from "../components.jsx";

const EMPTY_FORM = {
  name: "",
  email: "",
  subject: "",
  priority: "medium",
  message: "",
};

export default function CustomerSupport() {
  const [form, setForm] = useState(EMPTY_FORM);
  const [ticket, setTicket] = useState(null);
  const [result, setResult] = useState(null);
  const [messages, setMessages] = useState([]);
  const [busy, setBusy] = useState(false);
  const [statusText, setStatusText] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [followUp, setFollowUp] = useState("");

  const update = (key) => (event) =>
    setForm((current) => ({ ...current, [key]: event.target.value }));

  const loadConversation = async (ticketId) => {
    try {
      setMessages(await api.conversation(ticketId));
    } catch {
      setMessages([]);
    }
  };

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    setResult(null);
    setStatusText("Creating ticket…");
    try {
      const created = await api.createTicket(form);
      setTicket(created.ticket);
      setStatusText("Running multi-agent pipeline (classifier → specialist → resolution)…");
      const processed = await api.processTicket(created.ticket.id);
      setResult(processed);
      await loadConversation(created.ticket.id);
      setStatusText("");
    } catch (exc) {
      setError(exc.message);
      setStatusText("");
    } finally {
      setBusy(false);
    }
  };

  const sendFollowUp = async () => {
    if (!ticket || !followUp.trim()) return;
    setBusy(true);
    setError("");
    setNotice("");
    setStatusText("Saving follow-up and reprocessing…");
    try {
      await api.addMessage(ticket.id, followUp.trim());
      setFollowUp("");
      const processed = await api.processTicket(ticket.id);
      setResult(processed);
      await loadConversation(ticket.id);
      setNotice("Follow-up processed by the agent team.");
    } catch (exc) {
      setError(exc.message);
    } finally {
      setStatusText("");
      setBusy(false);
    }
  };

  const reset = () => {
    setForm(EMPTY_FORM);
    setTicket(null);
    setResult(null);
    setMessages([]);
    setError("");
    setNotice("");
  };

  return (
    <div className="grid-side">
      <div>
        <Panel title="Submit a Complaint" subtitle="Tickets are classified and routed automatically">
          <form onSubmit={submit}>
            <div className="form-grid">
              <div>
                <label>Full name</label>
                <input
                  required
                  value={form.name}
                  onChange={update("name")}
                  placeholder="Aarav Sharma"
                />
              </div>
              <div>
                <label>Email</label>
                <input
                  required
                  type="email"
                  value={form.email}
                  onChange={update("email")}
                  placeholder="aarav@example.com"
                />
              </div>
              <div className="span-2">
                <label>Subject</label>
                <input
                  required
                  value={form.subject}
                  onChange={update("subject")}
                  placeholder="Duplicate charge on my card"
                />
              </div>
              <div>
                <label>Priority</label>
                <select value={form.priority} onChange={update("priority")}>
                  <option value="low">low</option>
                  <option value="medium">medium</option>
                  <option value="high">high</option>
                  <option value="urgent">urgent</option>
                </select>
              </div>
              <div className="span-2">
                <label>Describe the problem</label>
                <textarea
                  required
                  minLength={5}
                  value={form.message}
                  onChange={update("message")}
                  placeholder="I was charged twice for TXNDEMO01. Please refund the duplicate."
                />
              </div>
            </div>
            <div className="btn-row" style={{ marginTop: 16 }}>
              <button className="btn" type="submit" disabled={busy}>
                {busy ? "Processing…" : "Submit & process"}
              </button>
              <button
                className="btn btn-secondary"
                type="button"
                onClick={reset}
                disabled={busy}
              >
                Reset
              </button>
            </div>
          </form>

          {statusText && <Spinner label={statusText} />}
          <ErrorMsg message={error} />
          <SuccessMsg message={notice} />
        </Panel>

        {ticket && (
          <Panel title="Conversation" subtitle={`Ticket ${ticket.id}`}>
            <Conversation messages={messages} />
            <div style={{ marginTop: 14 }}>
              <label>Follow-up message</label>
              <textarea
                value={followUp}
                onChange={(event) => setFollowUp(event.target.value)}
                placeholder="Any additional context for the support team…"
                style={{ minHeight: 70 }}
              />
              <div className="btn-row" style={{ marginTop: 10 }}>
                <button
                  className="btn btn-small"
                  onClick={sendFollowUp}
                  disabled={busy || !followUp.trim()}
                >
                  Send & reprocess
                </button>
              </div>
            </div>
          </Panel>
        )}
      </div>

      <div>
        <Panel title="Agent Result" subtitle="Live outcome from the Groq-powered pipeline">
          {!result && !busy && (
            <div className="empty">
              Submit a complaint to see the classifier decision, specialist reply and
              full agent trace.
            </div>
          )}
          {result && (
            <div>
              <div className="kv" style={{ marginBottom: 16 }}>
                <dt>Status</dt>
                <dd>
                  <Badge status={result.status} />
                </dd>
                <dt>Category</dt>
                <dd>
                  <Badge status={result.category || "unclassified"} />
                </dd>
                <dt>Confidence</dt>
                <dd>{Math.round((result.confidence || 0) * 100)}%</dd>
                <dt>Assigned agent</dt>
                <dd>{result.assigned_agent || "—"}</dd>
                <dt>Duration</dt>
                <dd>{(result.duration_ms / 1000).toFixed(1)}s</dd>
              </div>

              {result.customer_reply && (
                <div style={{ marginBottom: 16 }}>
                  <div className="mini-label">Customer reply</div>
                  <div className="reply-box">{result.customer_reply}</div>
                </div>
              )}

              {result.sources && result.sources.length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <div className="mini-label">RAG sources</div>
                  <div className="chips">
                    {result.sources.map((source) => (
                      <span key={source} className="chip chip-blue">
                        {source}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {result.error && <ErrorMsg message={result.error} />}

              {result.escalation && result.escalation.reason && (
                <div style={{ marginBottom: 16 }}>
                  <div className="mini-label">Escalation</div>
                  <div className="message-box">
                    <Badge status={result.escalation.priority || "high"} />{" "}
                    {result.escalation.reason}
                  </div>
                </div>
              )}

              <div className="mini-label">Execution trace</div>
              <div className="trace">
                {(result.trace || []).map((step, index) => (
                  <div key={index} className="trace-item">
                    <div className="trace-index">{index + 1}</div>
                    <div className="trace-body">
                      <div>
                        <span className="trace-agent">{step.agent}</span>
                        <span className="trace-action">{step.action}</span>
                        {step.status && step.status !== "ok" && (
                          <span style={{ marginLeft: 8 }}>
                            <Badge status={step.status} />
                          </span>
                        )}
                      </div>
                      {step.detail && <div className="trace-detail">{step.detail}</div>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
