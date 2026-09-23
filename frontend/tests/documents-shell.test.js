import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const documentsHtml = await readFile(new URL("../pages/documents.html", import.meta.url), "utf8");

test("document page exposes upload, status, library, and delete controls", () => {
  for (const id of [
    "drop-zone",
    "document-file-input",
    "upload-queue",
    "document-table-wrap",
    "refresh-documents-button",
    "delete-document-dialog",
    "confirm-delete-button",
  ]) {
    assert.match(documentsHtml, new RegExp(`id=["']${id}["']`));
  }
});

test("file input accepts the supported document formats", () => {
  assert.match(documentsHtml, /accept="[^"]*\.pdf[^"]*\.txt/);
  assert.match(documentsHtml, /\bmultiple\b/);
});
