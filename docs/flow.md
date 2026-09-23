# DocuSynth Engine — Complete Data Flow

> **What this document covers**: Every data transformation in DocuSynth Engine,
> from the moment a user uploads a file to when a streamed answer appears on screen.
> Each step shows which file handles the work, what goes in, and what comes out.

---

## Table of Contents

1. [Authentication Flow](#1-authentication-flow)
2. [Document Upload & Ingestion Flow](#2-document-upload--ingestion-flow)
3. [Question-Answering RAG Flow — Non-Streaming](#3-question-answering-rag-flow--non-streaming)
4. [Question-Answering RAG Flow — Streaming SSE](#4-question-answering-rag-flow--streaming-sse)
5. [Conversation Memory Flow](#5-conversation-memory-flow)
6. [Document Deletion Flow](#6-document-deletion-flow)
7. [Complete RAG Internal Pipeline Deep Dive](#7-complete-rag-internal-pipeline-deep-dive)
8. [Security Invariants](#8-security-invariants)

---

## 1. Authentication Flow

### 1.1 Registration

```
Browser (register.html)
    |
    |  POST /auth/register
    |  Body: { name, email, password }
    v
app/api/routes/auth.py  register_user()
    |
    |  1. Normalize email to lowercase
    |  2. Query PostgreSQL check if email already exists
    |  3. If exists raise HTTP 409 Conflict
    |
    v
app/security/authentication.py  hash_password()
    |
    |  Input  : "mysecretpassword" (plaintext)
    |  Process: bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    |  Output : "$2b$12$..." (60-char bcrypt hash)
    |
    v
PostgreSQL  users table
    |
    |  INSERT: id, name, email, hashed_password, is_active=True,
    |          created_at, updated_at
    |
    v
HTTP 201 Created
    Body: { id, name, email, is_active, created_at, updated_at }
    |
    v
Browser  redirect to login.html?registered=1
```

### 1.2 Login

```
Browser (login.html)
    |
    |  POST /auth/login
    |  Body: { email, password }
    v
app/api/routes/auth.py  login()
    |
    |  1. Normalize email to lowercase
    |  2. Query PostgreSQL  find user by email
    |  3. If not found or not active  HTTP 401
    |
    v
app/security/authentication.py  verify_password()
    |
    |  Input  : "mysecretpassword" + "$2b$12$..." (stored hash)
    |  Process: bcrypt.checkpw(password.encode, hash.encode)
    |  Output : True / False   If False HTTP 401
    |
    v
app/security/authentication.py  create_access_token(user.id)
    |
    |  Payload: { sub: "42", exp: <now + 30min>, type: "access" }
    |  Signed with: HS256 + JWT_SECRET_KEY
    |  Output : "eyJhbGci..." (JWT string)
    |
    v
HTTP 200 OK
    Body: { access_token: "eyJ...", token_type: "bearer" }
    |
    v
Browser  sessionStorage.setItem("docusynth_access_token", token)
         redirect to dashboard.html
```

### 1.3 Protected Route Verification (every API call)

```
Browser
    |
    |  Request Header: Authorization: Bearer eyJ...
    v
app/api/dependencies.py  get_current_user()
    |
    |  1. Extract token from Authorization header (OAuth2PasswordBearer)
    |  2. Call decode_access_token(token)
    |     jwt.decode() validates signature + expiry
    |     Extract user_id from payload["sub"]
    |  3. Query PostgreSQL  User.get(user_id)
    |  4. If user None or not active  HTTP 401
    |
    v
Returns: User ORM object (injected into every protected endpoint)
```

---

## 2. Document Upload & Ingestion Flow

### 2.1 Upload Phase (Synchronous — returns immediately)

```
Browser (documents.html)
    |
    |  POST /documents/upload
    |  Content-Type: multipart/form-data
    |  Body: file=<binary>
    |  Header: Authorization: Bearer eyJ...
    v
app/api/routes/documents.py  upload_document()
    |
    +-- STEP 1: Metadata Validation
    |   app/utils/validators.py  validate_upload_metadata(filename, content_type)
    |   - Checks: filename not None, extension in {.pdf, .txt}
    |   - Checks: MIME type matches extension
    |   - Returns: (safe_filename, extension)
    |
    +-- STEP 2: Magic Bytes Validation
    |   await file.read(1 MB)  first_chunk
    |   app/utils/validators.py  validate_file_header(extension, first_chunk)
    |   - PDF: first_chunk must start with b"%PDF-"
    |   - TXT: first_chunk must not contain b"\x00"
    |
    +-- STEP 3: Safe Filename Generation
    |   app/utils/file_utils.py  create_stored_filename(extension)
    |   - Output: "a3f9d2b1-uuid4-string.pdf" (never trusts original name)
    |
    +-- STEP 4: Streaming Disk Write
    |   aiofiles.open(stored_path, "wb")
    |   - Read in 1 MB chunks
    |   - Track cumulative size
    |   - Reject if size > MAX_UPLOAD_SIZE_BYTES (10 MB)
    |
    +-- STEP 5: Database Record Creation
    |   PostgreSQL  documents table
    |   - INSERT: user_id, original_filename, stored_filename,
    |             file_type, file_size, status="uploaded"
    |
    +-- STEP 6: Background Task Scheduling
        FastAPI BackgroundTasks.add_task(process_document, document.id)
        - Returns HTTP 201 immediately
        - Processing continues in background thread

HTTP 201 Created
    Body: { id, original_filename, status: "uploaded", ... }
```

### 2.2 Ingestion Pipeline (Background — LangGraph workflow)

```
FastAPI Background Thread
    |
    |  process_document(document_id)
    v
app/ingestion/pipeline.py  process_document()
    |
    |  1. Load document from PostgreSQL
    |  2. Set status = "processing"
    |  3. Commit to DB
    |
    v
INGESTION_GRAPH.invoke(initial_state)
    |
    |  LangGraph state machine: 5 sequential nodes
    |
    +-- NODE 1: load_document()
    |   |
    |   |  file_type == "pdf"
    |   |    app/ingestion/parsers.py  extract_pdf_pages()
    |   |    Uses: PyMuPDF (pymupdf.open)
    |   |    Process: iterate each page, call get_text("text")
    |   |    Output: [{ page_number: 1, text: "..." }, ...]
    |   |
    |   |  file_type == "txt"
    |   |    app/ingestion/loaders.py  extract_txt_pages()
    |   |    Uses: LangChain TextLoader (UTF-8 + autodetect encoding)
    |   |    Output: [{ page_number: 1, text: "<entire file>" }]
    |   |
    |   +-- State update: { pages: [ExtractedPage, ...] }
    |
    +-- NODE 2: clean_document()
    |   |
    |   |  app/ingestion/cleaners.py  clean_extracted_pages()
    |   |    Wraps pages as LangChain Documents
    |   |    TextCleaningTransformer.transform_documents()
    |   |
    |   |  For each page text:
    |   |    1. Normalize line endings: \r\n to \n
    |   |    2. Remove control characters: [\x00-\x08\x0b\x0c\x0e-\x1f\x7f]
    |   |    3. Collapse horizontal whitespace per line
    |   |    4. Strip trailing whitespace from each line
    |   |    5. Collapse 3+ blank lines to max 2
    |   |    6. Strip leading/trailing whitespace from full text
    |   |
    |   |  Safety check: if all pages empty  raise ValueError
    |   +-- State update: { pages: [cleaned ExtractedPage, ...] }
    |
    +-- NODE 3: split_document()
    |   |
    |   |  app/ingestion/chunkers.py  chunk_pages()
    |   |    RecursiveCharacterTextSplitter.from_tiktoken_encoder(
    |   |      encoding_name="cl100k_base",
    |   |      chunk_size=500,   (configurable)
    |   |      chunk_overlap=75, (configurable)
    |   |      separators=["\n\n", "\n", ". ", " ", ""]
    |   |    )
    |   |
    |   |  For each chunk:
    |   |    chunk_id = uuid5(NAMESPACE_URL,
    |   |                "docusynth:{user_id}:{doc_id}:{page}:{chunk_index}")
    |   |    Deterministic UUID: re-upload same doc = same IDs (upsert safe)
    |   |
    |   |  Output per chunk: DocumentChunk {
    |   |    chunk_id, document_id, user_id,
    |   |    page_number, chunk_index, text
    |   |  }
    |   +-- State update: { chunks: [DocumentChunk, ...] }
    |
    +-- NODE 4: embed_document()
    |   |
    |   |  app/embeddings/embedding_service.py  embed_texts([chunk.text, ...])
    |   |    load_model() [cached singleton via @lru_cache]
    |   |    Model: BAAI/bge-small-en-v1.5 (384 dimensions)
    |   |    Device: CUDA if available, else CPU
    |   |    model.embed_documents(texts)
    |   |    Batch size: 32 (configurable)
    |   |    Normalize embeddings: True (unit vectors for cosine similarity)
    |   |
    |   |  Input : ["chunk text 1", "chunk text 2", ...]
    |   |  Output: [[0.023, -0.15, ...], [0.044, 0.021, ...]]  (384 floats each)
    |   +-- State update: { embeddings: [[float, ...], ...] }
    |
    +-- NODE 5: store_document()
        |
        |  app/vector_store/qdrant_store.py  store_chunks()
        |    ensure_collection() [creates collection if not exists]
        |      collection_name: "document_chunks"
        |      vector_size: 384
        |      distance: COSINE
        |      payload_indexes: user_id (int), document_id (int)
        |
        |    Build PointStruct per chunk:
        |      id: chunk_id (UUID string)
        |      vector: [384 floats]
        |      payload: {
        |        user_id, document_id, filename,
        |        page_number, chunk_index, text
        |      }
        |
        |    qdrant.upsert(points, wait=True)
        |
        +-- State update: { stored_count: N }

Back in process_document():
    |
    |  Success  status = "ready", chunk_count = N, processed_at = now()
    |  Failure  status = "failed", chunk_count = 0
    |           delete_document_points(user_id, document_id)  cleanup Qdrant
    |
    +-- PostgreSQL commit
```

---

## 3. Question-Answering RAG Flow — Non-Streaming

```
Browser
    |
    |  POST /chat/query
    |  Body: { question, selected_document_ids, conversation_id? }
    |  Header: Authorization: Bearer eyJ...
    v
app/api/routes/chat.py  query_documents()
    |
    +-- GUARD 1: verify_selected_documents()
    |   - Queries PostgreSQL: ensure all document_ids belong to user
    |   - Ensures all selected documents have status = "ready"
    |   - If any mismatch  HTTP 404 or HTTP 409
    |
    +-- GUARD 2: resolve_conversation()
    |   - If conversation_id given  verify ownership  load existing
    |   - If None  create new Conversation(title=first 80 chars of question)
    |
    +-- MEMORY: load_conversation_memory()
    |   app/chains/conversational_rag.py  load_conversation_memory()
    |   (See Section 5 for detailed memory flow)
    |
    +-- RAG: run_rag(question, user_id, document_ids, conversation_history)
            |
            |  app/chains/rag_chain.py  run_rag()
            |    create_initial_state()  validates inputs, sets score_threshold
            |    RAG_GRAPH.invoke(state)
            |
            +-- NODE 1: retrieve_context()
            |   app/retrieval/retriever.py  retrieve_chunks()
            |     embed_query(question)
            |       BGE model with QUERY_INSTRUCTION prefix
            |       "Represent this sentence for searching relevant passages: {q}"
            |       Output: [384 floats]
            |     search_points(query_vector, user_id, document_ids, limit=5)
            |       Qdrant cosine similarity search
            |       Filter: user_id == current AND document_id IN selected_ids
            |       Returns: top-5 ScoredPoints
            |     Map to RetrievedChunk TypedDicts
            |
            +-- NODE 2: filter_context()
            |   Remove chunks below score_threshold (default 0.0)
            |
            +-- NODE 3: create_prompt()
            |   app/generation/prompt_builder.py  build_rag_prompt()
            |     build_context(chunks)
            |       Format: [Source N | filename.pdf | Page N]\n{text}
            |     build_conversation_history(messages)
            |       Format: USER: ...\nASSISTANT: ...
            |     RAGPrompt { system: SYSTEM_PROMPT, user: user_prompt }
            |
            +-- NODE 4: generate_answer()
            |   If chunks empty  return NO_CONTEXT_ANSWER (no LLM call)
            |   Else:
            |     app/generation/llm_service.py  OllamaLLM.generate()
            |       ollama.Client.generate(model, prompt, system, stream=False)
            |       response.response.strip()
            |
            +-- NODE 5: collect_sources()
                Build list of RAGSource TypedDicts from chunk metadata
                (never from LLM output — grounded in Qdrant payload)

    Back in query_documents():
        |
        +-- save_messages(conversation, [("user", question), ("assistant", answer)])
        |
        +-- Return ChatQueryResponse { answer, sources, conversation_id }

HTTP 200 OK
    Body: { answer: "...", sources: [...], conversation_id: 42 }
```

---

## 4. Question-Answering RAG Flow — Streaming SSE

```
Browser
    |
    |  POST /chat/query/stream
    |  Body: { question, selected_document_ids, conversation_id? }
    |  Header: Authorization: Bearer eyJ...
    v
app/api/routes/chat.py  stream_query_documents()
    |
    +-- Same guards as non-streaming (verify_documents, resolve_conversation)
    +-- Load conversation memory
    +-- save_messages(conversation, [("user", question)])  save user turn FIRST
    |
    +-- Return StreamingResponse(event_stream(), media_type="text/event-stream")
            headers: Cache-Control: no-cache, X-Accel-Buffering: no

Generator function event_stream():
    |
    |  Calls: stream_rag(question, user_id, document_ids, history)
    |         (bypasses LangGraph graph, runs nodes manually for streaming control)
    |
    +-- state = create_initial_state(...)
    +-- state  retrieve_context(state)    embed + Qdrant search
    +-- state  filter_context(state)      apply score threshold
    +-- state  collect_sources(state)     build source list from metadata
    |
    |  YIELD SSE EVENT #1:
    |    event: sources
    |    data: {"sources": [{ filename, page_number, ... }, ...]}
    |
    |  If chunks empty:
    |    YIELD SSE EVENT: event: token
    |                     data: {"token": "I could not find..."}
    |    YIELD SSE EVENT: event: done
    |    return
    |
    +-- state  create_prompt(state)
    |
    |  OllamaLLM.stream_generate(prompt.user, system_prompt=prompt.system)
    |    ollama.Client.generate(..., stream=True)
    |    Iterator of partial response objects
    |
    |  For each part in stream:
    |    if part.response:
    |      YIELD SSE EVENT: event: token
    |                       data: {"token": "word "}
    |      answer_parts.append(token)
    |
    |  After stream complete:
    |    Open new SessionLocal() session (background thread needs own session)
    |    save_messages(conversation, [("assistant", "".join(answer_parts))])
    |
    |  YIELD FINAL SSE EVENT: event: done
    |                         data: {"conversation_id": 42}

SSE Wire Format (what the browser reads):
    event: sources
    data: {"sources": [...]}

    event: token
    data: {"token": "Based"}

    event: token
    data: {"token": " on"}

    event: done
    data: {"conversation_id": 42}

Browser (frontend/js/chat.js  streamAnswer()):
    |
    |  ReadableStream reader  TextDecoder
    |  Buffer accumulates bytes
    |  Split on "\n\n" (SSE block boundary)
    |  Parse: event line + data line  { eventType, data }
    |
    +-- "sources"  renderSources(sources)
    +-- "token"    answer += token; body.textContent = answer; scroll
    +-- "done"     state.activeConversationId = conversation_id
    +-- On stream complete  renderMarkdown(body, answer)
```

---

## 5. Conversation Memory Flow

```
User sends Question 2 in an existing conversation
    |
    v
app/api/routes/chat.py  load_conversation_memory(conversation_id, user_id, db)
    |
    v
app/chains/conversational_rag.py  load_conversation_memory()
    |
    +-- Query: SELECT messages JOIN conversations
    |          WHERE message.conversation_id = ?
    |            AND conversation.user_id = ?   (user isolation enforced at DB)
    |          ORDER BY message.id DESC
    |          LIMIT conversation_memory_max_messages (default: 8)
    |
    +-- Reverse the list (most recent first to chronological order)
    |
    +-- trim_conversation_history(messages, max_messages=8, max_tokens=1200)
        |
        |  Iterates messages in REVERSE (newest first)
        |  For each message:
        |    1. count_memory_tokens(content)  [tiktoken cl100k_base]
        |    2. remaining_budget = max_tokens - used_tokens - 4 (role overhead)
        |    3. If budget exhausted  stop
        |    4. If message too long  truncate_message_content()
        |       Fits within budget, appends "... [truncated]" marker
        |    5. Append to selected_reversed
        |    6. Add tokens to used_tokens
        |
        +-- Return list(reversed(selected_reversed))
               Chronological order, oldest messages may be dropped

Output: [
    { role: "user",      content: "Who is Harry?" },
    { role: "assistant", content: "Harry is a wizard..." },
]

This history is injected into build_rag_prompt():
    CONVERSATION HISTORY
    <conversation_history>
    USER: Who is Harry?
    ASSISTANT: Harry is a wizard...
    </conversation_history>

    DOCUMENT CONTEXT
    <document_context>
    [Source 1 | book.pdf | Page 5]
    ... chunk text ...
    </document_context>

    CURRENT QUESTION
    Where did he go to school?

    LLM resolves "he" from history = "Harry"  answers from document context
```

---

## 6. Document Deletion Flow

```
Browser (documents.html)  click Delete  confirm dialog
    |
    |  DELETE /documents/{document_id}
    |  Header: Authorization: Bearer eyJ...
    v
app/api/routes/documents.py  delete_document()
    |
    +-- get_owned_document(document_id, user_id, db)
    |   SELECT WHERE id = ? AND user_id = ?  (ownership enforced)
    |   If not found  HTTP 404
    |
    +-- delete_document_points(user_id, document_id)
    |   app/vector_store/qdrant_store.py
    |   qdrant.delete(
    |     filter: { user_id == user AND document_id == doc_id }
    |   )
    |   Removes all Qdrant vectors for this document
    |   user_id filter prevents cross-user deletion
    |
    +-- database.delete(document)
    |   PostgreSQL: DELETE FROM documents WHERE id = ?
    |
    +-- database.commit()
    |
    +-- remove_file(stored_path)
        Path(upload_dir) / stored_filename
        os.remove()  deletes physical file from disk

HTTP 204 No Content

Browser  removes document row from UI  reloads document list
```

---

## 7. Complete RAG Internal Pipeline Deep Dive

Step-by-step data transformation showing actual data structures at every stage.

```
INPUT:
  question     = "What are the main themes in chapter 3?"
  user_id      = 42
  document_ids = [7, 12]

------------------------------------------------------------------

STEP 1: Question Embedding
  File: app/embeddings/embedding_service.py  embed_query()

  Input:
    "What are the main themes in chapter 3?"

  Internal process:
    Prefixed with: "Represent this sentence for searching relevant passages: "
    Sent to: BAAI/bge-small-en-v1.5 (loaded once, cached in memory)
    Normalized: Yes (L2-norm  unit vector)

  Output:
    [0.0234, -0.1502, 0.0891, ..., 0.0441]  (384 floats)

------------------------------------------------------------------

STEP 2: Vector Similarity Search
  File: app/vector_store/qdrant_store.py  search_points()

  Qdrant Query:
    collection: "document_chunks"
    query_vector: [384 floats]
    filter: {
      must: [
        { key: "user_id",     match: { value: 42 } },
        { key: "document_id", match: { any: [7, 12] } }
      ]
    }
    limit: 5
    with_payload: true
    with_vectors: false

  Output (list of ScoredPoint):
    [
      ScoredPoint(id="uuid-1", score=0.892, payload={
        user_id: 42, document_id: 7, filename: "book.pdf",
        page_number: 31, chunk_index: 14,
        text: "Chapter 3 explores themes of identity and belonging..."
      }),
      ScoredPoint(id="uuid-2", score=0.841, payload={ ... }),
      ScoredPoint(id="uuid-3", score=0.798, payload={ ... }),
      ScoredPoint(id="uuid-4", score=0.751, payload={ ... }),
      ScoredPoint(id="uuid-5", score=0.692, payload={ ... }),
    ]

------------------------------------------------------------------

STEP 3: Score Threshold Filter
  File: app/chains/rag_chain.py  filter_context()

  Threshold: 0.0 (all chunks pass; raise to 0.5 for stricter filtering)
  Output: same 5 chunks (all scores > 0.0)

------------------------------------------------------------------

STEP 4: Context Construction
  File: app/generation/prompt_builder.py  build_context()

  Output string:
    [Source 1 | book.pdf | Page 31]
    Chapter 3 explores themes of identity and belonging...

    [Source 2 | book.pdf | Page 32]
    The author contrasts two characters to illustrate...

    [Source 3 | report.txt | Page 1]
    ...

------------------------------------------------------------------

STEP 5: Prompt Construction
  File: app/generation/prompt_builder.py  build_rag_prompt()

  SYSTEM PROMPT (sent separately to Ollama):
    "You are DocuSynth, a careful document question-answering assistant.
     Rules: 1. Answer using only DOCUMENT CONTEXT. ..."

  USER PROMPT:
    CONVERSATION HISTORY
    <conversation_history>
    USER: Who wrote this book?
    ASSISTANT: The book was written by J.K. Rowling [Source 1].
    </conversation_history>

    DOCUMENT CONTEXT
    <document_context>
    [Source 1 | book.pdf | Page 31]
    Chapter 3 explores themes of identity and belonging...

    [Source 2 | book.pdf | Page 32]
    The author contrasts two characters to illustrate...
    </document_context>

    CURRENT QUESTION
    What are the main themes in chapter 3?

    Answer using only the document context and include source labels.

------------------------------------------------------------------

STEP 6: LLM Generation
  File: app/generation/llm_service.py  OllamaLLM.generate()

  Sent to: Ollama HTTP API at http://localhost:11434
  Model: gemma3:4b
  Options: temperature=0.2, num_predict=1024, keep_alive="10m"

  For streaming: same flow but stream=True  yields text fragments

  Output:
    "Chapter 3 primarily explores themes of identity and belonging [Source 1].
     The author uses contrasting characters to illustrate how individuals define
     themselves in relation to their community [Source 2]."

------------------------------------------------------------------

STEP 7: Source Collection
  File: app/chains/rag_chain.py  collect_sources()

  Built from Qdrant payload metadata (NOT from LLM output):
    [
      { source_number: 1, document_id: 7, filename: "book.pdf",
        page_number: 31, chunk_index: 14, score: 0.892 },
      { source_number: 2, document_id: 7, filename: "book.pdf",
        page_number: 32, chunk_index: 15, score: 0.841 },
      ...
    ]

------------------------------------------------------------------

FINAL OUTPUT:
  {
    answer: "Chapter 3 primarily explores themes of identity [Source 1]...",
    sources: [ { source_number, document_id, filename, page_number, ... } ],
    conversation_id: 42
  }
```

---

## 8. Security Invariants

| Checkpoint | Enforcement |
|---|---|
| Uploads | MIME type + file extension + magic bytes all validated |
| Filenames | Original filename stripped; UUID-based stored filename used |
| File size | Enforced while streaming to disk, not post-write |
| Document access | WHERE document_id IN (?) AND user_id = ? in every query |
| Vector search | user_id filter always included in Qdrant query filter |
| Vector deletion | user_id filter always included in Qdrant delete filter |
| Conversation access | WHERE conversation_id = ? AND user_id = ? always |
| JWT validation | Signature + expiry + type claim + numeric sub all verified |
| Password storage | bcrypt hash stored; plaintext never logged or stored |
| Prompt injection | Context wrapped in XML tags; system prompt warns against it |

---

*Document version: Phase 28 complete*
*Last updated: 2026-09-24*
