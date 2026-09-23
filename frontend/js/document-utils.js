const ALLOWED_EXTENSIONS = new Set(["pdf", "txt"]);
export const MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024;

export function validateClientFile(file, maxSizeBytes = MAX_UPLOAD_SIZE_BYTES) {
  const extension = file.name.split(".").pop()?.toLowerCase();
  if (!ALLOWED_EXTENSIONS.has(extension)) {
    return "Only PDF and TXT files are supported.";
  }
  if (!file.size) return "The file is empty.";
  if (file.size > maxSizeBytes) return "The file exceeds the 10 MB upload limit.";
  return "";
}

export function formatFileSize(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

export function buildChatDocumentUrl(documentId) {
  return `chat.html?document_id=${encodeURIComponent(documentId)}`;
}

export function requestedDocumentId(search) {
  const value = Number(new URLSearchParams(search).get("document_id"));
  return Number.isInteger(value) && value > 0 ? value : null;
}
