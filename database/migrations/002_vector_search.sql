-- ============================================================
-- 002_vector_search.sql
-- pgvector similarity search used by the RAG pipeline
-- ============================================================

-- HNSW index: works well for small and medium knowledge bases without
-- training data (IVFFlat needs enough rows per list, which breaks on demos).
create index if not exists idx_knowledge_embedding
    on knowledge_documents
    using hnsw (embedding vector_cosine_ops);

-- ------------------------------------------------------------
-- match_knowledge_chunks
-- Returns the most similar knowledge chunks for a query embedding.
--   query_embedding : 384-dim vector generated locally (all-MiniLM-L6-v2)
--   match_threshold : minimum cosine similarity (0..1)
--   match_count     : max rows to return
--   filter_category : optional category filter
-- ------------------------------------------------------------
create or replace function match_knowledge_chunks(
    query_embedding vector(384),
    match_threshold float default 0.0,
    match_count     int   default 5,
    filter_category text  default null
)
returns table (
    id         uuid,
    title      text,
    content    text,
    category   text,
    metadata   jsonb,
    similarity float
)
language sql
stable
as $$
    select
        k.id,
        k.title,
        k.content,
        k.category,
        k.metadata,
        1 - (k.embedding <=> query_embedding) as similarity
    from knowledge_documents k
    where k.embedding is not null
      and (filter_category is null or k.category = filter_category)
      and 1 - (k.embedding <=> query_embedding) >= match_threshold
    order by k.embedding <=> query_embedding
    limit match_count;
$$;

-- ------------------------------------------------------------
-- knowledge_base_stats: quick counts for the dashboard
-- ------------------------------------------------------------
create or replace function knowledge_base_stats()
returns table (documents bigint, chunks bigint, categories bigint)
language sql
stable
as $$
    select count(distinct title), count(*), count(distinct category)
    from knowledge_documents;
$$;
