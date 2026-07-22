export type PastPaperLibrarySource = {
  id: string;
  exam_id: string;
  title: string;
  source_url: string;
  year: number | null;
  session: string;
  set_number: number | null;
  installed: boolean;
};

export type PastPaperLibraryDocument = {
  id: string;
  source_id: string | null;
  exam_id: string;
  title: string;
  year: number | null;
  status: string;
  parser: string;
  raw_path: string;
  markdown_path: string;
  structured_path: string;
  error_code: string;
};

export type PastPaperImportJob = {
  id: string;
  source_id: string;
  title: string;
  status: string;
  stage: string;
  bytes_downloaded: number;
  error_code: string;
};

export type PastPaperLibrarySettings = {
  exam_id: string;
  auto_sync: boolean;
  sync_cadence_hours: number;
  recent_count: number;
  allowed_sources: string[];
  parser: "auto" | "mineru" | "rapidocr" | "text";
  auto_distill: boolean;
  verified_answers_only: boolean;
  long_tail_min_ratio: number;
  max_question_type_ratio: number;
  coverage_window: number;
};

export type PastPaperCatalog = {
  exam_id: string;
  remote_count: number;
  installed_count: number;
  sources: PastPaperLibrarySource[];
  documents: PastPaperLibraryDocument[];
  imports: PastPaperImportJob[];
  settings: PastPaperLibrarySettings;
};

export type RetrievedPastPaperQuestion = {
  id: string;
  document_id: string;
  document_title: string;
  question_type: string;
  prompt: string;
  source_page: number | null;
  verification_status: string;
  correctness_evidence: boolean;
};
