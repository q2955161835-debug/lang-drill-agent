import { apiDelete, apiGet, apiPost, apiPostFile } from "../../api";
import type { KnowledgeDocument, KnowledgeSearchResult } from "./types";

export type KnowledgeApi = {
  listDocuments(): Promise<KnowledgeDocument[]>;
  importDocument(file: File, title: string, language: string): Promise<unknown>;
  search(query: string): Promise<KnowledgeSearchResult>;
  reindex(documentId: string): Promise<unknown>;
  deleteDocument(documentId: string): Promise<{ deleted: boolean }>;
};

export const knowledgeApi: KnowledgeApi = {
  async listDocuments() {
    const response = await apiGet<{ documents: KnowledgeDocument[] }>(
      "/api/knowledge/documents",
    );
    return response.documents;
  },
  importDocument(file, title, language) {
    const params = new URLSearchParams({
      filename: file.name,
      title: title || file.name.replace(/\.[^.]+$/, ""),
      language,
    });
    return apiPostFile(`/api/knowledge/import-file?${params.toString()}`, file);
  },
  search(query) {
    return apiPost<KnowledgeSearchResult>("/api/knowledge/search", {
      query,
      top_k: 8,
      token_budget: 2000,
    });
  },
  reindex(documentId) {
    return apiPost("/api/knowledge/reindex", { document_id: documentId });
  },
  deleteDocument(documentId) {
    return apiDelete(`/api/knowledge/documents/${encodeURIComponent(documentId)}`);
  },
};
