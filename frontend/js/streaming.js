// Pure helpers for the chat streaming request and SSE protocol.

export function buildChatRequest(question, documentIds, conversationId = null, qualityOptions = {}) {
  const request = {
    question,
    selected_document_ids: documentIds,
  };
  if (conversationId) request.conversation_id = conversationId;
  if (qualityOptions.top_k != null) request.top_k = qualityOptions.top_k;
  if (qualityOptions.score_threshold != null) request.score_threshold = qualityOptions.score_threshold;
  return request;
}

export function parseEventBlock(block) {
  let eventType = "message";
  const dataLines = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) eventType = line.slice(6).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  return { eventType, data: JSON.parse(dataLines.join("\n")) };
}
