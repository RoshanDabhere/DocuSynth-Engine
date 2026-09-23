import assert from "node:assert/strict";
import test from "node:test";

import {
  buildChatDocumentUrl,
  formatFileSize,
  requestedDocumentId,
  validateClientFile,
} from "../js/document-utils.js";

test("validates supported extensions, empty files, and upload size", () => {
  assert.equal(validateClientFile({ name: "guide.pdf", size: 42 }), "");
  assert.match(validateClientFile({ name: "notes.docx", size: 42 }), /Only PDF and TXT/);
  assert.match(validateClientFile({ name: "empty.txt", size: 0 }), /empty/);
  assert.match(validateClientFile({ name: "large.pdf", size: 11 * 1024 * 1024 }), /10 MB/);
});

test("formats human-readable file sizes", () => {
  assert.equal(formatFileSize(800), "800 B");
  assert.equal(formatFileSize(1536), "1.5 KB");
  assert.equal(formatFileSize(2 * 1024 * 1024), "2.0 MB");
});

test("hands a ready document to chat through a validated query parameter", () => {
  assert.equal(buildChatDocumentUrl(23), "chat.html?document_id=23");
  assert.equal(requestedDocumentId("?document_id=23"), 23);
  assert.equal(requestedDocumentId("?document_id=invalid"), null);
});
