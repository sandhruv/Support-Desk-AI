import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import {
  Badge,
  ErrorMsg,
  Panel,
  Spinner,
  SuccessMsg,
  Table,
  fmtDate,
} from "../components.jsx";

export default function KnowledgeBase() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [ingestResult, setIngestResult] = useState(null);

  const [uploadFile, setUploadFile] = useState(null);
  const [uploadCategory, setUploadCategory] = useState("");
  const fileInput = useRef(null);

  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(4);
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);

  const loadDocuments = async () => {
    setLoading(true);
    try {
      setDocuments(await api.knowledge());
      setError("");
    } catch (exc) {
      setError(exc.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDocuments();
  }, []);

  const ingest = async () => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api.ingest({ replace: true });
      setIngestResult(result);
      setNotice(
        `Indexed ${result.documents} documents into ${result.chunks} pgvector chunks.`
      );
      await loadDocuments();
    } catch (exc) {
      setError(exc.message);
    } finally {
      setBusy(false);
    }
  };

  const upload = async (event) => {
    event.preventDefault();
    if (!uploadFile) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api.upload(uploadFile, uploadCategory || null);
      setNotice(
        `Uploaded ${uploadFile.name}: ${result.chunks} chunks embedded${
          result.errors?.length ? ` (${result.errors.length} errors)` : ""
        }.`
      );
      setUploadFile(null);
      setUploadCategory("");
      if (fileInput.current) fileInput.current.value = "";
      await loadDocuments();
    } catch (exc) {
      setError(exc.message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (title) => {
    if (!window.confirm(`Delete "${title}" and all of its chunks?`)) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api.deleteKnowledge(title);
      setNotice(`Deleted ${result.deleted_chunks} chunks for "${title}".`);
      await loadDocuments();
    } catch (exc) {
      setError(exc.message);
    } finally {
      setBusy(false);
    }
  };

  const search = async (event) => {
    event.preventDefault();
    if (!query.trim()) return;
    setSearching(true);
    setError("");
    try {
      setResults(await api.search(query.trim(), Number(topK)));
    } catch (exc) {
      setError(exc.message);
    } finally {
      setSearching(false);
    }
  };

  return (
    <div>
      <div className="grid-side">
        <Panel
          title="Indexed Documents"
          subtitle="Stored in Supabase knowledge_documents with all-MiniLM-L6-v2 embeddings"
          actions={
            <button className="btn btn-small" onClick={ingest} disabled={busy}>
              {busy ? "Working…" : "Re-index knowledge_base/"}
            </button>
          }
        >
          <ErrorMsg message={error} />
          <SuccessMsg message={notice} />
          {loading ? (
            <Spinner label="Loading documents…" />
          ) : (
            <Table
              rows={documents}
              columns={[
                { key: "title", label: "Title", render: (row) => <span className="cell-strong">{row.title}</span> },
                { key: "category", label: "Category", render: (row) => <Badge status={row.category || "general"} /> },
                { key: "chunks", label: "Chunks" },
                { key: "embedded", label: "Embedded", render: (row) => (row.embedded ? "Yes" : "No") },
                { key: "created_at", label: "Indexed", render: (row) => <span className="cell-muted">{fmtDate(row.created_at)}</span> },
                {
                  key: "actions",
                  label: "",
                  render: (row) => (
                    <button
                      className="btn btn-danger btn-small"
                      onClick={(event) => {
                        event.stopPropagation();
                        remove(row.title);
                      }}
                      disabled={busy}
                    >
                      Delete
                    </button>
                  ),
                },
              ]}
              empty="No documents indexed. Run ingestion."
            />
          )}
          {ingestResult && (
            <div className="ingest-result" style={{ marginTop: 12 }}>
              Last run: {ingestResult.state} · {ingestResult.documents} docs ·{" "}
              {ingestResult.chunks} chunks
              {ingestResult.errors?.length ? ` · ${ingestResult.errors.length} errors` : ""}
            </div>
          )}
        </Panel>

        <div>
          <Panel title="Upload Document" subtitle="TXT, MD, JSON or PDF — embedded automatically">
            <form onSubmit={upload}>
              <label>File</label>
              <input
                ref={fileInput}
                type="file"
                accept=".txt,.md,.json,.pdf"
                onChange={(event) => setUploadFile(event.target.files?.[0] || null)}
              />
              <div style={{ marginTop: 12 }}>
                <label>Category (optional)</label>
                <input
                  value={uploadCategory}
                  onChange={(event) => setUploadCategory(event.target.value)}
                  placeholder="billing, technical, account…"
                />
              </div>
              <div className="btn-row" style={{ marginTop: 14 }}>
                <button className="btn btn-small" type="submit" disabled={busy || !uploadFile}>
                  {busy ? "Indexing…" : "Upload & index"}
                </button>
              </div>
            </form>
          </Panel>

          <Panel title="Semantic Search" subtitle="Test pgvector retrieval without the LLM">
            <form onSubmit={search}>
              <label>Query</label>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="refund for duplicate charge"
              />
              <div className="filter-row" style={{ marginTop: 12, marginBottom: 0 }}>
                <div>
                  <label>Top K</label>
                  <select value={topK} onChange={(event) => setTopK(event.target.value)}>
                    <option value={2}>2</option>
                    <option value={4}>4</option>
                    <option value={6}>6</option>
                    <option value={10}>10</option>
                  </select>
                </div>
                <div style={{ display: "flex", alignItems: "flex-end" }}>
                  <button className="btn" type="submit" disabled={searching}>
                    {searching ? "Searching…" : "Search"}
                  </button>
                </div>
              </div>
            </form>

            <div style={{ marginTop: 16 }}>
              {results.length === 0 && !searching && (
                <div className="empty">No search run yet.</div>
              )}
              {results.map((result, index) => (
                <div key={index} className="sim-row">
                  <div className="sim-head">
                    <span>
                      {result.title}{" "}
                      {result.category && <Badge status={result.category} />}
                    </span>
                    <span className="cell-muted">
                      {(result.similarity * 100).toFixed(1)}% match
                    </span>
                  </div>
                  <div className="sim-bar">
                    <div
                      className="sim-fill"
                      style={{ width: `${Math.max(4, result.similarity * 100)}%` }}
                    />
                  </div>
                  <div className="sim-content">{result.content}</div>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
