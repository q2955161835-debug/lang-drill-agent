import { apiPostFile } from "./api";

export type ExtractedFileText = {
  filename: string;
  text: string;
  parser: string;
  size: number;
};

export type PastPaperUploadParams = {
  exam_id: string;
  title: string;
  year?: string;
  source_url?: string;
  summary?: string;
  question_types?: string;
  parse_now?: boolean;
};

export function fileTitle(file: File) {
  return file.name.replace(/\.[^.]+$/, "").trim() || file.name;
}

export function appendImportedText(current: string, addition: string) {
  const cleanCurrent = current.trimEnd();
  const cleanAddition = addition.trim();
  if (!cleanAddition) return current;
  return cleanCurrent ? `${cleanCurrent}\n\n${cleanAddition}` : cleanAddition;
}

export async function extractTextFromFile(file: File, language = "ch") {
  const params = new URLSearchParams({
    filename: file.name,
    language
  });
  return apiPostFile<ExtractedFileText>(`/api/files/extract-text?${params.toString()}`, file);
}

export async function extractTextFromFiles(files: File[], language = "ch") {
  const results = [];
  for (const file of files) {
    results.push(await extractTextFromFile(file, language));
  }
  return {
    results,
    text: results
      .map((result) => result.text.trim())
      .filter(Boolean)
      .join("\n\n"),
  };
}

export async function uploadPastPaperFile<T>(file: File, params: PastPaperUploadParams) {
  const query = new URLSearchParams({
    exam_id: params.exam_id,
    title: params.title,
    filename: file.name,
    source_url: params.source_url || "",
    summary: params.summary || "",
    question_types: params.question_types || "",
    parse_now: String(params.parse_now ?? true),
  });
  if (params.year) query.set("year", params.year);
  return apiPostFile<T>(`/api/past-papers/import-file?${query.toString()}`, file);
}
