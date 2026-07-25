import { apiPostFile } from "./api";

export type ExtractedFileText = {
  filename: string;
  text: string;
  parser: string;
  size: number;
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

export function isImageFile(file: File) {
  return file.type.startsWith("image/")
    || /\.(png|jpe?g|jp2|webp|gif|bmp)$/i.test(file.name);
}

export function fileToDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("图片读取失败。"));
    reader.readAsDataURL(file);
  });
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
