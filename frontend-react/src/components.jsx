import React from "react";

export function MetricCard({ label, value, hint }) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      {hint && <div className="metric-hint">{hint}</div>}
    </div>
  );
}

export function Badge({ status }) {
  const key = (status || "other").toLowerCase().replace(/\s+/g, "_");
  return <span className={`badge badge-${key}`}>{key.replace(/_/g, " ")}</span>;
}

export function Panel({ title, subtitle, actions, children, className = "" }) {
  return (
    <section className={`panel ${className}`}>
      {(title || actions) && (
        <div className="panel-head">
          <div>
            {title && <h3>{title}</h3>}
            {subtitle && <p className="panel-subtitle">{subtitle}</p>}
          </div>
          {actions && <div className="panel-actions">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Table({ columns, rows, selectedId, onRowClick, empty = "No records." }) {
  if (!rows || rows.length === 0) return <div className="empty">{empty}</div>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key}>{column.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const id = row.id ?? index;
            return (
              <tr
                key={id}
                className={`${onRowClick ? "clickable" : ""} ${
                  selectedId === row.id ? "selected" : ""
                }`}
                onClick={() => onRowClick && onRowClick(row)}
              >
                {columns.map((column) => (
                  <td key={column.key}>
                    {column.render ? column.render(row) : row[column.key] ?? "—"}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

const ROLE_LABELS = {
  customer: "Customer",
  assistant: "AI Assistant",
  human_support: "Human Support",
  system: "System",
};

export function Conversation({ messages }) {
  if (!messages || messages.length === 0) {
    return <div className="empty">No conversation history yet.</div>;
  }
  return (
    <div className="conversation">
      {messages.map((message) => (
        <div key={message.id} className={`bubble bubble-${message.role}`}>
          <span className="bubble-role">{ROLE_LABELS[message.role] || message.role}</span>
          <p>{message.message}</p>
        </div>
      ))}
    </div>
  );
}

export function Spinner({ label = "Loading…" }) {
  return (
    <div className="spinner">
      <span className="dot" /> {label}
    </div>
  );
}

export function ErrorMsg({ message }) {
  if (!message) return null;
  return <div className="error">{message}</div>;
}

export function SuccessMsg({ message }) {
  if (!message) return null;
  return <div className="success">{message}</div>;
}

export function Empty({ children }) {
  return <div className="empty">{children}</div>;
}

export function fmtDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return isNaN(date.getTime()) ? value : date.toLocaleString();
}
