import { apiGet, apiPost } from "../../api";
import type {
  PastPaperCatalog,
  PastPaperLibrarySettings,
  RetrievedPastPaperQuestion,
} from "./types";

export type PastPaperLibraryApi = {
  catalog(examId: string): Promise<PastPaperCatalog>;
  sync(examId: string, maxDocuments: number, force?: boolean): Promise<unknown>;
  search(examId: string, query: string, verifiedOnly: boolean): Promise<{
    mode: "fts" | "hybrid";
    items: RetrievedPastPaperQuestion[];
  }>;
  distill(examId: string, documentIds: string[]): Promise<{
    status: string;
    findings: unknown[];
  }>;
  reparse(documentId: string): Promise<unknown>;
  reindex(documentId: string): Promise<unknown>;
  saveSettings(settings: PastPaperLibrarySettings): Promise<unknown>;
};

export const pastPaperLibraryApi: PastPaperLibraryApi = {
  catalog(examId) {
    return apiGet(`/api/past-papers/catalog?exam_id=${encodeURIComponent(examId)}`);
  },
  sync(examId, maxDocuments, force = true) {
    return apiPost("/api/past-papers/sync", {
      exam_id: examId,
      max_documents: maxDocuments,
      force,
    });
  },
  search(examId, query, verifiedOnly) {
    return apiPost("/api/past-papers/search", {
      exam_id: examId,
      query,
      top_k: 8,
      verified_answers_only: verifiedOnly,
    });
  },
  distill(examId, documentIds) {
    return apiPost("/api/past-papers/distill", {
      exam_id: examId,
      document_ids: documentIds,
    });
  },
  reparse(documentId) {
    return apiPost("/api/past-papers/reparse", { document_id: documentId });
  },
  reindex(documentId) {
    return apiPost("/api/past-papers/reindex", { document_id: documentId });
  },
  saveSettings(settings) {
    return apiPost("/api/past-papers/settings", settings);
  },
};
