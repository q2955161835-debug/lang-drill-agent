import { useCallback, useRef, useState } from "react";
import {
  FileArrowUp,
  FolderOpen,
  Sparkle,
  Trash,
  UploadSimple,
} from "@phosphor-icons/react";

import { resourceImportApi, type ResourceImportApi } from "../features/resourceImports/api";
import type {
  QueuedResource,
  ResourceImportMetadata,
  ResourceImportPreview,
  ResourceImportRecord,
  ResourceImportTarget,
} from "../features/resourceImports/types";

const MAX_FILES = 20;

const ALLOWED_EXTENSIONS = [".pdf", ".docx", ".txt", ".md", ".markdown", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"];

const TARGET_LABEL: Record<ResourceImportTarget, string> = {
  knowledge: "知识库文件",
  past_paper: "真题文件",
};

const TARGET_DROP_LABEL: Record<ResourceImportTarget, string> = {
  knowledge: "拖拽或选择知识库文件",
  past_paper: "拖拽或选择真题文件",
};

function fileTitle(file: File) {
  return file.name.replace(/\.[^.]+$/, "").trim() || file.name;
}

function isAllowedFile(file: File) {
  const lower = file.name.toLowerCase();
  return ALLOWED_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

function statusLabel(status: QueuedResource["status"]): string {
  switch (status) {
    case "local":
      return "待解析";
    case "staging":
      return "上传中";
    case "staged":
      return "已暂存";
    case "parsing":
      return "解析中";
    case "preview_ready":
      return "预览就绪";
    case "confirming":
      return "入库中";
    case "confirmed":
      return "已入库";
    case "failed":
      return "失败";
    default:
      return status;
  }
}

function mergeRecord(item: QueuedResource, record: ResourceImportRecord): QueuedResource {
  return {
    ...item,
    remoteId: record.id,
    status: record.status,
    preview: record.preview ?? item.preview,
    error: record.error_code || record.error_detail || item.error,
  };
}

export type ResourceImportQueueProps = {
  target: ResourceImportTarget;
  api?: ResourceImportApi;
  defaultMetadata: ResourceImportMetadata;
  onConfirmed?: () => void | Promise<void>;
};

export function ResourceImportQueue({
  target,
  api = resourceImportApi,
  defaultMetadata,
  onConfirmed,
}: ResourceImportQueueProps) {
  const [items, setItems] = useState<QueuedResource[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [message, setMessage] = useState("");
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const appendFiles = useCallback((files: File[]) => {
    setItems((current) => {
      const remaining = Math.max(0, MAX_FILES - current.length);
      if (remaining <= 0) return current;
      const accepted = files
        .slice(0, remaining)
        .filter(isAllowedFile)
        .map((file) => ({
          localId: crypto.randomUUID(),
          file,
          status: "local" as const,
          metadata: { ...defaultMetadata, title: fileTitle(file) },
        }));
      return accepted.length ? [...current, ...accepted] : current;
    });
  }, [defaultMetadata]);

  const handleDrop = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragActive(false);
    if (!event.dataTransfer.types.includes("Files")) return;
    const files = Array.from(event.dataTransfer.files || []);
    if (files.length) appendFiles(files);
  }, [appendFiles]);

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    if (files.length) appendFiles(files);
    event.target.value = "";
  };

  const updateItem = (localId: string, updater: (item: QueuedResource) => QueuedResource) => {
    setItems((current) => current.map((item) => (item.localId === localId ? updater(item) : item)));
  };

  const removeItem = (localId: string) => {
    setItems((current) => current.filter((item) => item.localId !== localId));
  };

  const cancelRemote = async (item: QueuedResource) => {
    if (item.remoteId) {
      try {
        await api.cancel(item.remoteId);
      } catch {
        // ignore cancel errors; the staging row expires on its own
      }
    }
    removeItem(item.localId);
  };

  const parseOne = async (item: QueuedResource) => {
    setMessage("");
    let working = item;
    try {
      if (!item.remoteId) {
        updateItem(item.localId, (current) => ({ ...current, status: "staging" }));
        const staged = await api.stage(target, item.file);
        working = mergeRecord({ ...item, status: "staged" }, staged);
        updateItem(item.localId, () => working);
      }
      updateItem(item.localId, (current) => ({ ...current, status: "parsing" }));
      const previewed = await api.parse(working.remoteId || item.remoteId || "", item.metadata);
      updateItem(item.localId, (current) => mergeRecord(current, previewed));
    } catch (error) {
      const detail = error instanceof Error ? error.message : "解析失败";
      updateItem(item.localId, (current) => ({ ...current, status: "failed", error: detail }));
      setMessage(detail);
    }
  };

  const confirmOne = async (item: QueuedResource) => {
    if (!item.remoteId || item.status !== "preview_ready") return;
    setMessage("");
    updateItem(item.localId, (current) => ({ ...current, status: "confirming" }));
    try {
      await api.confirm(item.remoteId, item.metadata);
      updateItem(item.localId, (current) => ({ ...current, status: "confirmed" }));
      await onConfirmed?.();
      removeItem(item.localId);
    } catch (error) {
      const detail = error instanceof Error ? error.message : "入库失败";
      updateItem(item.localId, (current) => ({
        ...current,
        status: "preview_ready",
        error: detail,
      }));
      setMessage(detail);
    }
  };

  const parseAll = async () => {
    setMessage("");
    for (const item of items) {
      if (item.status === "local" || item.status === "failed") {
        await parseOne(item);
      }
    }
  };

  return (
    <div className="resource-import-queue">
      <div
        className={`drop-zone resource-import-drop ${dragActive ? "drag-over" : ""}`}
        onDragEnter={(event) => {
          if (event.dataTransfer.types.includes("Files")) setDragActive(true);
        }}
        onDragOver={(event) => {
          if (event.dataTransfer.types.includes("Files")) event.preventDefault();
        }}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
            setDragActive(false);
          }
        }}
        onDrop={handleDrop}
        aria-label={TARGET_DROP_LABEL[target]}
      >
        <FolderOpen size={20} />
        <strong>{TARGET_LABEL[target]}：拖入或点击选择</strong>
        <span>PDF / DOCX / TXT / MD / 图片 · 单文件最大 50 MiB · 最多 {MAX_FILES} 个</span>
        <input
          ref={fileInputRef}
          className="hidden-file-input"
          type="file"
          accept={ALLOWED_EXTENSIONS.join(",")}
          multiple
          onChange={handleFileChange}
        />
        <button
          type="button"
          className="drop-zone-action"
          onClick={() => fileInputRef.current?.click()}
        >
          <UploadSimple size={16} /> 选择文件
        </button>
      </div>

      {items.length > 0 && (
        <div className="resource-import-list" aria-label="资源导入队列">
          {items.map((item) => (
            <article key={item.localId} className="resource-import-item">
              <div className="resource-import-head">
                <FileArrowUp size={18} />
                <strong>{item.file.name}</strong>
                <span>{statusLabel(item.status)}</span>
                <div className="resource-import-actions">
                  {(item.status === "local" || item.status === "failed") && (
                    <button
                      type="button"
                      className="inline-action"
                      onClick={() => void parseOne(item)}
                    >
                      <Sparkle size={16} /> 解析预览
                    </button>
                  )}
                  {item.status === "preview_ready" && (
                    <button
                      type="button"
                      className="inline-action primary-inline"
                      onClick={() => void confirmOne(item)}
                    >
                      <FileArrowUp size={16} /> 确认入库
                    </button>
                  )}
                  <button
                    type="button"
                    className="inline-action"
                    aria-label="移除"
                    onClick={() => void cancelRemote(item)}
                  >
                    <Trash size={16} /> 移除
                  </button>
                </div>
              </div>
              <ResourceImportItemFields
                target={target}
                item={item}
                onChange={(metadata) => updateItem(item.localId, (current) => ({ ...current, metadata }))}
              />
              {item.preview && (
                <ResourceImportPreviewView target={target} preview={item.preview} />
              )}
              {item.error && <p className="error-text">{item.error}</p>}
            </article>
          ))}
          <div className="resource-import-batch-actions">
            <button
              type="button"
              className="inline-action"
              onClick={() => void parseAll()}
              disabled={!items.some((item) => item.status === "local" || item.status === "failed")}
            >
              <Sparkle size={16} /> 批量解析
            </button>
          </div>
        </div>
      )}

      {message && <p className="hint strong-hint" role="status">{message}</p>}
    </div>
  );
}

type ItemFieldsProps = {
  target: ResourceImportTarget;
  item: QueuedResource;
  onChange: (metadata: ResourceImportMetadata) => void;
};

function ResourceImportItemFields({ target, item, onChange }: ItemFieldsProps) {
  const { metadata } = item;
  if (target === "knowledge") {
    return (
      <div className="resource-import-fields">
        <label>
          <span>标题</span>
          <input
            value={metadata.title || ""}
            onChange={(event) => onChange({ ...metadata, title: event.target.value })}
            placeholder="文档标题"
          />
        </label>
        <label>
          <span>语言</span>
          <input
            value={metadata.language || ""}
            onChange={(event) => onChange({ ...metadata, language: event.target.value })}
            placeholder="en / ch / ja ..."
          />
        </label>
      </div>
    );
  }
  return (
    <div className="resource-import-fields">
      <label>
        <span>标题</span>
        <input
          value={metadata.title || ""}
          onChange={(event) => onChange({ ...metadata, title: event.target.value })}
          placeholder="试卷标题"
        />
      </label>
      <label>
        <span>年份</span>
        <input
          value={metadata.year ? String(metadata.year) : ""}
          inputMode="numeric"
          onChange={(event) => {
            const value = event.target.value.trim();
            onChange({ ...metadata, year: value ? Number(value) : null });
          }}
          placeholder="2025"
        />
      </label>
      <label>
        <span>来源 URL</span>
        <input
          value={metadata.source_url || ""}
          onChange={(event) => onChange({ ...metadata, source_url: event.target.value })}
          placeholder="https://example.edu/past-paper.pdf"
        />
      </label>
      <label>
        <span>考试</span>
        <input
          value={metadata.exam_id || ""}
          onChange={(event) => onChange({ ...metadata, exam_id: event.target.value })}
          placeholder="cet4 / cet6 / custom"
        />
      </label>
    </div>
  );
}

type PreviewProps = {
  target: ResourceImportTarget;
  preview: ResourceImportPreview;
};

function ResourceImportPreviewView({ target, preview }: PreviewProps) {
  return (
    <div className="resource-import-preview" aria-label="资源导入预览">
      <div>
        <strong>{preview.title}</strong>
        <span>
          {[preview.parser, `${preview.characters} 字符`].filter(Boolean).join(" · ")}
        </span>
      </div>
      {target === "knowledge" ? (
        <ul>
          <li>切块数：{preview.chunk_count}</li>
          {preview.pages && <li>页数：{preview.pages}</li>}
        </ul>
      ) : (
        <ul>
          <li>题目数：{preview.question_count}</li>
          {preview.question_types.length > 0 && <li>题型：{preview.question_types.join("、")}</li>}
          {preview.answer_confidence > 0 && (
            <li>答案置信度：{(preview.answer_confidence * 100).toFixed(0)}%</li>
          )}
        </ul>
      )}
      {preview.warnings.length > 0 && (
        <ul className="resource-import-warnings">
          {preview.warnings.map((warning, index) => (
            <li key={index}>{warning}</li>
          ))}
        </ul>
      )}
      <p className="resource-import-text-preview">{preview.text_preview}</p>
    </div>
  );
}
