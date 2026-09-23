import { API_BASE_URL, apiRequest, getToken } from "./api.js";
import {
  buildChatDocumentUrl,
  formatFileSize,
  validateClientFile,
} from "./document-utils.js";

const elements = {
  chooseFilesButton: document.querySelector("#choose-files-button"),
  confirmDeleteButton: document.querySelector("#confirm-delete-button"),
  deleteDialog: document.querySelector("#delete-document-dialog"),
  deleteDocumentName: document.querySelector("#delete-document-name"),
  documentTableWrap: document.querySelector("#document-table-wrap"),
  dropZone: document.querySelector("#drop-zone"),
  fileInput: document.querySelector("#document-file-input"),
  notice: document.querySelector("#document-notice"),
  processingCount: document.querySelector("#processing-document-count"),
  readyCount: document.querySelector("#ready-document-count"),
  refreshButton: document.querySelector("#refresh-documents-button"),
  totalChunkCount: document.querySelector("#total-chunk-count"),
  totalCount: document.querySelector("#total-document-count"),
  uploadQueue: document.querySelector("#upload-queue"),
};

const state = {
  documents: [],
  pendingDeleteId: null,
  pollTimer: null,
  uploads: [],
};

function showNotice(text, type = "error") {
  elements.notice.textContent = text;
  elements.notice.dataset.type = text ? type : "";
}

function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "Unknown date";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

function statusLabel(status) {
  return {
    uploaded: "Queued",
    processing: "Processing",
    ready: "Ready",
    failed: "Failed",
  }[status] || status;
}

function updateMetrics() {
  const readyDocuments = state.documents.filter((document) => document.status === "ready");
  const processingDocuments = state.documents.filter((document) => (
    document.status === "uploaded" || document.status === "processing"
  ));
  elements.totalCount.textContent = String(state.documents.length);
  elements.readyCount.textContent = String(readyDocuments.length);
  elements.processingCount.textContent = String(processingDocuments.length);
  elements.totalChunkCount.textContent = String(
    state.documents.reduce((total, document) => total + document.chunk_count, 0),
  );
}

function createDocumentRow(documentRecord) {
  const row = document.createElement("article");
  row.className = "document-row";
  row.dataset.documentId = String(documentRecord.id);

  const identity = document.createElement("div");
  identity.className = "document-identity";
  const fileIcon = document.createElement("span");
  fileIcon.className = `file-type-icon ${documentRecord.file_type}`;
  fileIcon.textContent = documentRecord.file_type.toUpperCase();
  const fileCopy = document.createElement("div");
  const name = document.createElement("strong");
  name.textContent = documentRecord.original_filename;
  const metadata = document.createElement("span");
  metadata.textContent = `${formatFileSize(documentRecord.file_size)} · Added ${formatDate(documentRecord.created_at)}`;
  fileCopy.append(name, metadata);
  identity.append(fileIcon, fileCopy);

  const status = document.createElement("div");
  status.className = `library-status ${documentRecord.status}`;
  const dot = document.createElement("span");
  dot.setAttribute("aria-hidden", "true");
  const statusCopy = document.createElement("div");
  const statusName = document.createElement("strong");
  statusName.textContent = statusLabel(documentRecord.status);
  const statusDetail = document.createElement("small");
  statusDetail.textContent = documentRecord.status === "ready"
    ? `${documentRecord.chunk_count} searchable chunks`
    : documentRecord.status === "failed"
      ? "Processing could not complete"
      : "Preparing document knowledge";
  statusCopy.append(statusName, statusDetail);
  status.append(dot, statusCopy);

  const actions = document.createElement("div");
  actions.className = "document-actions";
  if (documentRecord.status === "ready") {
    const chatLink = document.createElement("a");
    chatLink.className = "document-chat-link";
    chatLink.href = buildChatDocumentUrl(documentRecord.id);
    chatLink.textContent = "Ask in chat";
    actions.append(chatLink);
  }
  const deleteButton = document.createElement("button");
  deleteButton.type = "button";
  deleteButton.className = "document-delete-button";
  deleteButton.dataset.deleteDocument = String(documentRecord.id);
  deleteButton.setAttribute("aria-label", `Delete ${documentRecord.original_filename}`);
  deleteButton.textContent = "Delete";
  actions.append(deleteButton);

  row.append(identity, status, actions);
  return row;
}

function renderDocuments() {
  updateMetrics();
  elements.documentTableWrap.replaceChildren();
  if (!state.documents.length) {
    const empty = document.createElement("div");
    empty.className = "document-library-empty";
    const mark = document.createElement("span");
    mark.textContent = "＋";
    const heading = document.createElement("strong");
    heading.textContent = "Your library is ready for its first source";
    const detail = document.createElement("p");
    detail.textContent = "Upload a PDF or TXT document above to start building searchable knowledge.";
    empty.append(mark, heading, detail);
    elements.documentTableWrap.append(empty);
    return;
  }
  const list = document.createElement("div");
  list.className = "document-rows";
  for (const documentRecord of state.documents) {
    list.append(createDocumentRow(documentRecord));
  }
  elements.documentTableWrap.append(list);
}

function renderUploadQueue() {
  elements.uploadQueue.replaceChildren();
  if (!state.uploads.length) return;
  for (const upload of state.uploads) {
    const row = document.createElement("article");
    row.className = `upload-item ${upload.status}`;
    const copy = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = upload.file.name;
    const detail = document.createElement("span");
    detail.textContent = upload.error || {
      queued: "Waiting to upload",
      uploading: `Uploading · ${upload.progress}%`,
      complete: "Uploaded · Processing started",
      error: "Upload failed",
    }[upload.status];
    copy.append(name, detail);
    const progress = document.createElement("progress");
    progress.max = 100;
    progress.value = upload.progress;
    progress.setAttribute("aria-label", `Upload progress for ${upload.file.name}`);
    row.append(copy, progress);
    elements.uploadQueue.append(row);
  }
}

function uploadFile(file, onProgress) {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    const formData = new FormData();
    formData.append("file", file);
    request.open("POST", `${API_BASE_URL}/documents/upload`);
    request.setRequestHeader("Authorization", `Bearer ${getToken()}`);
    request.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    });
    request.addEventListener("load", () => {
      let response = {};
      try {
        response = JSON.parse(request.responseText || "{}");
      } catch {
        response = {};
      }
      if (request.status === 201) resolve(response);
      else reject(new Error(response.detail || "Upload failed"));
    });
    request.addEventListener("error", () => reject(new Error("The upload connection failed")));
    request.send(formData);
  });
}

async function processFiles(fileList) {
  const additions = [...fileList].map((file, index) => ({
    id: `${Date.now()}-${index}`,
    file,
    progress: 0,
    status: "queued",
    error: validateClientFile(file),
  }));
  for (const upload of additions) {
    if (upload.error) upload.status = "error";
  }
  state.uploads.push(...additions);
  renderUploadQueue();

  for (const upload of additions.filter((item) => !item.error)) {
    upload.status = "uploading";
    renderUploadQueue();
    try {
      await uploadFile(upload.file, (progress) => {
        upload.progress = progress;
        renderUploadQueue();
      });
      upload.status = "complete";
      upload.progress = 100;
    } catch (error) {
      upload.status = "error";
      upload.error = error.message;
    }
    renderUploadQueue();
  }

  elements.fileInput.value = "";
  await loadDocuments();
  const successfulUploads = additions.filter((item) => item.status === "complete").length;
  if (successfulUploads) {
    showNotice(
      `${successfulUploads} document${successfulUploads === 1 ? "" : "s"} uploaded. Processing continues automatically.`,
      "success",
    );
  }
}

function scheduleStatusPolling() {
  window.clearTimeout(state.pollTimer);
  const hasPendingDocuments = state.documents.some((document) => (
    document.status === "uploaded" || document.status === "processing"
  ));
  if (!hasPendingDocuments) return;
  state.pollTimer = window.setTimeout(async () => {
    try {
      await loadDocuments();
    } catch (error) {
      showNotice(error.message);
    }
  }, 2000);
}

async function loadDocuments() {
  state.documents = await apiRequest("/documents");
  renderDocuments();
  scheduleStatusPolling();
}

function openDeleteDialog(documentId) {
  const documentRecord = state.documents.find((document) => document.id === documentId);
  if (!documentRecord) return;
  state.pendingDeleteId = documentId;
  elements.deleteDocumentName.textContent = documentRecord.original_filename;
  elements.deleteDialog.showModal();
}

async function deletePendingDocument() {
  if (!state.pendingDeleteId) return;
  const documentId = state.pendingDeleteId;
  elements.confirmDeleteButton.disabled = true;
  try {
    await apiRequest(`/documents/${documentId}`, { method: "DELETE" });
    state.pendingDeleteId = null;
    elements.deleteDialog.close();
    await loadDocuments();
    showNotice("Document deleted from storage and vector search.", "success");
  } catch (error) {
    showNotice(error.message);
  } finally {
    elements.confirmDeleteButton.disabled = false;
  }
}

elements.chooseFilesButton?.addEventListener("click", (event) => {
  event.stopPropagation();
  elements.fileInput.click();
});
elements.fileInput?.addEventListener("change", () => processFiles(elements.fileInput.files));
elements.dropZone?.addEventListener("click", () => elements.fileInput.click());
elements.dropZone?.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    elements.fileInput.click();
  }
});
for (const eventName of ["dragenter", "dragover"]) {
  elements.dropZone?.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.dropZone.classList.add("drag-active");
  });
}
for (const eventName of ["dragleave", "drop"]) {
  elements.dropZone?.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.dropZone.classList.remove("drag-active");
  });
}
elements.dropZone?.addEventListener("drop", (event) => processFiles(event.dataTransfer.files));
elements.refreshButton?.addEventListener("click", async () => {
  try {
    await loadDocuments();
    showNotice("Document statuses refreshed.", "success");
  } catch (error) {
    showNotice(error.message);
  }
});
elements.documentTableWrap?.addEventListener("click", (event) => {
  const deleteButton = event.target.closest("[data-delete-document]");
  if (deleteButton) openDeleteDialog(Number(deleteButton.dataset.deleteDocument));
});
elements.deleteDialog?.addEventListener("close", () => {
  if (elements.deleteDialog.returnValue === "confirm") deletePendingDocument();
  else state.pendingDeleteId = null;
});
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) loadDocuments().catch((error) => showNotice(error.message));
});

loadDocuments().catch((error) => showNotice(error.message));
