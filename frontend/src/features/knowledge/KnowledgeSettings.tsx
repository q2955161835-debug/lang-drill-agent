import { useEffect, useState } from "react";
import {
  ArrowClockwise,
  FileArrowUp,
  MagnifyingGlass,
  Trash,
} from "@phosphor-icons/react";

import { knowledgeApi, type KnowledgeApi } from "./api";
import type { KnowledgeDocument, RetrievedKnowledgeChunk } from "./types";

const STATUS_LABELS: Record<KnowledgeDocument["status"], string> = {
  queued: "等待中",
  importing: "处理中",
  ready: "可用",
  failed: "失败",
};

export function KnowledgeSettings({ api = knowledgeApi }: { api?: KnowledgeApi }) {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [language, setLanguage] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<RetrievedKnowledgeChunk[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const refreshDocuments = async () => {
    try {
      setDocuments(await api.listDocuments());
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "知识库加载失败");
    }
  };

  useEffect(() => {
    void api.listDocuments()
      .then(setDocuments)
      .catch((error: unknown) => {
        setMessage(error instanceof Error ? error.message : "知识库加载失败");
      });
  }, [api]);

  const chooseFile = (file: File | null) => {
    setSelectedFile(file);
    if (file && !title.trim()) {
      setTitle(file.name.replace(/\.[^.]+$/, ""));
    }
    setMessage("");
  };

  const importSelected = async () => {
    if (!selectedFile) return;
    setBusy(true);
    setMessage("正在加入知识库...");
    try {
      await api.importDocument(selectedFile, title.trim(), language.trim());
      setSelectedFile(null);
      setTitle("");
      setMessage("文档已加入知识库。");
      await refreshDocuments();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "知识库导入失败");
    } finally {
      setBusy(false);
    }
  };

  const runSearch = async () => {
    const cleanQuery = query.trim();
    if (!cleanQuery) return;
    setBusy(true);
    try {
      const response = await api.search(cleanQuery);
      setResults(response.items);
      setMessage(response.items.length ? `找到 ${response.items.length} 条引用。` : "未找到匹配引用。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "知识库检索失败");
    } finally {
      setBusy(false);
    }
  };

  const reindexDocument = async (documentId: string) => {
    setBusy(true);
    setMessage("正在重建索引...");
    try {
      await api.reindex(documentId);
      setMessage("索引已重建。");
      await refreshDocuments();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "索引重建失败");
    } finally {
      setBusy(false);
    }
  };

  const deleteDocument = async (document: KnowledgeDocument) => {
    if (!window.confirm(`删除“${document.title}”及其本地源文件和索引？`)) return;
    setBusy(true);
    try {
      await api.deleteDocument(document.id);
      setResults((current) => current.filter((item) => item.document_id !== document.id));
      setMessage("文档已删除。");
      await refreshDocuments();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "文档删除失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="knowledge-settings">
      <div className="knowledge-import-row">
        <label className="knowledge-file-picker">
          <FileArrowUp size={18} />
          <span>{selectedFile?.name || "选择文件"}</span>
          <input
            type="file"
            aria-label="选择知识库文件"
            accept=".txt,.md,.markdown,.pdf,.docx,image/*"
            onChange={(event) => chooseFile(event.target.files?.[0] || null)}
          />
        </label>
        <input
          aria-label="文档标题"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="文档标题"
        />
        <input
          aria-label="文档语言"
          value={language}
          onChange={(event) => setLanguage(event.target.value)}
          placeholder="语言，例如 en"
        />
        <button
          type="button"
          className="inline-action primary-inline"
          disabled={!selectedFile || busy}
          onClick={() => void importSelected()}
        >
          <FileArrowUp size={16} />
          加入知识库
        </button>
      </div>

      <div className="knowledge-search-row">
        <input
          aria-label="知识库检索测试"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") void runSearch();
          }}
          placeholder="检索知识库"
        />
        <button
          type="button"
          className="inline-action square-action"
          aria-label="检索知识库"
          title="检索知识库"
          disabled={!query.trim() || busy}
          onClick={() => void runSearch()}
        >
          <MagnifyingGlass size={18} />
        </button>
      </div>

      {message && <p className="hint strong-hint" role="status">{message}</p>}

      {results.length > 0 && (
        <div className="knowledge-results" aria-label="知识库检索结果">
          {results.map((item) => (
            <article key={item.id} className="knowledge-result-item">
              <div>
                <strong>{item.citation.document_title}</strong>
                <span>
                  {[item.citation.heading, item.citation.page_start ? `第 ${item.citation.page_start} 页` : ""]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              </div>
              <p>{item.content.slice(0, 220)}</p>
            </article>
          ))}
        </div>
      )}

      <div className="knowledge-document-list" aria-label="知识库文档">
        {documents.map((document) => (
          <article className="knowledge-document-item" key={document.id}>
            <div className="knowledge-document-main">
              <strong>{document.title}</strong>
              <span>{document.source_name}</span>
              <small>
                {STATUS_LABELS[document.status]} · {document.parser || "待解析"} · {document.chunk_count} 个切块
              </small>
              {document.error_code && <small className="error-text">{document.error_code}</small>}
            </div>
            <div className="knowledge-document-actions">
              <button
                type="button"
                className="icon-button"
                aria-label={`重建 ${document.title}`}
                title="重建索引"
                disabled={busy}
                onClick={() => void reindexDocument(document.id)}
              >
                <ArrowClockwise size={16} />
              </button>
              <button
                type="button"
                className="icon-button"
                aria-label={`删除 ${document.title}`}
                title="删除文档"
                disabled={busy}
                onClick={() => void deleteDocument(document)}
              >
                <Trash size={16} />
              </button>
            </div>
          </article>
        ))}
        {!documents.length && <p className="hint">暂无知识库文档。</p>}
      </div>
    </div>
  );
}
