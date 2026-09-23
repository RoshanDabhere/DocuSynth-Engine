import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const chatHtml = await readFile(new URL("../pages/chat.html", import.meta.url), "utf8");
const chatCss = await readFile(new URL("../css/styles.css", import.meta.url), "utf8");

test("chat page exposes every required interactive region", () => {
  for (const id of [
    "new-chat-button",
    "conversation-list",
    "document-list",
    "selected-document-chips",
    "chat-messages",
    "question-input",
    "send-button",
  ]) {
    assert.match(chatHtml, new RegExp(`id=["']${id}["']`));
  }
  assert.match(chatHtml, /href="documents\.html"[^>]*>[\s\S]*Upload document/);
});

test("chat styles include responsive and reduced-motion behavior", () => {
  assert.match(chatCss, /@media \(max-width: 800px\)/);
  assert.match(chatCss, /@media \(prefers-reduced-motion: reduce\)/);
});
