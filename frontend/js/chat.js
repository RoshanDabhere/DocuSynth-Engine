import { API_BASE_URL, apiRequest, getToken } from "./api.js";
import { requestedDocumentId } from "./document-utils.js";
import { renderMarkdown } from "./markdown.js";
import { buildChatRequest, parseEventBlock } from "./streaming.js";

const elements = {
  chatForm: document.querySelector("#chat-form"),
  conversationCount: document.querySelector("#conversation-count"),
  conversationList: document.querySelector("#conversation-list"),
  conversationTitle: document.querySelector("#conversation-title"),
  documentCount: document.querySelector("#document-count"),
  documentList: document.querySelector("#document-list"),
  messages: document.querySelector("#chat-messages"),
  newChatButton: document.querySelector("#new-chat-button"),
  questionInput: document.querySelector("#question-input"),
  selectedDocumentChips: document.querySelector("#selected-document-chips"),
  sendButton: document.querySelector("#send-button"),
  statusMessage: document.querySelector("#chat-status"),
};

const state = {
  activeConversationId: null,
  conversations: [],
  documents: [],
  isStreaming: false,
  selectedDocumentIds: new Set(),
};

function showStatus(text, type = "error") {
  elements.statusMessage.textContent = text;
  elements.statusMessage.dataset.type = text ? type : "";
}

function scrollMessagesToBottom() {
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

function formatConversationDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
  }).format(date);
}

function renderEmptyConversation() {
  elements.messages.replaceChildren();
  const welcome = document.createElement("div");
  welcome.id = "chat-welcome";
  welcome.className = "chat-welcome";
  welcome.innerHTML = `
    <div class="welcome-mark" aria-hidden="true">D</div>
    <p class="eyebrow">Private document intelligence</p>
    <h2>What would you like to understand?</h2>
    <p>Select one or more ready documents, then ask a question. Every answer stays grounded in your chosen sources.</p>
    <div class="prompt-suggestions" aria-label="Example questions">
      <button type="button" data-suggestion="Summarize the key ideas in these documents.">Summarize the key ideas</button>
      <button type="button" data-suggestion="What are the most important facts I should know?">Find the important facts</button>
      <button type="button" data-suggestion="Compare the main arguments across these documents.">Compare the documents</button>
    </div>`;
  elements.messages.append(welcome);
}

function appendMessage(role, text = "") {
  document.querySelector("#chat-welcome")?.remove();
  const message = document.createElement("article");
  message.className = `chat-message ${role}`;

  const avatar = document.createElement("span");
  avatar.className = "message-avatar";
  avatar.textContent = role === "user" ? "Y" : "D";
  avatar.setAttribute("aria-hidden", "true");

  const content = document.createElement("div");
  content.className = "message-card";
  const label = document.createElement("strong");
  label.className = "message-author";
  label.textContent = role === "user" ? "You" : "DocuSynth";
  const body = document.createElement("div");
  body.className = "message-body";
  if (role === "assistant") {
    renderMarkdown(body, text);
  } else {
    const paragraph = document.createElement("p");
    paragraph.textContent = text;
    body.append(paragraph);
  }
  const sources = document.createElement("div");
  sources.className = "chat-sources";
  content.append(label, body, sources);
  message.append(avatar, content);
  elements.messages.append(message);
  scrollMessagesToBottom();
  return { body, message, sources };
}

function formatScore(score) {
  return `${Math.round(Math.max(0, Math.min(1, score)) * 100)}%`;
}

function deduplicateSources(sources) {
  // Merge chunks from the same document page into one card,
  // keeping the highest relevance score and collecting all text snippets.
  const seen = new Map();
  for (const source of sources) {
    const key = `${source.document_id}:${source.page_number}`;
    if (!seen.has(key)) {
      seen.set(key, { ...source, snippets: [source.text] });
    } else {
      const existing = seen.get(key);
      if (source.score > existing.score) existing.score = source.score;
      if (source.text && !existing.snippets.includes(source.text)) {
        existing.snippets.push(source.text);
      }
    }
  }
  return [...seen.values()];
}

function truncateSnippet(text, maxChars = 260) {
  const clean = (text || "").replace(/\s+/g, " ").trim();
  if (clean.length <= maxChars) return clean;
  return `${clean.slice(0, maxChars).trimEnd()}\u2026`;
}

function renderSources(container, sources, confidence = "none") {
  container.replaceChildren();
  if (!sources || !sources.length) return;

  const deduplicated = deduplicateSources(sources);

  // Header
  const header = document.createElement("div");
  header.className = "sources-header";
  const headerLabel = document.createElement("span");
  headerLabel.className = "sources-label";
  headerLabel.textContent = `Sources \u00b7 ${deduplicated.length}`;

  // Confidence badge
  const confidenceBadge = document.createElement("span");
  confidenceBadge.className = `confidence-badge confidence-${confidence}`;
  const confidenceLabels = {
    high: "\u2714 High Confidence",
    medium: "\u25cf Medium Confidence",
    low: "\u25cb Low Confidence",
    none: "No Match",
  };
  confidenceBadge.textContent = confidenceLabels[confidence] || confidenceLabels.none;

  const headerHint = document.createElement("span");
  headerHint.className = "sources-hint";
  headerHint.textContent = "Click to see evidence";
  header.append(headerLabel, confidenceBadge, headerHint);
  container.append(header);

  const list = document.createElement("div");
  list.className = "source-list";

  deduplicated.forEach((source, index) => {
    const wrapper = document.createElement("div");
    wrapper.className = "source-item-wrap";

    // Card row (always visible)
    const card = document.createElement("div");
    card.className = "source-card-v2";
    card.setAttribute("role", "button");
    card.setAttribute("tabindex", "0");
    card.setAttribute("aria-expanded", "false");
    card.setAttribute(
      "aria-label",
      `Source ${index + 1}: ${source.filename}, page ${source.page_number}. Click to expand evidence.`,
    );

    // Numbered badge
    const badge = document.createElement("span");
    badge.className = "source-badge";
    badge.setAttribute("aria-hidden", "true");
    badge.textContent = String(index + 1);

    // Info block
    const info = document.createElement("div");
    info.className = "source-info";

    const topRow = document.createElement("div");
    topRow.className = "source-top-row";
    const filenameEl = document.createElement("span");
    filenameEl.className = "source-filename";
    filenameEl.textContent = source.filename;
    const pageEl = document.createElement("span");
    pageEl.className = "source-page-badge";
    pageEl.textContent = `p.\u00a0${source.page_number}`;
    topRow.append(filenameEl, pageEl);

    // Relevance score bar
    const scoreRow = document.createElement("div");
    scoreRow.className = "source-score-row";
    const bar = document.createElement("div");
    bar.className = "source-score-bar";
    const fill = document.createElement("div");
    fill.className = "source-score-fill";
    const pct = Math.round(Math.max(0, Math.min(1, source.score)) * 100);
    // Animate on next frame so CSS transition triggers
    requestAnimationFrame(() => requestAnimationFrame(() => {
      fill.style.width = `${pct}%`;
    }));
    bar.append(fill);
    const scoreText = document.createElement("span");
    scoreText.className = "source-score-text";
    scoreText.textContent = `${formatScore(source.score)} match`;
    scoreRow.append(bar, scoreText);

    info.append(topRow, scoreRow);

    // Toggle chevron
    const chevron = document.createElement("span");
    chevron.className = "source-chevron";
    chevron.setAttribute("aria-hidden", "true");
    chevron.textContent = "\u203a";

    card.append(badge, info, chevron);

    // Evidence panel (hidden by default)
    const evidence = document.createElement("div");
    evidence.className = "source-evidence";
    evidence.setAttribute("aria-hidden", "true");

    const snippets = source.snippets || [source.text];
    snippets.forEach((snippet, si) => {
      const p = document.createElement("p");
      p.className = "evidence-text";
      p.textContent = truncateSnippet(snippet);
      evidence.append(p);
      if (si < snippets.length - 1) {
        const sep = document.createElement("div");
        sep.className = "evidence-sep";
        evidence.append(sep);
      }
    });

    function toggleCard() {
      const isOpen = wrapper.classList.toggle("open");
      card.setAttribute("aria-expanded", String(isOpen));
      evidence.setAttribute("aria-hidden", String(!isOpen));
      chevron.style.transform = isOpen ? "rotate(90deg)" : "";
    }
    card.addEventListener("click", toggleCard);
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleCard(); }
    });

    wrapper.append(card, evidence);
    list.append(wrapper);
  });

  container.append(list);
}


function wireCitationBadges(bodyElement, sourcesContainer) {
  // After renderMarkdown, each [Source N] in the answer is a .citation-badge button.
  // Wire clicks so they open the matching source card and scroll it into view.
  const badges = bodyElement.querySelectorAll(".citation-badge[data-source-ref]");
  badges.forEach((badge) => {
    badge.addEventListener("click", () => {
      const n = parseInt(badge.dataset.sourceRef, 10);
      if (!n || n < 1) return;

      // Source cards are the .source-item-wrap elements (1-indexed)
      const wrappers = sourcesContainer.querySelectorAll(".source-item-wrap");
      const target = wrappers[n - 1];
      if (!target) return;

      // Open the card if not already open
      if (!target.classList.contains("open")) {
        target.classList.add("open");
        const card = target.querySelector(".source-card-v2");
        const chevron = target.querySelector(".source-chevron");
        if (card) card.setAttribute("aria-expanded", "true");
        if (chevron) chevron.style.transform = "rotate(90deg)";
      }

      // Briefly highlight then scroll into view
      target.classList.add("citation-highlight");
      target.addEventListener("animationend", () => {
        target.classList.remove("citation-highlight");
      }, { once: true });

      target.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  });
}

function setStreamingState(isStreaming) {
  state.isStreaming = isStreaming;
  elements.sendButton.disabled = isStreaming;
  elements.newChatButton.disabled = isStreaming;
  elements.questionInput.disabled = isStreaming;
  document.querySelectorAll(".conversation-button, .document-choice input").forEach((control) => {
    const unavailableDocument = control.dataset.ready === "false";
    control.disabled = isStreaming || unavailableDocument;
  });
  elements.sendButton.querySelector("span:first-child").textContent = isStreaming ? "Thinking" : "Send";
}

async function streamAnswer(question, documentIds, assistantMessage) {
  const requestBody = buildChatRequest(
    question,
    documentIds,
    state.activeConversationId,
  );

  const response = await fetch(`${API_BASE_URL}/chat/query/stream`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${getToken()}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(requestBody),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || "Streaming request failed");
  }
  if (!response.body) throw new Error("Streaming is unavailable in this browser");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let answer = "";
  let buffer = "";
  let receivedFirstToken = false;
  let confidence = "none";

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      if (block.trim()) {
        const { eventType, data } = parseEventBlock(block);
        if (eventType === "token") {
          if (!receivedFirstToken) {
            assistantMessage.body.replaceChildren();
            assistantMessage.message.classList.remove("waiting");
            receivedFirstToken = true;
          }
          answer += data.token;
          assistantMessage.body.textContent = answer;
          scrollMessagesToBottom();
        } else if (eventType === "sources") {
          confidence = data.confidence || "none";
          renderSources(assistantMessage.sources, data.sources, confidence);
        } else if (eventType === "done") {
          state.activeConversationId = data.conversation_id;
        } else if (eventType === "error") {
          throw new Error(data.detail);
        }
      }
      boundary = buffer.indexOf("\n\n");
    }
    if (done) break;
  }

  assistantMessage.message.classList.remove("waiting");
  renderMarkdown(assistantMessage.body, answer || "No answer was returned.");
  wireCitationBadges(assistantMessage.body, assistantMessage.sources);
}

function renderConversationList() {
  elements.conversationCount.textContent = String(state.conversations.length);
  elements.conversationList.replaceChildren();
  if (!state.conversations.length) {
    const empty = document.createElement("p");
    empty.className = "sidebar-empty";
    empty.textContent = "Your conversations will appear here.";
    elements.conversationList.append(empty);
    return;
  }

  for (const conversation of state.conversations) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "conversation-button";
    button.classList.toggle("active", conversation.id === state.activeConversationId);
    button.dataset.conversationId = String(conversation.id);
    const title = document.createElement("span");
    title.className = "conversation-button-title";
    title.textContent = conversation.title;
    const date = document.createElement("time");
    date.dateTime = conversation.updated_at;
    date.textContent = formatConversationDate(conversation.updated_at);
    button.append(title, date);
    elements.conversationList.append(button);
  }
}

function renderSelectedDocumentChips() {
  elements.selectedDocumentChips.replaceChildren();
  const selectedDocuments = state.documents.filter((document) => (
    state.selectedDocumentIds.has(document.id)
  ));
  if (!selectedDocuments.length) {
    const empty = document.createElement("span");
    empty.className = "empty-chip";
    empty.textContent = "No documents selected";
    elements.selectedDocumentChips.append(empty);
    return;
  }
  for (const documentRecord of selectedDocuments) {
    const chip = document.createElement("span");
    chip.className = "document-chip";
    chip.textContent = documentRecord.original_filename;
    elements.selectedDocumentChips.append(chip);
  }
}

function renderDocumentList() {
  elements.documentCount.textContent = String(state.documents.length);
  elements.documentList.replaceChildren();
  if (!state.documents.length) {
    const empty = document.createElement("p");
    empty.className = "sidebar-empty";
    empty.textContent = "Upload a PDF or TXT file to begin.";
    elements.documentList.append(empty);
    renderSelectedDocumentChips();
    return;
  }

  for (const documentRecord of state.documents) {
    const isReady = documentRecord.status === "ready";
    const choice = document.createElement("label");
    choice.className = "document-choice";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = String(documentRecord.id);
    checkbox.checked = state.selectedDocumentIds.has(documentRecord.id);
    checkbox.disabled = !isReady || state.isStreaming;
    checkbox.dataset.ready = String(isReady);
    const detail = document.createElement("span");
    detail.className = "document-choice-detail";
    const name = document.createElement("strong");
    name.textContent = documentRecord.original_filename;
    const status = document.createElement("span");
    status.className = `document-status ${documentRecord.status}`;
    status.textContent = isReady ? `${documentRecord.chunk_count} chunks · Ready` : documentRecord.status;
    detail.append(name, status);
    choice.append(checkbox, detail);
    elements.documentList.append(choice);
  }
  renderSelectedDocumentChips();
}

async function loadDocuments() {
  const documents = await apiRequest("/documents");
  state.documents = documents;
  const readyDocuments = documents.filter((document) => document.status === "ready");
  const linkedDocumentId = requestedDocumentId(window.location.search);
  const linkedDocumentIsReady = readyDocuments.some(
    (document) => document.id === linkedDocumentId,
  );
  if (linkedDocumentIsReady) {
    state.selectedDocumentIds.add(linkedDocumentId);
  }
  if (!state.selectedDocumentIds.size && readyDocuments.length) {
    state.selectedDocumentIds.add(readyDocuments[0].id);
  }
  renderDocumentList();
  if (!readyDocuments.length) {
    showStatus("Upload and process a document before starting a chat.", "info");
  }
}

async function loadConversations() {
  state.conversations = await apiRequest("/chat/conversations");
  renderConversationList();
}

async function openConversation(conversationId) {
  if (state.isStreaming) return;
  showStatus("Loading conversation…", "info");
  const conversation = await apiRequest(`/chat/conversations/${conversationId}`);
  state.activeConversationId = conversation.id;
  elements.conversationTitle.textContent = conversation.title;
  elements.messages.replaceChildren();
  for (const message of conversation.messages) {
    appendMessage(message.role, message.content);
  }
  if (!conversation.messages.length) renderEmptyConversation();
  renderConversationList();
  showStatus("");
  elements.questionInput.focus();
}

function startNewChat() {
  if (state.isStreaming) return;
  state.activeConversationId = null;
  elements.conversationTitle.textContent = "New conversation";
  renderEmptyConversation();
  renderConversationList();
  showStatus("");
  elements.questionInput.focus();
}

function resizeComposer() {
  elements.questionInput.style.height = "auto";
  elements.questionInput.style.height = `${Math.min(elements.questionInput.scrollHeight, 180)}px`;
}

elements.chatForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = elements.questionInput.value.trim();
  const documentIds = [...state.selectedDocumentIds];
  if (!question || !documentIds.length) {
    showStatus("Enter a question and select at least one ready document.");
    return;
  }

  showStatus("");
  appendMessage("user", question);
  const assistantMessage = appendMessage("assistant");
  assistantMessage.message.classList.add("waiting");
  assistantMessage.body.textContent = "Searching your documents";
  setStreamingState(true);
  elements.questionInput.value = "";
  resizeComposer();

  try {
    await streamAnswer(question, documentIds, assistantMessage);
    await loadConversations();
    const activeConversation = state.conversations.find(
      (conversation) => conversation.id === state.activeConversationId,
    );
    if (activeConversation) elements.conversationTitle.textContent = activeConversation.title;
  } catch (error) {
    assistantMessage.message.classList.remove("waiting");
    if (!assistantMessage.body.textContent.trim()) {
      assistantMessage.body.textContent = "The answer could not be generated.";
    }
    showStatus(error.message);
  } finally {
    setStreamingState(false);
    renderDocumentList();
    elements.questionInput.focus();
  }
});

elements.newChatButton?.addEventListener("click", startNewChat);

elements.conversationList?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-conversation-id]");
  if (!button) return;
  try {
    await openConversation(Number(button.dataset.conversationId));
  } catch (error) {
    showStatus(error.message);
  }
});

elements.documentList?.addEventListener("change", (event) => {
  if (!event.target.matches("input[type='checkbox']")) return;
  const documentId = Number(event.target.value);
  if (event.target.checked) state.selectedDocumentIds.add(documentId);
  else state.selectedDocumentIds.delete(documentId);
  renderSelectedDocumentChips();
  showStatus("");
});

elements.messages?.addEventListener("click", (event) => {
  const suggestion = event.target.closest("[data-suggestion]");
  if (!suggestion) return;
  elements.questionInput.value = suggestion.dataset.suggestion;
  resizeComposer();
  elements.questionInput.focus();
});

elements.questionInput?.addEventListener("input", resizeComposer);
elements.questionInput?.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    elements.chatForm.requestSubmit();
  }
});

async function initializeChat() {
  try {
    await Promise.all([loadDocuments(), loadConversations()]);
  } catch (error) {
    showStatus(error.message);
  }
}

initializeChat();
