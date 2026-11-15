"""PAGE 5 - Knowledge Base: upload, index, delete and test semantic search."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from frontend.utils import (
    ApiError,
    api_delete,
    api_get,
    api_post,
    api_upload,
    empty_state,
    inject_css,
    page_header,
)

inject_css()
page_header("Knowledge Base", "RAG documents stored in Supabase with 384-dim pgvector embeddings.")

try:
    documents = api_get("/knowledge")
except ApiError as exc:
    st.error(str(exc))
    st.stop()

top_left, top_right = st.columns((1, 1))

with top_left:
    st.subheader("Index the built-in knowledge base")
    st.caption("Loads knowledge_base/*.txt from the project, chunks and embeds them locally.")
    if st.button("Run indexing", use_container_width=True):
        try:
            with st.spinner("Chunking and embedding documents (first run downloads the model)..."):
                result = api_post("/knowledge/ingest", {"replace": True})
            st.success(
                f"Indexed {result.get('documents', 0)} documents · "
                f"{result.get('chunks', 0)} chunks"
            )
            if result.get("errors"):
                st.warning(result["errors"])
            st.rerun()
        except ApiError as exc:
            st.error(str(exc))

with top_right:
    st.subheader("Upload a document")
    uploaded = st.file_uploader("TXT, MD, JSON or PDF", type=["txt", "md", "json", "pdf"])
    category = st.selectbox("Category", ["auto", "billing", "technical", "account", "general"])
    if uploaded is not None and st.button("Upload & index", use_container_width=True):
        try:
            with st.spinner("Uploading and indexing..."):
                result = api_upload(
                    "/knowledge/upload",
                    uploaded.name,
                    uploaded.getvalue(),
                    None if category == "auto" else category,
                )
            st.success(f"Indexed {result.get('chunks', 0)} chunks.")
            st.rerun()
        except ApiError as exc:
            st.error(str(exc))

st.divider()
st.subheader("Indexed documents")
if documents:
    df = pd.DataFrame(documents)
    st.dataframe(
        df[["title", "category", "chunks", "embedded", "created_at"]],
        use_container_width=True,
        hide_index=True,
    )
    with st.expander("Delete a document"):
        target = st.selectbox("Document", [doc["title"] for doc in documents])
        confirm = st.checkbox(f"I understand '{target}' and all its chunks will be deleted.")
        if st.button("Delete permanently", disabled=not confirm):
            try:
                result = api_delete(f"/knowledge/{target}")
                st.success(f"Deleted {result.get('deleted_chunks')} chunks.")
                st.rerun()
            except ApiError as exc:
                st.error(str(exc))
else:
    empty_state("No documents indexed yet. Run indexing or upload a file.")

st.divider()
st.subheader("Test semantic search")
query = st.text_input("Search query", placeholder="application crashes on login")
if st.button("Search") and query.strip():
    try:
        with st.spinner("Embedding query and searching pgvector..."):
            results = api_post("/knowledge/search", {"query": query, "top_k": 4})
        if not results:
            st.warning("No relevant chunks found.")
        for item in results:
            st.markdown(
                f"**{item['title']}** · {item['category'] or 'general'} · "
                f"similarity `{item['similarity']:.3f}`"
            )
            st.caption(item["content"][:500])
    except ApiError as exc:
        st.error(str(exc))
