# Staged Resource Imports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-file drag/drop imports for knowledge and true papers with parse preview, editable metadata, and explicit confirmation before formal writes.

**Architecture:** A small shared staging service owns temporary files and preview state. Domain adapters parse and confirm knowledge or past-paper records using the existing extraction, chunking, paper parsing, repository, and asset services; the React queue is shared but rendered inside the existing knowledge and true-paper pages.

**Tech Stack:** FastAPI, SQLite, Pydantic, existing MinerU/RapidOCR/pypdf/python-docx chain, React 19, TypeScript, Vitest.

## Global Constraints

- Preserve the current visual style and page locations; do not add an import center.
- Support `.pdf`, `.docx`, `.txt`, `.md`, `.markdown`, and images accepted by `paper_assets.IMAGE_SUFFIXES`.
- Maximum one file is `50 MiB`; the frontend queue accepts at most `20` files.
- Staged files expire after `24 hours`.
- Parse is preview-only; confirm is the only operation that writes formal domain rows or assets.
- A failed file does not block other files in the queue.

## File Structure

- Create `backend/langdrill_agent/resource_imports/models.py`: staging and preview contracts.
- Create `backend/langdrill_agent/resource_imports/repository.py`: SQLite staging persistence.
- Create `backend/langdrill_agent/resource_imports/service.py`: file validation, staging, parsing, confirmation dispatch, cancellation, expiry cleanup.
- Create `backend/langdrill_agent/routers/resource_imports.py`: HTTP endpoints.
- Create `backend/langdrill_agent/migrations/006_resource_import_staging.sql`: staging table and expiry index.
- Modify `backend/langdrill_agent/api.py`: register the new router.
- Modify `backend/langdrill_agent/knowledge/ingestion.py`: confirm a pre-extracted staged document without extracting twice.
- Modify `backend/langdrill_agent/past_papers/ingestion.py`: add local-file confirmation using existing paper parsers and repositories.
- Create `frontend/src/components/ResourceImportQueue.tsx`: shared queue, drag/drop, parse and confirm controls.
- Create `frontend/src/components/ResourceImportQueue.test.tsx`: queue behavior tests.
- Create `frontend/src/features/resourceImports/types.ts`: frontend contracts.
- Create `frontend/src/features/resourceImports/api.ts`: staging API client.
- Modify `frontend/src/features/knowledge/KnowledgeSettings.tsx` and test.
- Modify `frontend/src/features/pastPapers/PastPaperLibrary.tsx`, `api.ts`, `types.ts`, and test.
- Modify `frontend/src/App.tsx`: remove the superseded local true-paper import form under the syllabus tab after the library flow is wired.
- Modify `frontend/src/fileImport.ts`: remove superseded true-paper upload helpers while retaining chat/screenshot extraction helpers.
- Modify `frontend/src/styles.css`: styles using existing border, radius, surface, accent and muted variables.
- Create `tests/test_resource_import_staging.py`.
- Modify `tests/test_knowledge_api.py` and `tests/test_past_papers_api.py`.

---

### Task 1: Persist Safe Staging Records

**Files:**
- Create: `backend/langdrill_agent/migrations/006_resource_import_staging.sql`
- Create: `backend/langdrill_agent/resource_imports/__init__.py`
- Create: `backend/langdrill_agent/resource_imports/models.py`
- Create: `backend/langdrill_agent/resource_imports/repository.py`
- Test: `tests/test_resource_import_staging.py`

**Interfaces:**
- Produces: `ResourceImportRecord`, `ResourceImportPreview`, `ResourceImportRepository.create/get/update/delete/list_expired`.
- Consumes: existing `utils.dumps`, `utils.loads`, `utils.new_id`.

- [ ] **Step 1: Write the migration and repository failure tests**

```python
def test_staging_record_round_trip(db_conn, tmp_path):
    repo = ResourceImportRepository(db_conn)
    record = repo.create(
        target="knowledge",
        filename="notes.md",
        mime_type="text/markdown",
        size_bytes=12,
        staged_path=str(tmp_path / "notes.md"),
    )
    assert repo.get(record.id).status == "staged"
    assert repo.get(record.id).expires_at

def test_expired_records_are_listed(db_conn, tmp_path):
    repo = ResourceImportRepository(db_conn)
    record = repo.create(
        target="past_paper",
        filename="paper.pdf",
        mime_type="application/pdf",
        size_bytes=12,
        staged_path=str(tmp_path / "paper.pdf"),
    )
    db_conn.execute(
        "UPDATE resource_import_staging SET expires_at='2000-01-01T00:00:00' WHERE id=?",
        (record.id,),
    )
    assert [item.id for item in repo.list_expired()] == [record.id]
```

- [ ] **Step 2: Run the focused tests and verify the missing module failure**

Run: `py -m pytest tests/test_resource_import_staging.py -v`

Expected: FAIL during collection with `ModuleNotFoundError: langdrill_agent.resource_imports`.

- [ ] **Step 3: Add the staging schema and exact models**

```sql
CREATE TABLE IF NOT EXISTS resource_import_staging (
  id TEXT PRIMARY KEY,
  target TEXT NOT NULL CHECK(target IN ('knowledge', 'past_paper')),
  filename TEXT NOT NULL,
  mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
  size_bytes INTEGER NOT NULL,
  staged_path TEXT NOT NULL,
  extracted_path TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL CHECK(status IN ('staged', 'parsing', 'preview_ready', 'failed', 'confirmed', 'cancelled')),
  parser TEXT NOT NULL DEFAULT '',
  preview_json TEXT NOT NULL DEFAULT '{}',
  error_code TEXT NOT NULL DEFAULT '',
  error_detail TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_resource_import_expiry
ON resource_import_staging(status, expires_at);
```

```python
ImportTarget = Literal["knowledge", "past_paper"]
ImportStatus = Literal[
    "staged", "parsing", "preview_ready", "failed", "confirmed", "cancelled"
]

class ResourceImportPreview(BaseModel):
    title: str
    language: str = ""
    year: int | None = None
    parser: str
    text_preview: str
    characters: int
    pages: int | None = None
    chunk_count: int = 0
    question_count: int = 0
    question_types: list[str] = Field(default_factory=list)
    answer_confidence: float = 0
    warnings: list[str] = Field(default_factory=list)

class ResourceImportRecord(BaseModel):
    id: str
    target: ImportTarget
    filename: str
    mime_type: str
    size_bytes: int
    staged_path: str
    extracted_path: str = ""
    status: ImportStatus
    parser: str = ""
    preview: ResourceImportPreview | None = None
    error_code: str = ""
    error_detail: str = ""
    created_at: str
    updated_at: str
    expires_at: str
```

- [ ] **Step 4: Implement repository CRUD with a 24-hour expiry**

```python
class ResourceImportRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create(self, *, target: ImportTarget, filename: str, mime_type: str,
               size_bytes: int, staged_path: str,
               record_id: str | None = None) -> ResourceImportRecord:
        now = datetime.now()
        record_id = record_id or new_id("import")
        expires_at = (now + timedelta(hours=24)).isoformat(timespec="seconds")
        self.conn.execute(
            """INSERT INTO resource_import_staging
               (id,target,filename,mime_type,size_bytes,staged_path,status,
                created_at,updated_at,expires_at)
               VALUES (?,?,?,?,?,?,'staged',?,?,?)""",
            (record_id, target, filename, mime_type, size_bytes, staged_path,
             now.isoformat(timespec="seconds"), now.isoformat(timespec="seconds"), expires_at),
        )
        return self.get(record_id)
```

Implement `get`, `update`, `delete`, and `list_expired` using `dumps/loads`; `get` raises `KeyError` for an unknown ID.

- [ ] **Step 5: Run tests and commit**

Run: `py -m pytest tests/test_resource_import_staging.py tests/test_migration_runner.py -v`

Expected: PASS.

```powershell
git add backend/langdrill_agent/migrations/006_resource_import_staging.sql backend/langdrill_agent/resource_imports tests/test_resource_import_staging.py
git commit -m "feat: add resource import staging records"
```

---

### Task 2: Parse Previews Without Formal Writes

**Files:**
- Create: `backend/langdrill_agent/resource_imports/service.py`
- Modify: `tests/test_resource_import_staging.py`

**Interfaces:**
- Consumes: `extract_text_from_file`, `parse_extracted_paper_text`, `chunk_markdown`.
- Produces: `ResourceImportService.stage_bytes`, `parse`, `cancel`, `cleanup_expired`.

- [ ] **Step 1: Add safety and preview tests**

```python
def test_parse_preview_does_not_create_formal_rows(db_conn, tmp_path):
    service = ResourceImportService(db_conn, user_data_dir=tmp_path)
    record = service.stage_bytes(
        target="knowledge", filename="notes.md",
        mime_type="text/markdown", data=b"# Notes\nconsecutive",
    )
    previewed = service.parse(record.id, metadata={"language": "en"})
    assert previewed.status == "preview_ready"
    assert previewed.preview.chunk_count == 1
    assert db_conn.execute("SELECT COUNT(*) FROM knowledge_documents").fetchone()[0] == 0

def test_rejects_oversized_and_unsupported_files(db_conn, tmp_path):
    service = ResourceImportService(db_conn, user_data_dir=tmp_path, max_bytes=4)
    with pytest.raises(ResourceImportError, match="RESOURCE_IMPORT_TOO_LARGE"):
        service.stage_bytes(target="knowledge", filename="notes.md",
                            mime_type="text/markdown", data=b"12345")
    with pytest.raises(ResourceImportError, match="RESOURCE_IMPORT_TYPE_UNSUPPORTED"):
        service.stage_bytes(target="knowledge", filename="../bad.exe",
                            mime_type="application/octet-stream", data=b"x")
```

- [ ] **Step 2: Run tests and verify service import fails**

Run: `py -m pytest tests/test_resource_import_staging.py -v`

Expected: FAIL with missing `ResourceImportService`.

- [ ] **Step 3: Implement validation and staging**

```python
ALLOWED_SUFFIXES = {".pdf", ".docx", ".txt", ".md", ".markdown", *IMAGE_SUFFIXES}

class ResourceImportError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code

def stage_bytes(self, *, target: ImportTarget, filename: str,
                mime_type: str, data: bytes) -> ResourceImportRecord:
    safe_name = Path(filename.replace("\\", "/")).name
    suffix = Path(safe_name).suffix.lower()
    if not safe_name or suffix not in ALLOWED_SUFFIXES:
        raise ResourceImportError("RESOURCE_IMPORT_TYPE_UNSUPPORTED")
    if not data:
        raise ResourceImportError("RESOURCE_IMPORT_EMPTY")
    if len(data) > self.max_bytes:
        raise ResourceImportError("RESOURCE_IMPORT_TOO_LARGE")
    import_id = new_id("import")
    target_dir = self.user_data_dir / "staging" / "resource-imports" / import_id
    target_dir.mkdir(parents=True, exist_ok=False)
    path = target_dir / safe_name
    path.write_bytes(data)
    return self.repository.create(
        target=target, filename=safe_name, mime_type=mime_type,
        size_bytes=len(data), staged_path=str(path), record_id=import_id,
    )
```

- [ ] **Step 4: Implement knowledge and past-paper previews**

```python
def parse(self, import_id: str, *, metadata: dict[str, object]) -> ResourceImportRecord:
    record = self.repository.get(import_id)
    self.repository.update(import_id, status="parsing", error_code="", error_detail="")
    try:
        text, parser = self.extractor(
            Path(record.staged_path),
            language=str(metadata.get("language") or "ch"),
            preferred_parser=str(metadata.get("parser") or "auto"),
        )
        extracted_path = Path(record.staged_path).parent / "extracted.txt"
        extracted_path.write_text(text, encoding="utf-8")
        if record.target == "knowledge":
            chunks = chunk_markdown(text)
            preview = ResourceImportPreview(
                title=str(metadata.get("title") or Path(record.filename).stem),
                language=str(metadata.get("language") or ""),
                parser=parser, text_preview=text[:1200],
                characters=len(text), chunk_count=len(chunks),
            )
        else:
            parsed = parse_extracted_paper_text(
                text,
                exam_id=str(metadata.get("exam_id") or "custom"),
                title=str(metadata.get("title") or Path(record.filename).stem),
                year=_optional_year(metadata.get("year")),
                source_url=str(metadata.get("source_url") or ""),
            )
            preview = ResourceImportPreview(
                title=parsed.title,
                year=_optional_year(metadata.get("year")),
                parser=parser, text_preview=text[:1200],
                characters=len(text), question_count=len(parsed.questions),
                question_types=sorted({q.question_type for q in parsed.questions}),
                answer_confidence=_mean_confidence(parsed.questions),
                warnings=_paper_warnings(parsed),
            )
        return self.repository.update(
            import_id, status="preview_ready", parser=parser,
            extracted_path=str(extracted_path), preview=preview,
        )
    except Exception as exc:
        return self.repository.update(
            import_id, status="failed", error_code="RESOURCE_IMPORT_PARSE_FAILED",
            error_detail=str(exc)[:300],
        )
```

`cancel` sets `cancelled` and removes only the record’s staging directory. `cleanup_expired` iterates `list_expired`, removes those directories, and deletes their rows.

```python
def _optional_year(value: object) -> int | None:
    clean = str(value or "").strip()
    return int(clean) if clean.isdigit() and 1900 <= int(clean) <= 2200 else None

def _mean_confidence(questions: list[ParsedPaperQuestion]) -> float:
    if not questions:
        return 0.0
    return round(sum(item.answer_confidence for item in questions) / len(questions), 4)

def _paper_warnings(parsed: PaperParseResult) -> list[str]:
    warnings: list[str] = []
    if not parsed.questions:
        warnings.append("未识别到结构化题目，请检查抽取文本。")
    if parsed.questions and all(not item.answer for item in parsed.questions):
        warnings.append("未识别到可核验答案，入库后仅作为风格证据。")
    return warnings
```

- [ ] **Step 5: Run tests and commit**

Run: `py -m pytest tests/test_resource_import_staging.py -v`

Expected: PASS, including zero formal rows before confirmation.

```powershell
git add backend/langdrill_agent/resource_imports/service.py tests/test_resource_import_staging.py
git commit -m "feat: parse staged resource previews"
```

---

### Task 3: Confirm Knowledge and Past-Paper Imports

**Files:**
- Modify: `backend/langdrill_agent/knowledge/ingestion.py`
- Modify: `backend/langdrill_agent/past_papers/ingestion.py`
- Modify: `backend/langdrill_agent/resource_imports/service.py`
- Create: `backend/langdrill_agent/routers/resource_imports.py`
- Modify: `backend/langdrill_agent/api.py`
- Modify: `tests/test_resource_import_staging.py`
- Modify: `tests/test_knowledge_api.py`
- Modify: `tests/test_past_papers_api.py`

**Interfaces:**
- Produces: `POST /api/resource-imports/stage`, `POST /{id}/parse`, `POST /{id}/confirm`, `DELETE /{id}`.
- Produces: `KnowledgeIngestionService.import_preparsed` and `PastPaperIngestionService.import_local_file`.

- [ ] **Step 1: Add API tests for explicit confirmation and partial independence**

```python
def test_stage_parse_confirm_knowledge(client):
    staged = client.post(
        "/api/resource-imports/stage?target=knowledge&filename=notes.md",
        content=b"# Notes\nconsecutive",
        headers={"Content-Type": "text/markdown"},
    ).json()["item"]
    assert staged["status"] == "staged"
    assert client.get("/api/knowledge/documents").json()["documents"] == []
    preview = client.post(
        f"/api/resource-imports/{staged['id']}/parse",
        json={"title": "Notes", "language": "en"},
    ).json()["item"]
    assert preview["status"] == "preview_ready"
    assert client.get("/api/knowledge/documents").json()["documents"] == []
    confirmed = client.post(
        f"/api/resource-imports/{staged['id']}/confirm",
        json={"title": "Edited Notes", "language": "en", "confirmed": True},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["document"]["title"] == "Edited Notes"

def test_confirm_requires_true(client):
    response = client.post(
        "/api/resource-imports/import_missing/confirm",
        json={"confirmed": False},
    )
    assert response.status_code == 400
```

- [ ] **Step 2: Run API tests and verify 404 endpoint failures**

Run: `py -m pytest tests/test_resource_import_staging.py tests/test_knowledge_api.py tests/test_past_papers_api.py -v`

Expected: FAIL with `404 Not Found` for `/api/resource-imports`.

- [ ] **Step 3: Add domain confirmation methods**

```python
def import_preparsed(self, path: Path, *, extracted_text: str, parser: str,
                     title: str, language: str = "") -> AgentRunRecord:
    return self._persist_import(
        source=path.resolve(), extracted_text=extracted_text, parser=parser,
        title=title, language=language, document_id=None,
    )
```

Refactor `KnowledgeIngestionService.import_file` to extract once and call `_persist_import`; keep its public response and rollback behavior unchanged.

```python
def import_local_file(self, path: Path, *, exam_id: str, title: str,
                      year: int | None, source_url: str, extracted_text: str,
                      parser: str) -> PaperDocument:
    parsed = parse_extracted_paper_text(
        extracted_text, exam_id=exam_id, title=title,
        year=year, source_url=source_url,
    )
    asset_id = new_id("paperasset")
    dirs = ensure_exam_paper_dirs(exam_id)
    raw_path = dirs["raw"] / f"{asset_id}{path.suffix.lower() or '.bin'}"
    markdown_path = dirs["parsed"] / f"{asset_id}.md"
    structured_path = dirs["structured"] / f"{asset_id}.json"
    _atomic_copy(path, raw_path)
    _atomic_write(markdown_path, render_paper_markdown(parsed))
    _atomic_write(structured_path, dumps(parsed.model_dump(mode="json")))
    document = self.repository.create_document(
        PaperDocumentInput(
            exam_id=exam_id, title=title, year=year,
            source_url=source_url, raw_path=str(raw_path),
            markdown_path=str(markdown_path), structured_path=str(structured_path),
            content_hash=_file_hash(raw_path), status="ready",
            parser=parser, parser_version="2",
        )
    )
    self.repository.replace_questions(
        document.id,
        [PaperQuestionInput(**question.model_dump()) for question in parsed.questions],
    )
    return self.repository.get_document(document.id)
```

The implementation must use existing `PastPaperRepository.create_document` and `replace_questions`; a local paper uses an empty `source_id` and the user-provided source URL.

`_atomic_copy` copies to the destination with a `.staging` suffix and uses `Path.replace`; `_atomic_write` writes UTF-8 to the same staging suffix and replaces only after a successful write. On any exception, delete the three files created for `asset_id` before re-raising.

- [ ] **Step 4: Add confirmed dispatch and router**

```python
class ParseRequest(BaseModel):
    title: str = ""
    language: str = ""
    exam_id: str = ""
    year: int | None = None
    source_url: str = ""
    parser: Literal["auto", "mineru", "rapidocr", "text"] = "auto"

class ConfirmRequest(ParseRequest):
    confirmed: bool

@router.post("/stage", status_code=202)
async def stage(request: Request, target: ImportTarget, filename: str) -> dict:
    with transaction() as conn:
        item = ResourceImportService(conn).stage_bytes(
            target=target, filename=filename,
            mime_type=request.headers.get("content-type", "application/octet-stream"),
            data=await request.body(),
        )
    return {"item": item.model_dump(mode="json")}

@router.post("/{import_id}/confirm")
def confirm(import_id: str, request: ConfirmRequest) -> dict:
    if not request.confirmed:
        raise HTTPException(400, detail={"code": "RESOURCE_IMPORT_CONFIRMATION_REQUIRED"})
    with transaction() as conn:
        return ResourceImportService(conn).confirm(
            import_id, metadata=request.model_dump(exclude={"confirmed"}),
        )
```

```python
def confirm(self, import_id: str, *, metadata: dict[str, object]) -> dict[str, object]:
    record = self.repository.get(import_id)
    if record.status != "preview_ready" or not record.extracted_path:
        raise ResourceImportError("RESOURCE_IMPORT_PREVIEW_REQUIRED")
    source = Path(record.staged_path)
    extracted_text = Path(record.extracted_path).read_text(encoding="utf-8")
    if record.target == "knowledge":
        run = KnowledgeIngestionService(self.conn).import_preparsed(
            source, extracted_text=extracted_text, parser=record.parser,
            title=str(metadata.get("title") or record.preview.title),
            language=str(metadata.get("language") or record.preview.language),
        )
        document = KnowledgeRepository(self.conn).list_documents()[-1]
        result: dict[str, object] = {
            "run": run.model_dump(mode="json"),
            "document": document.model_dump(mode="json"),
        }
    else:
        document = PastPaperIngestionService(
            self.conn, papers_root=paper_root(),
        ).import_local_file(
            source, extracted_text=extracted_text, parser=record.parser,
            exam_id=str(metadata.get("exam_id") or "custom"),
            title=str(metadata.get("title") or record.preview.title),
            year=_optional_year(metadata.get("year")),
            source_url=str(metadata.get("source_url") or ""),
        )
        result = {"document": document.model_dump(mode="json")}
    self.repository.update(import_id, status="confirmed")
    shutil.rmtree(source.parent, ignore_errors=True)
    return result
```

Map unknown IDs to 404, invalid state to 409, validation to 400, and unexpected parse failure to a sanitized error detail. Register the router in `api.py`.

- [ ] **Step 5: Run regression tests and commit**

Run: `py -m pytest tests/test_resource_import_staging.py tests/test_knowledge_api.py tests/test_past_papers_api.py tests/test_past_paper_ingestion.py -v`

Expected: PASS.

```powershell
git add backend/langdrill_agent/api.py backend/langdrill_agent/routers/resource_imports.py backend/langdrill_agent/resource_imports/service.py backend/langdrill_agent/knowledge/ingestion.py backend/langdrill_agent/past_papers/ingestion.py tests/test_resource_import_staging.py tests/test_knowledge_api.py tests/test_past_papers_api.py
git commit -m "feat: confirm staged knowledge and paper imports"
```

---

### Task 4: Add the Shared React Queue to Existing Pages

**Files:**
- Create: `frontend/src/features/resourceImports/types.ts`
- Create: `frontend/src/features/resourceImports/api.ts`
- Create: `frontend/src/components/ResourceImportQueue.tsx`
- Create: `frontend/src/components/ResourceImportQueue.test.tsx`
- Modify: `frontend/src/features/knowledge/KnowledgeSettings.tsx`
- Modify: `frontend/src/features/knowledge/KnowledgeSettings.test.tsx`
- Modify: `frontend/src/features/pastPapers/PastPaperLibrary.tsx`
- Modify: `frontend/src/features/pastPapers/api.ts`
- Modify: `frontend/src/features/pastPapers/types.ts`
- Modify: `frontend/src/features/pastPapers/PastPaperLibrary.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/fileImport.ts`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: the resource import HTTP contract from Task 3.
- Produces: reusable `ResourceImportQueue({ target, defaultMetadata, onConfirmed })`.

- [ ] **Step 1: Write queue and page integration tests**

```tsx
it("keeps dropped files local until parse is clicked", () => {
  const api = createResourceImportApi();
  render(<ResourceImportQueue target="knowledge" api={api} defaultMetadata={{ language: "en" }} />);
  const file = new File(["notes"], "notes.md", { type: "text/markdown" });
  fireEvent.drop(screen.getByLabelText("拖拽或选择知识库文件"), {
    dataTransfer: { files: [file], types: ["Files"] },
  });
  expect(screen.getByText("notes.md")).toBeTruthy();
  expect(api.stage).not.toHaveBeenCalled();
});

it("parses before enabling confirmation", async () => {
  const api = createResourceImportApi();
  render(<ResourceImportQueue target="past_paper" api={api}
          defaultMetadata={{ exam_id: "cet4" }} />);
  // Select one file, click 解析, wait for preview.
  expect((await screen.findByRole("button", { name: "确认入库" }) as HTMLButtonElement).disabled)
    .toBe(false);
});
```

Update the existing knowledge and past-paper tests to assert `ResourceImportQueue` labels are visible inside their existing page containers.

- [ ] **Step 2: Run Vitest and verify missing component failures**

Run: `npm test -- --run src/components/ResourceImportQueue.test.tsx src/features/knowledge/KnowledgeSettings.test.tsx src/features/pastPapers/PastPaperLibrary.test.tsx`

Working directory: `frontend`

Expected: FAIL with missing `ResourceImportQueue`.

- [ ] **Step 3: Define frontend contracts and API**

```ts
export type ResourceImportTarget = "knowledge" | "past_paper";
export type ResourceImportStatus =
  | "local" | "staging" | "staged" | "parsing"
  | "preview_ready" | "confirming" | "confirmed" | "failed";

export type ResourceImportPreview = {
  title: string;
  language: string;
  year: number | null;
  parser: string;
  text_preview: string;
  characters: number;
  pages: number | null;
  chunk_count: number;
  question_count: number;
  question_types: string[];
  answer_confidence: number;
  warnings: string[];
};

export type ResourceImportMetadata = {
  title?: string;
  language?: string;
  exam_id?: string;
  year?: number | null;
  source_url?: string;
  parser?: "auto" | "mineru" | "rapidocr" | "text";
};

export type ResourceImportRecord = {
  id: string;
  target: ResourceImportTarget;
  filename: string;
  status: Exclude<ResourceImportStatus, "local" | "staging" | "confirming">;
  preview: ResourceImportPreview | null;
  error_code: string;
  error_detail: string;
};

export type QueuedResource = {
  localId: string;
  file: File;
  status: ResourceImportStatus;
  remoteId?: string;
  metadata: ResourceImportMetadata;
  preview?: ResourceImportPreview;
  error?: string;
};
```

```ts
export type ResourceImportApi = {
  stage(target: ResourceImportTarget, file: File): Promise<ResourceImportRecord>;
  parse(id: string, metadata: ResourceImportMetadata): Promise<ResourceImportRecord>;
  confirm(id: string, metadata: ResourceImportMetadata): Promise<unknown>;
  cancel(id: string): Promise<void>;
};

export type ResourceImportQueueProps = {
  target: ResourceImportTarget;
  api?: ResourceImportApi;
  defaultMetadata: ResourceImportMetadata;
  onConfirmed?: () => void | Promise<void>;
};
```

- [ ] **Step 4: Implement queue state and existing-style markup**

```tsx
export function ResourceImportQueue({
  target, api = resourceImportApi, defaultMetadata, onConfirmed,
}: ResourceImportQueueProps) {
  const [items, setItems] = useState<QueuedResource[]>([]);
  const appendFiles = (files: File[]) => {
    setItems(current => [
      ...current,
      ...files.slice(0, Math.max(0, 20 - current.length)).map(file => ({
        localId: crypto.randomUUID(), file, status: "local" as const,
        metadata: { ...defaultMetadata, title: fileTitle(file) },
      })),
    ]);
  };
  // Drop/select only calls appendFiles. parseOne performs stage then parse.
  // confirmOne sends confirmed=true and removes only the successful item.
}
```

Render per-file metadata fields and domain preview:

- Knowledge: title, language, characters, chunk count, text preview, warnings.
- Past paper: title, year, source URL, question types, question count, answer confidence, text preview, warnings.

Use existing classes such as `drop-zone`, `inline-action`, `primary-inline`, `hint`, and `error-text`, plus focused `.resource-import-*` classes backed by existing CSS variables.

- [ ] **Step 5: Integrate pages, remove duplicate old upload, run and commit**

Place the queue in `KnowledgeSettings` above search and in `PastPaperLibrary` below the summary/actions. Keep remote sync, local catalog, search, distillation and settings. Wrap low-frequency true-paper source and coverage settings in a native `<details>` labelled `高级同步设置`.

After the new true-paper queue passes tests, delete only the superseded local import form/state/handlers from `App.tsx` and remove `uploadPastPaperFile`/`uploadPastPaperDraftFile` from `fileImport.ts`; retain question-type selection and legacy data display until a later migration explicitly replaces them.

Run:

```powershell
Set-Location frontend
npm test -- --run src/components/ResourceImportQueue.test.tsx src/features/knowledge/KnowledgeSettings.test.tsx src/features/pastPapers/PastPaperLibrary.test.tsx
npm run build
```

Expected: all selected tests PASS and TypeScript/Vite build exits 0.

```powershell
git add frontend/src/components/ResourceImportQueue.tsx frontend/src/components/ResourceImportQueue.test.tsx frontend/src/features/resourceImports frontend/src/features/knowledge frontend/src/features/pastPapers frontend/src/App.tsx frontend/src/fileImport.ts frontend/src/styles.css
git commit -m "feat: add staged drag drop imports to resource pages"
```
