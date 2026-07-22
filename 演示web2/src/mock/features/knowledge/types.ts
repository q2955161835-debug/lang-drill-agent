export type KnowledgeDocumentStatus = "queued" | "importing" | "ready" | "failed";

export type KnowledgeDocument = {
  id: string;
  title: string;
  source_name: string;
  mime_type: string;
  raw_path: string;
  parsed_path: string;
  content_hash: string;
  language: string;
  status: KnowledgeDocumentStatus;
  parser: string;
  parser_version: string;
  error_code: string;
  chunk_count: number;
};

export type KnowledgeCitation = {
  document_id: string;
  document_title: string;
  source_name: string;
  heading: string;
  page_start?: number | null;
  page_end?: number | null;
  content_hash: string;
};

export type RetrievedKnowledgeChunk = {
  id: string;
  document_id: string;
  content: string;
  content_hash: string;
  token_count: number;
  score: number;
  citation: KnowledgeCitation;
};

export type KnowledgeSearchResult = {
  mode: "fts" | "hybrid";
  items: RetrievedKnowledgeChunk[];
};
