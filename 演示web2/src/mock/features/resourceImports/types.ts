export type ResourceImportTarget = "knowledge" | "past_paper";

export type ResourceImportStatus =
  | "local"
  | "staging"
  | "staged"
  | "parsing"
  | "preview_ready"
  | "confirming"
  | "confirmed"
  | "failed";

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
