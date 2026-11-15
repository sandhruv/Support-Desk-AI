import React, { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api.js";
import {
  Badge,
  ErrorMsg,
  MetricCard,
  Panel,
  Spinner,
  Table,
  fmtDate,
} from "../components.jsx";

const COLORS = ["#7c5cff", "#14b8a6", "#f59e0b", "#e11d48", "#0ea5e9", "#a855f7"];

export default function Overview({ onNavigate }) {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    api
      .stats()
      .then((data) => {
        setStats(data);
        setError("");
      })
      .catch((exc) => setError(exc.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  if (loading) return <Spinner label="Loading live dashboard…" />;
  if (error) return <ErrorMsg message={error} />;
  if (!stats) return null;

  const categoryData = (stats.category_distribution || []).map((row) => ({
    name: row.category || "unclassified",
    value: row.count,
  }));
  const statusData = (stats.status_distribution || []).map((row) => ({
    name: row.status,
    value: row.count,
  }));
  const agentData = (stats.agent_performance || []).map((row) => ({
    name: (row.agent_name || "").replace(" Agent", "").replace(" Specialist", ""),
    runs: row.runs,
    errors: row.errors,
  }));
  const escalationStats = stats.escalations || {};

  return (
    <div>
      <div className="metric-grid">
        <MetricCard label="Total Tickets" value={stats.total} hint="All time" />
        <MetricCard
          label="Resolved"
          value={stats.resolved}
          hint={`${Math.round((stats.resolution_rate || 0) * 100)}% resolution rate`}
        />
        <MetricCard label="Pending" value={stats.pending} hint="Open or processing" />
        <MetricCard
          label="Escalations"
          value={escalationStats.total ?? stats.escalated}
          hint={`${escalationStats.pending ?? 0} awaiting human review`}
        />
      </div>

      <div className="grid-2">
        <Panel title="Category Distribution" subtitle="Classifier output across all tickets">
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={categoryData}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={55}
                  outerRadius={90}
                  paddingAngle={3}
                >
                  {categoryData.map((entry, index) => (
                    <Cell key={entry.name} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="chips">
            {categoryData.map((entry, index) => (
              <span key={entry.name} className="chip">
                <span
                  style={{
                    display: "inline-block",
                    width: 8,
                    height: 8,
                    borderRadius: 99,
                    background: COLORS[index % COLORS.length],
                    marginRight: 6,
                  }}
                />
                {entry.name} · {entry.value}
              </span>
            ))}
          </div>
        </Panel>

        <Panel title="Ticket Status" subtitle="Lifecycle state of the support queue">
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={statusData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 12 }} width={30} />
                <Tooltip />
                <Bar dataKey="value" fill="#7c5cff" radius={[6, 6, 0, 0]} maxBarSize={56} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <Panel
        title="Recent Tickets"
        subtitle="Latest activity from the multi-agent pipeline"
        actions={
          <button className="btn btn-secondary btn-small" onClick={() => onNavigate("tickets")}>
            View all tickets
          </button>
        }
      >
        <Table
          rows={stats.recent_tickets || []}
          columns={[
            { key: "subject", label: "Subject", render: (row) => <span className="cell-strong">{row.subject}</span> },
            { key: "category", label: "Category", render: (row) => <Badge status={row.category || "unclassified"} /> },
            { key: "status", label: "Status", render: (row) => <Badge status={row.status} /> },
            { key: "priority", label: "Priority", render: (row) => <Badge status={row.priority} /> },
            { key: "assigned_agent", label: "Agent", render: (row) => row.assigned_agent || "—" },
            { key: "created_at", label: "Created", render: (row) => <span className="cell-muted">{fmtDate(row.created_at)}</span> },
          ]}
          onRowClick={() => onNavigate("tickets")}
          empty="No tickets yet. Submit one from Customer Support."
        />
      </Panel>

      <div className="grid-side">
        <Panel title="Agent Performance" subtitle="Runs recorded per agent (agent_logs)">
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={agentData} layout="vertical" margin={{ left: 10, right: 16 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
                <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12 }} />
                <YAxis type="category" dataKey="name" width={130} tick={{ fontSize: 11.5 }} />
                <Tooltip />
                <Bar dataKey="runs" fill="#14b8a6" radius={[0, 6, 6, 0]} maxBarSize={18} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel title="Quick Actions" subtitle="Jump into the core workflows">
          <div className="btn-row">
            <button className="btn" onClick={() => onNavigate("customer")}>
              New complaint
            </button>
            <button className="btn btn-secondary" onClick={() => onNavigate("escalations")}>
              Review escalations
            </button>
            <button className="btn btn-secondary" onClick={() => onNavigate("knowledge")}>
              Knowledge base
            </button>
          </div>
          <div style={{ marginTop: 18 }}>
            <div className="kv">
              <dt>Failed runs</dt>
              <dd>{stats.failed}</dd>
              <dt>Escalated tickets</dt>
              <dd>{stats.escalated}</dd>
              <dt>Awaiting verdict</dt>
              <dd>{escalationStats.pending ?? 0}</dd>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}
