const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function request(path, { method = "GET", body, file, params } = {}) {
  const url = new URL(BASE + path);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, value);
      }
    });
  }

  const options = { method, headers: {} };
  if (file) {
    const form = new FormData();
    form.append("file", file);
    options.body = form;
  } else if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(url, options);
  } catch {
    throw new Error(
      `Cannot reach the FastAPI backend at ${BASE}. Start it with: python run.py api`
    );
  }

  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!response.ok) {
    const detail = data?.detail ?? data;
    const message =
      typeof detail === "string"
        ? detail
        : detail?.message || JSON.stringify(detail) || `Request failed (${response.status})`;
    throw new Error(message);
  }
  return data;
}

export const api = {
  base: BASE,
  health: () => request("/health"),
  stats: () => request("/dashboard/stats"),

  tickets: (params) => request("/tickets", { params }),
  ticket: (id) => request(`/tickets/${id}`),
  createTicket: (payload) => request("/tickets", { method: "POST", body: payload }),
  processTicket: (id) => request(`/tickets/${id}/process`, { method: "POST" }),
  conversation: (id) => request(`/tickets/${id}/conversation`),
  addMessage: (id, message) =>
    request(`/tickets/${id}/messages`, { method: "POST", body: { message } }),

  agents: () => request("/agents"),
  logs: (params) => request("/agents/logs", { params }),

  knowledge: () => request("/knowledge"),
  ingest: (body = { replace: true }) =>
    request("/knowledge/ingest", { method: "POST", body }),
  upload: (file, category) =>
    request("/knowledge/upload", {
      method: "POST",
      file,
      params: category ? { category } : undefined,
    }),
  deleteKnowledge: (title) =>
    request(`/knowledge/${encodeURIComponent(title)}`, { method: "DELETE" }),
  search: (query, top_k = 4) =>
    request("/knowledge/search", { method: "POST", body: { query, top_k } }),

  escalations: (params) => request("/escalations", { params }),
  verdict: (id, body) =>
    request(`/escalations/${id}/verdict`, { method: "POST", body }),
};
