import { useEffect, useState } from "react";
import {
  ArrowClockwise,
  CheckCircle,
  CloudArrowDown,
  MagnifyingGlass,
} from "@phosphor-icons/react";

import { ResourceImportQueue } from "../../components/ResourceImportQueue";
import { pastPaperLibraryApi, type PastPaperLibraryApi } from "./api";
import type {
  PastPaperCatalog,
  PastPaperLibrarySettings,
  RetrievedPastPaperQuestion,
} from "./types";

export function PastPaperLibrary({
  examId,
  api = pastPaperLibraryApi,
}: {
  examId: string;
  api?: PastPaperLibraryApi;
}) {
  const [catalog, setCatalog] = useState<PastPaperCatalog | null>(null);
  const [settings, setSettings] = useState<PastPaperLibrarySettings | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<RetrievedPastPaperQuestion[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const refresh = async () => {
    const payload = await api.catalog(examId);
    setCatalog(payload);
    setSettings(payload.settings);
  };

  useEffect(() => {
    let active = true;
    void api.catalog(examId)
      .then(async (payload) => {
        if (!active) return;
        setCatalog(payload);
        setSettings(payload.settings);
        if (payload.settings.auto_sync && payload.settings.allowed_sources.length) {
          await api.sync(examId, payload.settings.recent_count, false);
          if (!active) return;
          const refreshed = await api.catalog(examId);
          if (!active) return;
          setCatalog(refreshed);
          setSettings(refreshed.settings);
        }
      })
      .catch((error: unknown) => {
        if (active) setMessage(error instanceof Error ? error.message : "真题库加载失败");
      });
    return () => {
      active = false;
    };
  }, [api, examId]);

  const runSync = async () => {
    if (!settings) return;
    setBusy(true);
    setMessage("正在同步真实真题...");
    try {
      await api.sync(examId, settings.recent_count);
      await refresh();
      setMessage("同步任务已完成。可查看导入阶段和本地文档状态。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "真题同步失败");
    } finally {
      setBusy(false);
    }
  };

  const runSearch = async () => {
    if (!settings || !query.trim()) return;
    setBusy(true);
    try {
      const response = await api.search(examId, query.trim(), settings.verified_answers_only);
      setResults(response.items);
      setMessage(response.items.length ? `找到 ${response.items.length} 条题目证据。` : "未找到题目证据。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "真题检索失败");
    } finally {
      setBusy(false);
    }
  };

  const runDistill = async () => {
    if (!catalog) return;
    setBusy(true);
    try {
      const response = await api.distill(examId, catalog.documents.map((item) => item.id));
      setMessage(
        response.status === "ready"
          ? `蒸馏完成，形成 ${response.findings.length} 条有证据结论。`
          : "证据不足，未提升为考试模式结论。",
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "真题蒸馏失败");
    } finally {
      setBusy(false);
    }
  };

  const refreshDocument = async (documentId: string, action: "reparse" | "reindex") => {
    setBusy(true);
    setMessage(action === "reparse" ? "正在重解析可审阅 Markdown..." : "正在重建题目索引...");
    try {
      if (action === "reparse") await api.reparse(documentId);
      else await api.reindex(documentId);
      await refresh();
      setMessage(action === "reparse" ? "文档已按当前 Markdown 重解析。" : "题目索引已重建。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "真题文档操作失败");
    } finally {
      setBusy(false);
    }
  };

  const saveSettings = async () => {
    if (!settings) return;
    setBusy(true);
    try {
      await api.saveSettings(settings);
      setMessage("真题库设置已保存。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "真题库设置保存失败");
    } finally {
      setBusy(false);
    }
  };

  if (!catalog || !settings) {
    return <p className="hint" role="status">{message || "正在加载真题库..."}</p>;
  }

  return (
    <div className="past-paper-library">
      <div className="paper-library-summary" aria-label="真题库数量">
        <strong>本地真题 {catalog.installed_count}</strong>
        <strong>远程目录 {catalog.remote_count}</strong>
        <span>远程目录只代表发现来源，不计入本地真实试卷数量。</span>
      </div>

      <div className="paper-library-actions">
        <button type="button" className="inline-action" disabled={busy} onClick={() => void refresh()}>
          <ArrowClockwise size={16} />刷新状态
        </button>
        <button type="button" className="inline-action primary-inline" disabled={busy || !settings.allowed_sources.length} onClick={() => void runSync()}>
          <CloudArrowDown size={16} />立即同步
        </button>
        <button type="button" className="inline-action" disabled={busy || !catalog.documents.length} onClick={() => void runDistill()}>
          <CheckCircle size={16} />重新蒸馏
        </button>
      </div>

      <ResourceImportQueue
        target="past_paper"
        defaultMetadata={{ exam_id: examId }}
        onConfirmed={() => void refresh()}
      />

      <div className="paper-source-list" aria-label="远程真题目录">
        {catalog.sources.map((source) => (
          <article key={source.id} className="paper-source-card">
            <div>
              <strong>{source.title}</strong>
              <span>{[source.year, source.session, source.set_number ? `第 ${source.set_number} 套` : ""].filter(Boolean).join(" · ")}</span>
            </div>
            <em className={source.installed ? "installed" : "remote-only"}>
              {source.installed ? "已下载" : "尚未下载"}
            </em>
          </article>
        ))}
        {!catalog.sources.length && <p className="hint">暂无可核验远程目录项。</p>}
      </div>

      <div className="paper-document-list" aria-label="本地真题文档">
        {catalog.documents.map((document) => (
          <article key={document.id} className="paper-document-card">
            <div>
              <strong>{document.title}</strong>
              <span>{document.year || "年份未记录"} · {document.status} · {document.parser || "待解析"}</span>
              {document.error_code && <small className="error-text">{document.error_code}</small>}
            </div>
            <div className="paper-document-actions">
              <button type="button" className="inline-action" disabled={busy} onClick={() => void refreshDocument(document.id, "reparse")}>重解析</button>
              <button type="button" className="inline-action" disabled={busy} onClick={() => void refreshDocument(document.id, "reindex")}>重建索引</button>
            </div>
          </article>
        ))}
        {!catalog.documents.length && <p className="hint">暂无本地真实试卷。</p>}
      </div>

      <div className="paper-search-row">
        <input
          aria-label="检索真实真题"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") void runSearch();
          }}
          placeholder="检索题干、题型或知识标签"
        />
        <button type="button" className="inline-action square-action" aria-label="检索真实真题" disabled={busy || !query.trim()} onClick={() => void runSearch()}>
          <MagnifyingGlass size={18} />
        </button>
      </div>

      {results.length > 0 && (
        <div className="paper-search-results" aria-label="真题检索结果">
          {results.map((item) => (
            <article key={item.id}>
              <strong>{item.document_title} · {item.question_type}</strong>
              <span>{item.source_page ? `第 ${item.source_page} 页` : "页码未记录"} · {item.correctness_evidence ? "答案已验证" : "仅风格证据"}</span>
              <p>{item.prompt.slice(0, 240)}</p>
            </article>
          ))}
        </div>
      )}

      <details className="paper-advanced-settings">
        <summary>高级同步设置</summary>
        <div className="paper-library-settings">
          <label>
            <span>允许来源，每行一个 HTTPS（安全网址）</span>
            <textarea
              aria-label="允许真题来源"
              value={settings.allowed_sources.join("\n")}
              onChange={(event) => setSettings({ ...settings, allowed_sources: event.target.value.split(/\n+/).map((item) => item.trim()).filter(Boolean) })}
              placeholder="https://example.edu/past-papers"
            />
          </label>
          <label><span>同步周期（小时）</span><input type="number" min="1" max="720" value={settings.sync_cadence_hours} onChange={(event) => setSettings({ ...settings, sync_cadence_hours: Number(event.target.value) })} /></label>
          <label><span>最近试卷数</span><input type="number" min="1" max="20" value={settings.recent_count} onChange={(event) => setSettings({ ...settings, recent_count: Number(event.target.value) })} /></label>
          <label><span>解析器</span><select value={settings.parser} onChange={(event) => setSettings({ ...settings, parser: event.target.value as PastPaperLibrarySettings["parser"] })}><option value="auto">自动</option><option value="mineru">MinerU（文档解析）</option><option value="rapidocr">RapidOCR（本地文字识别）</option><option value="text">纯文本</option></select></label>
          <label><span>冷门保底比例</span><input type="number" min="0" max="0.5" step="0.05" value={settings.long_tail_min_ratio} onChange={(event) => setSettings({ ...settings, long_tail_min_ratio: Number(event.target.value) })} /></label>
          <label><span>单题型最大比例</span><input type="number" min="0.1" max="1" step="0.05" value={settings.max_question_type_ratio} onChange={(event) => setSettings({ ...settings, max_question_type_ratio: Number(event.target.value) })} /></label>
          <label><span>覆盖窗口</span><input type="number" min="5" max="200" value={settings.coverage_window} onChange={(event) => setSettings({ ...settings, coverage_window: Number(event.target.value) })} /></label>
          <label className="inline-check"><input type="checkbox" checked={settings.auto_sync} onChange={(event) => setSettings({ ...settings, auto_sync: event.target.checked })} />自动同步</label>
          <label className="inline-check"><input type="checkbox" checked={settings.auto_distill} onChange={(event) => setSettings({ ...settings, auto_distill: event.target.checked })} />同步后自动蒸馏</label>
          <label className="inline-check"><input type="checkbox" checked={settings.verified_answers_only} onChange={(event) => setSettings({ ...settings, verified_answers_only: event.target.checked })} />仅使用已验证答案</label>
          <button type="button" className="inline-action primary-inline" disabled={busy} onClick={() => void saveSettings()}>保存真题库设置</button>
        </div>
      </details>

      {catalog.imports.length > 0 && (
        <div className="paper-import-progress" aria-label="真题导入进度">
          {catalog.imports.map((item) => <p key={item.id}>{item.title} · {item.stage} · {item.status}</p>)}
        </div>
      )}
      {message && <p className="hint strong-hint" role="status">{message}</p>}
    </div>
  );
}
