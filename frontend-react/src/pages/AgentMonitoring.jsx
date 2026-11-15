import React, { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api.js";
import { Badge, ErrorMsg, Panel, Spinner, Table, fmtDate } from "../components.jsx";

export default function AgentMonitoring() {
  const [agents, setAgents] = useState([]);
  const [logs, setLogs] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [agentFilter, setAgentFilter] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const [roster, agentLogs, dashboard] = await Promise.all([
        api.agents(),
        api.logs({ limit: 200 }),
        api.stats(),
      ]);
      setAgents(roster);
      setLogs(agentLogs);
      setStats(dashboard);
      setError("");
    } catch (exc) {
      setError(exc.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const visibleLogs = agentFilter
    ? logs.filter((log) => log.agent_name === agentFilter)
    : logs;
  const errors = logs.filter((log) => log.execution_status === "error");

  const performance = (stats?.agent_performance || []).map((row) => ({
    name: (row.agent_name || "").replace(" Agent", "").replace(" Specialist", ""),
    runs: row.runs,
    errors: row.errors,
  }));

  if (loading) return <Spinner label="Loading agent telemetry…" />;
  if (error) return <ErrorMsg message={error} />;

  return (
    <div>
      <Panel
        title="Agent Roster"
        subtitle="Semantic Kernel agents with their tools and responsibilities"
        actions={
          <button className="btn btn-secondary btn-small" onClick={load}>
            Refresh
          </button>
        }
      >
        <div className="agent-grid">
          {agents.map((agent) => (
            <div key={agent.name} className="agent-card">
              <div className="agent-card-top">
                <span className="agent-name">{agent.name}</span>
                <Badge status={agent.status || "active"} />
              </div>
              <p className="agent-desc">{agent.description}</p>
              <div className="mini-label">Tools</div>
              <div className="chips">
                {(agent.tools || []).map((tool) => (
                  <span key={tool} className="chip chip-blue">
                    {tool}
                  </span>
                ))}
              </div>
              <div className="mini-label">Responsibilities</div>
              <div className="chips">
                {(agent.responsibilities || []).map((item) => (
                  <span key={item} className="chip">
                    {item}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Panel>

      <div className="grid-side">
        <Panel title="Runs per Agent" subtitle="Total logged executions">
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={performance} layout="vertical" margin={{ left: 8, right: 16 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
                <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12 }} />
                <YAxis type="category" dataKey="name" width={130} tick={{ fontSize: 11.5 }} />
                <Tooltip />
                <Bar dataKey="runs" fill="#7c5cff" radius={[0, 6, 6, 0]} maxBarSize={18} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel title="Errors" subtitle="Failed agent executions (if any)">
          {errors.length === 0 ? (
            <div className="empty">No agent errors recorded. Healthy pipeline.</div>
          ) : (
            <Table
              rows={errors.slice(0, 12)}
              columns={[
                { key: "agent_name", label: "Agent" },
                { key: "action", label: "Action" },
                { key: "error_message", label: "Error", render: (row) => <span className="cell-muted">{row.error_message || "—"}</span> },
                { key: "created_at", label: "When", render: (row) => <span className="cell-muted">{fmtDate(row.created_at)}</span> },
              ]}
            />
          )}
        </Panel>
      </div>

      <Panel
        title="Execution Logs"
        subtitle={`${visibleLogs.length} entries`}
        actions={
          <div style={{ minWidth: 200 }}>
            <select value={agentFilter} onChange={(event) => setAgentFilter(event.target.value)}>
              <option value="">All agents</option>
              {agents.map((agent) => (
                <option key={agent.name} value={agent.name}>
                  {agent.name}
                </option>
              ))}
            </select>
          </div>
        }
      >
        <Table
          rows={visibleLogs.slice(0, 120)}
          columns={[
            { key: "created_at", label: "Time", render: (row) => <span className="cell-muted">{fmtDate(row.created_at)}</span> },
            { key: "agent_name", label: "Agent", render: (row) => <span className="cell-strong">{row.agent_name}</span> },
            { key: "action", label: "Action" },
            { key: "execution_status", label: "Status", render: (row) => <Badge status={row.execution_status} /> },
            { key: "duration_ms", label: "Duration", render: (row) => (row.duration_ms == null ? "—" : `${row.duration_ms} ms`) },
            { key: "ticket_id", label: "Ticket", render: (row) => <span className="mono">{row.ticket_id ? row.ticket_id.slice(0, 8) : "—"}</span> },
          ]}
          empty="No agent logs yet."
        />
      </Panel>
    </div>
  );
}
