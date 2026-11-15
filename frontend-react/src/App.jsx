import React, { useEffect, useState } from "react";
import { api } from "./api.js";
import Overview from "./pages/Overview.jsx";
import CustomerSupport from "./pages/CustomerSupport.jsx";
import TicketManagement from "./pages/TicketManagement.jsx";
import AgentMonitoring from "./pages/AgentMonitoring.jsx";
import KnowledgeBase from "./pages/KnowledgeBase.jsx";
import HumanEscalation from "./pages/HumanEscalation.jsx";

const PAGES = [
  {
    id: "overview",
    label: "Overview",
    subtitle: "Live health of the multi-agent support desk: volume, resolution and agent activity.",
    component: Overview,
    group: "Operations",
  },
  {
    id: "customer",
    label: "Customer Support",
    subtitle: "Submit a complaint — the Classifier routes it to the right specialist automatically.",
    component: CustomerSupport,
    group: "Operations",
  },
  {
    id: "tickets",
    label: "Ticket Management",
    subtitle: "Search and inspect tickets, agent decisions and full conversations.",
    component: TicketManagement,
    group: "Operations",
  },
  {
    id: "agents",
    label: "Agent Monitoring",
    subtitle: "The five agents, their tools, execution traces and errors.",
    component: AgentMonitoring,
    group: "Intelligence",
  },
  {
    id: "knowledge",
    label: "Knowledge Base",
    subtitle: "RAG documents stored in Supabase with 384-dim pgvector embeddings.",
    component: KnowledgeBase,
    group: "Intelligence",
  },
  {
    id: "escalations",
    label: "Human Escalation",
    subtitle: "Review low-confidence tickets and issue a human verdict.",
    component: HumanEscalation,
    group: "Human Loop",
  },
];

export default function App() {
  const [activeId, setActiveId] = useState("overview");
  const [health, setHealth] = useState(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
  }, [activeId]);

  const page = PAGES.find((item) => item.id === activeId) || PAGES[0];
  const PageComponent = page.component;

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 32 32" fill="none">
              <path
                d="M7.5 9.5h17A3.5 3.5 0 0 1 28 13v6.5a3.5 3.5 0 0 1-3.5 3.5h-9.1l-4.6 3.4c-.66.49-1.6.02-1.6-.8v-2.7A3.5 3.5 0 0 1 5 19.5V13a3.5 3.5 0 0 1 3.5-3.5Z"
                stroke="#ffffff"
                strokeWidth="2"
                strokeLinejoin="round"
              />
              <circle cx="11.4" cy="16.2" r="1.35" fill="#ffffff" />
              <circle cx="16" cy="16.2" r="1.35" fill="#ffffff" />
              <circle cx="20.6" cy="16.2" r="1.35" fill="#ffffff" />
              <path
                d="M24.9 4.6l1 2.4 2.4 1-2.4 1-1 2.4-1-2.4-2.4-1 2.4-1 1-2.4Z"
                fill="#ffffff"
                opacity="0.95"
              />
            </svg>
          </div>
          <div>
            <div className="brand-name">Support Desk AI</div>
            <div className="brand-sub">CSE476 · Agentic AI</div>
          </div>
        </div>

        <nav>
          {["Operations", "Intelligence", "Human Loop"].map((group) => (
            <div key={group} className="nav-group">
              <div className="nav-group-label">{group}</div>
              {PAGES.filter((item) => item.group === group).map((item) => (
                <button
                  key={item.id}
                  className={`nav-item ${activeId === item.id ? "active" : ""}`}
                  onClick={() => setActiveId(item.id)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="status-line">
            <span className={`status-dot ${health?.database_ok ? "ok" : "warn"}`} />
            {health?.database_ok ? "Database connected" : "Database not configured"}
          </div>
          <div className="status-line">
            <span className={`status-dot ${health?.groq_configured ? "ok" : "warn"}`} />
            {health?.groq_configured ? "Groq ready" : "Groq key missing"}
          </div>
          <div className="sidebar-caption">API · {api.base}</div>
        </div>
      </aside>

      <main className="content">
        <header className="page-head">
          <div>
            <div className="eyebrow">{page.group} console</div>
            <h1>{page.label}</h1>
            <p>{page.subtitle}</p>
          </div>
          <div className="head-badges">
            <span className={`pill ${health?.database_ok ? "ok" : "warn"}`}>
              <span className="pill-dot" /> DB {health?.database_ok ? "online" : "offline"}
            </span>
            <span className={`pill ${health?.groq_configured ? "ok" : "warn"}`}>
              <span className="pill-dot" /> Groq {health?.groq_configured ? "ready" : "offline"}
            </span>
          </div>
        </header>
        <PageComponent onNavigate={setActiveId} />
      </main>
    </div>
  );
}
