import assert from "node:assert/strict";
import test from "node:test";

import { buildChatRequest, parseEventBlock } from "../js/streaming.js";

test("includes the active conversation in a follow-up streaming request", () => {
  assert.deepEqual(buildChatRequest("Where did she meet him?", [4, 9], 23), {
    question: "Where did she meet him?",
    selected_document_ids: [4, 9],
    conversation_id: 23,
  });
});

test("omits conversation_id for a new chat", () => {
  assert.deepEqual(buildChatRequest("Summarize this.", [4]), {
    question: "Summarize this.",
    selected_document_ids: [4],
  });
});

test("parses a named JSON server-sent event", () => {
  assert.deepEqual(
    parseEventBlock('event: done\ndata: {"conversation_id":23}'),
    { eventType: "done", data: { conversation_id: 23 } },
  );
});
