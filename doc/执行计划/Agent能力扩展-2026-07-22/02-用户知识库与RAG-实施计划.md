# 用户知识库与 RAG Implementation Plan

状态：活动计划；实施暂停。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户明确加入的学习文档形成可管理、可引用、可重建的本地知识库，并为聊天、出题、讲解、总结和计划提供混合检索证据。

**Architecture:** 原始文件继续复用现有抽取链路，新增规范化切块、SQLite FTS5 和可选 Embedding 层。检索先做元数据过滤，再并行关键词/向量召回、融合去重并按 Token 预算组装引用。

**Tech Stack:** Python 3.11、SQLite FTS5、Pydantic、FastAPI、httpx、本地/兼容 Embedding Provider、React/Vitest。

## Global Constraints

- 只有用户明确选择“加入知识库”才持久化附件。
- 原始文档和解析结果跟随用户数据目录，不进入安装目录。
- FTS5 必须在没有 Embedding 时可用。
- 文档内容是非可信证据，不能成为系统指令。
- 所有检索结果必须携带来源定位与内容哈希。

---

### Task 1: 知识库 Schema、模型与仓库

**Files:**
- Create: `backend/langdrill_agent/migrations/003_knowledge_base.sql`
- Create: `backend/langdrill_agent/knowledge/__init__.py`
- Create: `backend/langdrill_agent/knowledge/models.py`
- Create: `backend/langdrill_agent/knowledge/repository.py`
- Create: `tests/test_knowledge_repository.py`

**Interfaces:**
- Produces: `KnowledgeDocument`, `KnowledgeChunk`, `DocumentStatus`
- Produces: `KnowledgeRepository.create_document/upsert_chunks/get_document/delete_document`.

- [ ] **Step 1: Write failing repository test**

```python
def test_document_and_chunks_round_trip(db_conn):
    repo = KnowledgeRepository(db_conn)
    doc = repo.create_document(
        title="Unit 1",
        source_name="unit1.pdf",
        mime_type="application/pdf",
        content_hash="sha256:abc",
    )
    repo.upsert_chunks(doc.id, [KnowledgeChunkInput(
        ordinal=0, heading="Vocabulary", page_start=2, page_end=2,
        content="consecutive means following continuously", content_hash="sha256:c1",
    )])
    assert repo.get_document(doc.id).title == "Unit 1"
    assert repo.list_chunks(doc.id)[0].page_start == 2
```

- [ ] **Step 2: Verify failure**

Run: `py -m pytest tests/test_knowledge_repository.py -v`
Expected: FAIL because knowledge package does not exist.

- [ ] **Step 3: Add schema**

```sql
CREATE TABLE knowledge_documents (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  source_name TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  raw_path TEXT NOT NULL DEFAULT '',
  parsed_path TEXT NOT NULL DEFAULT '',
  content_hash TEXT NOT NULL,
  language TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'queued',
  parser TEXT NOT NULL DEFAULT '',
  parser_version TEXT NOT NULL DEFAULT '',
  error_code TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE knowledge_chunks (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  heading TEXT NOT NULL DEFAULT '',
  page_start INTEGER,
  page_end INTEGER,
  content TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  token_count INTEGER NOT NULL DEFAULT 0,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  UNIQUE(document_id, ordinal),
  FOREIGN KEY(document_id) REFERENCES knowledge_documents(id) ON DELETE CASCADE
);

CREATE VIRTUAL TABLE knowledge_chunk_fts USING fts5(
  chunk_id UNINDEXED, document_id UNINDEXED, heading, content,
  tokenize='unicode61 remove_diacritics 2'
);

CREATE TABLE knowledge_embeddings (
  chunk_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  dimensions INTEGER NOT NULL,
  vector_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  PRIMARY KEY(chunk_id, provider, model)
);

CREATE TABLE retrieval_events (
  id TEXT PRIMARY KEY,
  trace_id TEXT NOT NULL DEFAULT '',
  query TEXT NOT NULL,
  filters_json TEXT NOT NULL DEFAULT '{}',
  result_json TEXT NOT NULL DEFAULT '[]',
  injected_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

- [ ] **Step 4: Implement typed repository**

Use explicit column lists and parameter binding. `delete_document` must rely on foreign-key cascade and separately delete corresponding FTS rows in one transaction.

- [ ] **Step 5: Run and commit**

Run: `py -m pytest tests/test_knowledge_repository.py -v`
Expected: PASS.

```powershell
git add backend/langdrill_agent/migrations/003_knowledge_base.sql backend/langdrill_agent/knowledge tests/test_knowledge_repository.py
git commit -m "feat: add knowledge base storage"
```

### Task 2: 文档规范化、切块与可重建导入

**Files:**
- Create: `backend/langdrill_agent/knowledge/chunking.py`
- Create: `backend/langdrill_agent/knowledge/ingestion.py`
- Create: `tests/test_knowledge_chunking.py`
- Modify: `backend/langdrill_agent/data_paths.py`

**Interfaces:**
- Produces: `ChunkingConfig(target_tokens=400, overlap_tokens=80)`
- Produces: `chunk_markdown(text, config) -> list[KnowledgeChunkInput]`
- Produces: `KnowledgeIngestionService.import_file(path, title, language) -> AgentRunRecord`.

- [ ] **Step 1: Write chunking tests**

```python
def test_chunking_preserves_heading_and_page_marker():
    text = "# Unit 1\n<!-- page: 2 -->\n" + ("alpha beta gamma. " * 120)
    chunks = chunk_markdown(text, ChunkingConfig(target_tokens=80, overlap_tokens=10))
    assert len(chunks) > 1
    assert all(chunk.heading == "Unit 1" for chunk in chunks)
    assert chunks[0].page_start == 2
    assert chunks[0].content_hash.startswith("sha256:")


def test_chunking_is_deterministic():
    text = "# A\nOne paragraph.\n\nSecond paragraph."
    assert chunk_markdown(text, ChunkingConfig()) == chunk_markdown(text, ChunkingConfig())
```

- [ ] **Step 2: Verify failure**

Run: `py -m pytest tests/test_knowledge_chunking.py -v`
Expected: FAIL because chunking module does not exist.

- [ ] **Step 3: Implement deterministic chunking**

```python
@dataclass(frozen=True)
class ChunkingConfig:
    target_tokens: int = 400
    overlap_tokens: int = 80


def stable_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
```

Split on Markdown headings and blank paragraphs first; split oversized paragraphs by sentence; apply overlap only within the same heading. Use the existing token estimator instead of adding a tokenizer dependency.

- [ ] **Step 4: Implement ingestion with existing extractors**

`import_file` must copy the source into `<user_data>/knowledge/raw`, call `extract_text_from_file`, write normalized Markdown under `knowledge/parsed`, call `chunk_markdown`, update FTS, and append run events at 10/35/60/90/100 percent. Write into a staging filename and rename only after success.

- [ ] **Step 5: Test path and ingestion failure behavior**

Add a test where extractor raises `RuntimeError`; expected document status is `failed`, original staging file is removed, and run error code is `KNOWLEDGE_EXTRACTION_FAILED`.

- [ ] **Step 6: Run and commit**

Run: `py -m pytest tests/test_knowledge_chunking.py -v`
Expected: PASS.

```powershell
git add backend/langdrill_agent/knowledge backend/langdrill_agent/data_paths.py tests/test_knowledge_chunking.py
git commit -m "feat: ingest and chunk knowledge documents"
```

### Task 3: FTS5 检索与引用

**Files:**
- Create: `backend/langdrill_agent/knowledge/retrieval.py`
- Create: `tests/test_knowledge_retrieval.py`

**Interfaces:**
- Produces: `RetrievalQuery(text, document_ids, top_k, token_budget)`
- Produces: `RetrievedChunk` with `score`, `citation`, and `content_hash`
- Produces: `KnowledgeRetrievalService.search(query) -> list[RetrievedChunk]`.

- [ ] **Step 1: Write exact-term and citation tests**

```python
def test_fts_finds_exact_term_and_returns_page(db_conn, indexed_document):
    results = KnowledgeRetrievalService(db_conn).search(RetrievalQuery(
        text="consecutive", top_k=5, token_budget=500
    ))
    assert results[0].citation.page_start == 2
    assert "consecutive" in results[0].content.lower()


def test_document_filter_prevents_cross_document_results(db_conn, two_documents):
    result = KnowledgeRetrievalService(db_conn).search(RetrievalQuery(
        text="shared", document_ids=[two_documents[0]], top_k=10
    ))
    assert {item.document_id for item in result} == {two_documents[0]}
```

- [ ] **Step 2: Verify failure**

Run: `py -m pytest tests/test_knowledge_retrieval.py -v`
Expected: FAIL because retrieval module does not exist.

- [ ] **Step 3: Implement escaped FTS and token budget**

Build MATCH terms by quoting user tokens; never interpolate raw query into SQL. Convert BM25 to normalized positive score. Stop adding results before the next chunk would exceed `token_budget`, except always allow the first result.

- [ ] **Step 4: Record retrieval event**

Store query, filters, ranked result IDs/scores and final injected IDs; do not store secrets or unrelated context.

- [ ] **Step 5: Run and commit**

Run: `py -m pytest tests/test_knowledge_retrieval.py -v`
Expected: PASS.

```powershell
git add backend/langdrill_agent/knowledge/retrieval.py tests/test_knowledge_retrieval.py
git commit -m "feat: add cited FTS knowledge retrieval"
```

### Task 4: 可选 Embedding 与混合融合

**Files:**
- Create: `backend/langdrill_agent/knowledge/embeddings.py`
- Modify: `backend/langdrill_agent/knowledge/retrieval.py`
- Create: `tests/test_hybrid_retrieval.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: `EmbeddingProvider.embed(texts: list[str]) -> list[list[float]]`
- Produces: `EmbeddingConfig(provider, model, dimensions, enabled)`
- Adds `search_mode: Literal["fts", "hybrid"]` to retrieval response.

- [ ] **Step 1: Write fusion and fallback tests**

```python
def test_reciprocal_rank_fusion_keeps_exact_and_semantic_hits():
    fused = reciprocal_rank_fusion([["exact", "other"], ["semantic", "exact"]], k=60)
    assert fused[0][0] == "exact"
    assert {item[0] for item in fused[:2]} == {"exact", "semantic"}


def test_missing_embedding_provider_returns_fts_results(service):
    result = service.search(RetrievalQuery(text="consecutive", top_k=3))
    assert result.mode == "fts"
    assert result.items
```

- [ ] **Step 2: Verify failure**

Run: `py -m pytest tests/test_hybrid_retrieval.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement provider adapter and index identity**

```python
class EmbeddingProvider(Protocol):
    @property
    def identity(self) -> str: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...
```

Use existing configured provider only when it supports `/embeddings`; local adapter remains optional. Persist provider/model/dimensions/content hash. If identity changes, mark vector status `reindex_required` and continue FTS.

- [ ] **Step 4: Implement RRF and MMR diversity**

Use Reciprocal Rank Fusion for lexical/vector lists and optional MMR after fusion. Default weights live in knowledge settings, not constants scattered through agents.

- [ ] **Step 5: Update `.env.example` without secrets**

Add only placeholder variable names required by a dedicated compatible embedding endpoint; reuse provider settings when possible.

- [ ] **Step 6: Run and commit**

Run: `py -m pytest tests/test_hybrid_retrieval.py -v`
Expected: PASS.

```powershell
git add backend/langdrill_agent/knowledge .env.example tests/test_hybrid_retrieval.py
git commit -m "feat: add optional hybrid knowledge retrieval"
```

### Task 5: 知识库 API 与后台任务

**Files:**
- Create: `backend/langdrill_agent/routers/knowledge.py`
- Modify: `backend/langdrill_agent/api.py`
- Modify: `backend/langdrill_agent/models.py`
- Create: `tests/test_knowledge_api.py`

**Interfaces:**
- `GET /api/knowledge/documents`
- `POST /api/knowledge/import`
- `POST /api/knowledge/search`
- `POST /api/knowledge/reindex`
- `DELETE /api/knowledge/documents/{id}`.

- [ ] **Step 1: Write API contract tests**

```python
def test_import_returns_run_id(client, tmp_path):
    path = tmp_path / "notes.md"
    path.write_text("# Notes\nconsecutive", encoding="utf-8")
    response = client.post("/api/knowledge/import", json={
        "local_path": str(path), "title": "Notes", "language": "en"
    })
    assert response.status_code == 202
    assert response.json()["run_id"].startswith("run_")


def test_search_returns_citations(client, ready_knowledge_doc):
    response = client.post("/api/knowledge/search", json={"query": "consecutive"})
    assert response.json()["items"][0]["citation"]["document_id"] == ready_knowledge_doc
```

- [ ] **Step 2: Verify failure**

Run: `py -m pytest tests/test_knowledge_api.py -v`
Expected: routes missing.

- [ ] **Step 3: Implement request models and router**

Use Pydantic bounds: query 1–2000 chars, top_k 1–50, token_budget 100–20,000. Import accepts a local path only from explicit desktop file selection/upload staging, never arbitrary model-supplied paths.

- [ ] **Step 4: Run and commit**

Run: `py -m pytest tests/test_knowledge_api.py -v`
Expected: PASS.

```powershell
git add backend/langdrill_agent/routers/knowledge.py backend/langdrill_agent/api.py backend/langdrill_agent/models.py tests/test_knowledge_api.py
git commit -m "feat: expose knowledge base API"
```

### Task 6: Prompt 与领域 Agent 接入

**Files:**
- Create: `backend/langdrill_agent/knowledge/context.py`
- Modify: `backend/langdrill_agent/api.py`
- Modify: `backend/langdrill_agent/agents.py`
- Modify: `backend/langdrill_agent/prompt_engine.py`
- Create: `tests/test_knowledge_context_integration.py`

**Interfaces:**
- Produces: `build_knowledge_context(query, task_type, token_budget) -> dict`
- Context key: `context_pack.knowledge_retrieval`.

- [ ] **Step 1: Write prompt-boundary tests**

```python
def test_retrieved_document_is_fenced_as_untrusted(pack):
    block = pack.context_pack["knowledge_retrieval"]
    assert block["trust"] == "untrusted_reference"
    assert block["items"][0]["citation"]["content_hash"]


def test_document_instruction_cannot_enter_system_modules(pack):
    assert all("ignore previous" not in item["content"].lower() for item in pack.system_modules)
```

- [ ] **Step 2: Verify failure**

Run: `py -m pytest tests/test_knowledge_context_integration.py -v`
Expected: missing context key.

- [ ] **Step 3: Implement task-specific retrieval**

General chat uses the user query; Question Author uses `primary_learning_targets`; Evaluator uses question tags plus user error; summary uses explicit user request only. Store citations in model-call metadata and generated `source_refs` without copying long document passages.

- [ ] **Step 4: Run focused agent tests and commit**

Run: `py -m pytest tests/test_knowledge_context_integration.py -v`
Expected: PASS.

```powershell
git add backend/langdrill_agent/knowledge/context.py backend/langdrill_agent/api.py backend/langdrill_agent/agents.py backend/langdrill_agent/prompt_engine.py tests/test_knowledge_context_integration.py
git commit -m "feat: ground learning agents with knowledge retrieval"
```

### Task 7: 知识库设置与管理 UI

**Files:**
- Create: `frontend/src/features/knowledge/types.ts`
- Create: `frontend/src/features/knowledge/api.ts`
- Create: `frontend/src/features/knowledge/KnowledgeSettings.tsx`
- Create: `frontend/src/features/knowledge/KnowledgeSettings.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Produces settings tab with import, status, search test, reindex and delete.
- Consumes Agent Run SSE from plan 01.

- [ ] **Step 1: Write UI test**

```tsx
it("requires explicit confirmation before adding an attachment", async () => {
  render(<KnowledgeSettings api={fakeApi} />);
  await userEvent.click(screen.getByRole("button", { name: "选择文件" }));
  expect(screen.getByRole("button", { name: "加入知识库" })).toBeEnabled();
  expect(fakeApi.importDocument).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Verify failure**

Run: `npm --prefix frontend test -- src/features/knowledge/KnowledgeSettings.test.tsx`
Expected: component missing.

- [ ] **Step 3: Implement focused component**

Render document title, state, parser, chunks, vector state and last error. Search test results show title/page/heading and short excerpt. Destructive delete requires confirmation and explains source file deletion.

- [ ] **Step 4: Wire settings tab without moving unrelated UI**

Add tab ID `knowledge`; keep component mounted while switching settings tabs if it owns an active import run.

- [ ] **Step 5: Run frontend and backend gates**

Run: `npm --prefix frontend test`
Run: `npm --prefix frontend run build`
Expected: PASS.
Run: `py -m pytest -v`
Expected: PASS.

- [ ] **Step 6: Commit and record L3 acceptance**

```powershell
git add frontend/src/features/knowledge frontend/src/App.tsx frontend/src/styles.css
git commit -m "feat: add knowledge base management UI"
```

Update local module and task acceptance documents; verify delete/reindex/import failure and data-path migration manually.
