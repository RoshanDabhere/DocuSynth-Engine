# DocuSynth Engine — Architecture Reference

> **Purpose**: A complete technical reference for every layer of the DocuSynth Engine
> system. Use this document to understand how modules fit together, why each design
> decision was made, and where to add new features.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Directory Structure](#2-directory-structure)
3. [Backend Architecture](#3-backend-architecture)
4. [Frontend Architecture](#4-frontend-architecture)
5. [Database Architecture](#5-database-architecture)
6. [Vector Database Architecture](#6-vector-database-architecture)
7. [Ingestion Pipeline Architecture](#7-ingestion-pipeline-architecture)
8. [RAG Chain Architecture](#8-rag-chain-architecture)
9. [Authentication Architecture](#9-authentication-architecture)
10. [Configuration Architecture](#10-configuration-architecture)
11. [Module Dependency Map](#11-module-dependency-map)
12. [Technology Decisions](#12-technology-decisions)
13. [Extension Points](#13-extension-points)

---

## 1. System Overview

DocuSynth Engine is a production-style RAG (Retrieval-Augmented Generation) application.

```
+------------------+       HTTP REST + SSE       +-------------------+
|                  |  <----------------------->   |                   |
|  Browser         |                             |  FastAPI Backend   |
|  Vanilla HTML    |                             |  (Python 3.12)    |
|  CSS + JS        |                             |                   |
+------------------+                             +-------------------+
                                                   |        |
                                          +--------+        +--------+
                                          |                          |
                                   +------+------+          +--------+------+
                                   | PostgreSQL  |          |   Qdrant      |
                                   | (Relational)|          | (Vector DB)   |
                                   | users       |          | document_chunks|
                                   | documents   |          | collection    |
                                   | conversations|         | 384-dim COSINE|
                                   | messages    |          +---------------+
                                   +-------------+
                                          |
                                   +------+------+
                                   |   Ollama    |
                                   | gemma3:4b   |
                                   | (local LLM) |
                                   +-------------+
```

**Two separate AI model processes run locally:**

| Model | Role | Loaded By |
|---|---|---|
| BAAI/bge-small-en-v1.5 | Embedding (384 dim) | HuggingFace in FastAPI process |
| gemma3:4b | Generation (LLM) | Ollama daemon (separate process) |

---

## 2. Directory Structure

```
DocuSynth-Engine/
|
+-- app/                          Backend Python package
|   +-- main.py                   FastAPI app factory + CORS + router registration
|   +-- config.py                 Pydantic Settings (reads .env, cached singleton)
|   |
|   +-- api/                      HTTP interface layer
|   |   +-- dependencies.py       Reusable FastAPI Depends: CurrentUser, DatabaseSession
|   |   +-- routes/
|   |       +-- auth.py           POST /auth/register, POST /auth/login, GET /auth/me
|   |       +-- documents.py      POST /documents/upload, GET /documents, DELETE /{id}
|   |       +-- chat.py           POST /chat/query, POST /chat/query/stream,
|   |                             GET /chat/conversations, GET /chat/conversations/{id}
|   |
|   +-- models/                   SQLAlchemy ORM models (PostgreSQL tables)
|   |   +-- user.py               users table
|   |   +-- documents.py          documents table
|   |   +-- conversation.py       conversations table
|   |   +-- message.py            messages table
|   |
|   +-- schemas/                  Pydantic schemas (API request/response validation)
|   |   +-- auth.py               LoginRequest, TokenResponse
|   |   +-- user.py               UserCreate, UserResponse
|   |   +-- document.py           DocumentResponse
|   |   +-- chat.py               ChatQueryRequest, ChatQueryResponse
|   |   +-- conversation.py       ConversationResponse, ConversationDetailResponse
|   |
|   +-- database/                 Database infrastructure
|   |   +-- connection.py         engine, SessionLocal, Base, get_db()
|   |
|   +-- security/                 Auth helpers
|   |   +-- authentication.py     hash_password, verify_password, create/decode JWT
|   |
|   +-- ingestion/                Document processing pipeline
|   |   +-- types.py              ExtractedPage, DocumentChunk TypedDicts
|   |   +-- parsers.py            PyMuPDF PDF text extraction
|   |   +-- loaders.py            LangChain TXT loading
|   |   +-- cleaners.py           Text normalization transformer
|   |   +-- chunkers.py           Token-aware recursive text splitter
|   |   +-- pipeline.py           LangGraph ingestion state machine
|   |
|   +-- embeddings/               Embedding model management
|   |   +-- embedding_service.py  BGE model singleton, embed_text/texts/query
|   |
|   +-- vector_store/             Qdrant client operations
|   |   +-- qdrant_store.py       ensure_collection, store_chunks, search_points,
|   |                             delete_document_points, user_filter
|   |
|   +-- retrieval/                Semantic search
|   |   +-- retriever.py          retrieve_chunks (embed + Qdrant search + mapping)
|   |
|   +-- generation/               LLM and prompt management
|   |   +-- llm_service.py        LLMProvider protocol, OllamaLLM, get_llm_service()
|   |   +-- prompt_builder.py     SYSTEM_PROMPT, build_context, build_rag_prompt
|   |
|   +-- chains/                   LangGraph orchestration
|   |   +-- rag_chain.py          RAG_GRAPH (5-node), run_rag, stream_rag
|   |   +-- conversational_rag.py load_conversation_memory, trim_conversation_history
|   |
|   +-- utils/                    Cross-cutting utilities
|       +-- file_utils.py         create_stored_filename, remove_file
|       +-- validators.py         validate_upload_metadata, validate_file_header
|
+-- frontend/                     Vanilla HTML + CSS + ES Modules
|   +-- index.html                Root redirect to login
|   +-- pages/
|   |   +-- login.html            Login page
|   |   +-- register.html         Registration page
|   |   +-- dashboard.html        User dashboard (redirects to chat/documents)
|   |   +-- documents.html        Document library with drag-and-drop upload
|   |   +-- chat.html             Main chat interface
|   |
|   +-- css/
|   |   +-- styles.css            Complete design system (27 KB)
|   |
|   +-- js/
|       +-- api.js                Fetch wrapper, token get/save/clear
|       +-- auth.js               Login, register, logout, protectPage()
|       +-- documents.js          Upload, polling, delete, document list UI
|       +-- chat.js               Conversation list, SSE streaming, message rendering
|       +-- markdown.js           Simple markdown to HTML renderer
|       +-- streaming.js          buildChatRequest, parseEventBlock helpers
|       +-- document-utils.js     formatFileSize, validateClientFile, buildChatDocumentUrl
|       +-- app.js                Shared initialization
|
+-- uploads/                      Physical file storage (gitignored)
+-- tests/                        Test suite
+-- docs/                         Project documentation (this folder)
+-- docker-compose.yml            Container orchestration
+-- requirements.txt              Python dependencies
+-- run.py                        Dev server launcher
+-- .env                          Environment variables (gitignored)
+-- .env.example                  Template with all required variables
+-- pyproject.toml                Linting + formatting config
```

---

## 3. Backend Architecture

### 3.1 Application Factory Pattern

```python
# app/main.py
def create_application() -> FastAPI:
    settings = get_settings()
    application = FastAPI(...)
    application.add_middleware(CORSMiddleware, ...)
    application.include_router(auth_router)
    application.include_router(documents_router)
    application.include_router(chat_router)
    return application

app = create_application()
```

**Why factory pattern?** Allows creating fresh app instances in tests without
global state leaking between test runs.

### 3.2 Layer Responsibilities

```
Request arrives at FastAPI
    |
    v
[ROUTE LAYER]  app/api/routes/*.py
    - HTTP parsing (query params, body, headers)
    - FastAPI dependency injection (CurrentUser, DatabaseSession)
    - Input validation via Pydantic schemas
    - Orchestration of service calls
    - HTTP response shaping

    |
    v
[CHAIN/ORCHESTRATION LAYER]  app/chains/*.py
    - LangGraph state machines
    - Calls service-layer modules in the right order
    - Manages state passing between steps

    |
    v
[SERVICE LAYER]  app/ingestion/, app/embeddings/, app/retrieval/,
                 app/generation/, app/vector_store/
    - Single-responsibility domain logic
    - Stateless functions
    - No awareness of HTTP

    |
    v
[INFRASTRUCTURE LAYER]  app/database/, app/security/
    - Raw database/crypto operations
    - Connection management
```

### 3.3 Dependency Injection

FastAPI uses Python type annotations as the DI mechanism:

```python
# app/api/dependencies.py
DatabaseSession = Annotated[Session, Depends(get_db)]
CurrentUser     = Annotated[User,    Depends(get_current_user)]

# Usage in any route — FastAPI injects automatically:
def my_endpoint(user: CurrentUser, db: DatabaseSession):
    ...
```

**get_db()** is a generator that yields one session and guarantees close(),
even on exception. This prevents connection pool exhaustion.

**get_current_user()** validates the JWT, queries the user, and raises HTTP 401
if anything fails. Every protected endpoint inherits this behavior automatically
just by declaring `current_user: CurrentUser` in its signature.

### 3.4 Background Task Pattern

Document ingestion uses FastAPI's `BackgroundTasks` to avoid blocking the HTTP response:

```python
# Route returns HTTP 201 immediately
background_tasks.add_task(process_document, document.id)
return document
```

The background function opens its own database session (cannot share the request
session which is closed after the response). This is why `process_document` uses
`SessionLocal()` as a context manager.

---

## 4. Frontend Architecture

### 4.1 Technology Choice

Vanilla HTML + CSS + ES Modules (no build step, no framework).

**Why no React/Vue?** The project requirement is to understand every layer.
A framework would hide the state management, event handling, and DOM updates
that are essential to understand. The vanilla stack also eliminates Node.js
dependency for the frontend and can be served by any static file server.

### 4.2 Module Structure

```
api.js            <- Bottom layer: raw HTTP + token storage
    |
    +-- auth.js         Uses apiRequest for login/register
    +-- documents.js    Uses apiRequest + XHR for upload progress
    +-- chat.js         Uses fetch directly for SSE streaming
        +-- markdown.js     Used by chat.js to render assistant responses
        +-- streaming.js    SSE parsing helpers used by chat.js
        +-- document-utils.js  Shared helpers used by chat.js and documents.js
```

### 4.3 Token Storage Decision

Token stored in **sessionStorage** (not localStorage).

| Storage | Persistence | XSS Risk | CSRF Risk |
|---|---|---|---|
| localStorage | Survives tab close | High (JS readable) | None |
| sessionStorage | Tab lifetime only | Medium (JS readable) | None |
| httpOnly cookie | Survives tab close | Low (JS cannot read) | High |

SessionStorage is a pragmatic balance: no XSS from other tabs, clears on tab
close (reduces credential theft window), and avoids the CSRF complexity of
secure cookies in a single-origin dev setup.

### 4.4 State Management

Each page's JS file maintains a plain `state` object:

```javascript
// chat.js
const state = {
    activeConversationId: null,
    conversations: [],
    documents: [],
    isStreaming: false,
    selectedDocumentIds: new Set(),
};
```

State mutations are followed immediately by a render call. This is a simple
unidirectional data flow without a reactive framework. It works cleanly for
this project's complexity level.

### 4.5 SSE Streaming Pattern

```javascript
// Incremental token display during streaming
answer += data.token;
assistantMessage.body.textContent = answer;
scrollMessagesToBottom();

// Convert raw text to Markdown only after stream ends
renderMarkdown(assistantMessage.body, answer || "No answer was returned.");
```

Tokens are shown as plain text during streaming for maximum performance.
Markdown rendering is deferred to the `done` event to avoid re-parsing on
every token.

### 4.6 Document Status Polling

The documents page polls the API every 2 seconds while any document is in
`uploaded` or `processing` state:

```javascript
function scheduleStatusPolling() {
    const hasPending = state.documents.some(d =>
        d.status === "uploaded" || d.status === "processing"
    );
    if (!hasPending) return;
    state.pollTimer = setTimeout(async () => { await loadDocuments(); }, 2000);
}
```

Polling stops automatically when all documents reach `ready` or `failed`.

---

## 5. Database Architecture

### 5.1 Entity Relationship Diagram

```
users
  id (PK)
  name
  email (UNIQUE, INDEX)
  hashed_password
  is_active
  created_at
  updated_at
      |
      | 1:N (CASCADE DELETE)
      |
  documents
    id (PK)
    user_id (FK -> users.id)
    original_filename
    stored_filename (UNIQUE)
    file_type
    file_size
    status  [uploaded|processing|ready|failed]
    chunk_count
    created_at
    processed_at

  conversations
    id (PK)
    user_id (FK -> users.id)
    title
    created_at
    updated_at
        |
        | 1:N (CASCADE DELETE)
        |
      messages
        id (PK)
        conversation_id (FK -> conversations.id)
        role  [user|assistant]
        content (TEXT)
        created_at
```

### 5.2 Key Design Decisions

**CASCADE DELETE on user_id**: Deleting a user automatically deletes all their
documents, conversations, and messages. Prevents orphaned rows.

**stored_filename UNIQUE constraint**: Guarantees two uploads never overwrite
each other on disk. Uses UUID generation to achieve this.

**status CHECK constraint**: PostgreSQL enforces that status can only be one of
the four allowed values at the database level, not just application level.

**role CHECK constraint on messages**: `user` or `assistant` only — enforced
at database level.

**expire_on_commit=False in SessionLocal**: Objects remain accessible after
`commit()` without requiring a new `SELECT`. This is important in background
tasks where we commit and then immediately read `document.status`.

### 5.3 ORM Layer

Uses SQLAlchemy 2.0 mapped_column API (type-annotated style):

```python
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    ...
```

The `Mapped[T]` annotation makes the type checker aware that `user.id` is an
`int`, not `Any`. This catches bugs at static analysis time.

---

## 6. Vector Database Architecture

### 6.1 Qdrant Collection Design

```
Collection: "document_chunks"
Vector dimension: 384
Distance metric: COSINE

Payload indexes (for fast filtered search):
  - user_id    (INTEGER)
  - document_id (INTEGER)

Each point:
  id      : UUID string (deterministic from user+doc+page+chunk)
  vector  : [384 floats]  (normalized, L2 unit vector)
  payload : {
    user_id     : int,
    document_id : int,
    filename    : str,
    page_number : int,
    chunk_index : int,
    text        : str
  }
```

### 6.2 Why Cosine Distance?

The BAAI/bge-small-en-v1.5 model normalizes embeddings to unit vectors
(normalize_embeddings=True). For unit vectors:

```
cosine_similarity(a, b) = a . b = dot_product(a, b)
```

Cosine similarity measures the angle between vectors, not their magnitude.
Two semantically similar texts produce vectors that point in similar directions
even if they have different lengths. This is what we want for semantic search.

**Score range:** -1 (opposite meaning) to +1 (identical meaning).
A threshold of 0.0 means we only return chunks that have at least some
semantic alignment with the query.

### 6.3 Why Payload Indexes?

Without indexes, Qdrant must scan every point's payload to apply the filter.
With indexed payload fields, Qdrant can narrow the candidate set before
performing vector comparison, making searches much faster as the collection grows.

**user_id index** is critical for multi-tenant isolation.
**document_id index** is critical for filtering to selected documents only.

### 6.4 Deterministic Chunk IDs

```python
chunk_id = uuid5(NAMESPACE_URL,
                 f"docusynth:{user_id}:{doc_id}:{page}:{chunk_index}")
```

UUID v5 is deterministic: same inputs always produce the same UUID.
This means if a document is re-uploaded:
- The same chunk IDs are generated
- `qdrant.upsert()` updates existing points (not duplicates)
- The collection remains consistent

---

## 7. Ingestion Pipeline Architecture

### 7.1 LangGraph State Machine

```
START
  |
  v
load_document
  (parsers.py or loaders.py)
  |
  v
clean_document
  (cleaners.py)
  |
  v
split_document
  (chunkers.py)
  |
  v
embed_document
  (embedding_service.py)
  |
  v
store_document
  (qdrant_store.py)
  |
  v
END
```

**Why LangGraph?** LangGraph provides a typed state container (IngestionState
TypedDict) that is passed between nodes. Each node receives the full state and
returns only the keys it modifies. This prevents bugs where a node accidentally
overwrites state set by a previous node.

**Why not a simple function call chain?**
- Error boundary is cleaner (exception in any node propagates cleanly)
- State is explicit and inspectable
- Easy to add conditional edges later (e.g., skip clean step for pre-cleaned docs)
- Matches the RAG chain pattern for consistency

### 7.2 IngestionState TypedDict

```python
class IngestionState(TypedDict, total=False):
    document_id  : int
    user_id      : int
    filename     : str
    file_path    : Path
    file_type    : str
    pages        : list[ExtractedPage]      # set by load_document
    chunks       : list[DocumentChunk]      # set by split_document
    embeddings   : list[list[float]]        # set by embed_document
    stored_count : int                      # set by store_document
```

`total=False` means all keys are optional. Initial state only has the first
five keys; later nodes add the rest. LangGraph merges return dicts into state.

### 7.3 Error Handling Strategy

```python
try:
    result = INGESTION_GRAPH.invoke(initial_state)
    document.status = "ready"
    document.chunk_count = result["stored_count"]
except Exception:
    document.status = "failed"
    delete_document_points(user_id, document_id)  # cleanup Qdrant on failure
```

If any node raises an exception (PDF corrupted, all text empty, Qdrant down,
etc.), the document is marked `failed` and any partially-stored vectors are
deleted. The user sees `failed` status in the UI and can re-upload.

---

## 8. RAG Chain Architecture

### 8.1 LangGraph RAG Graph

```
START
  |
  v
retrieve  (embed question + Qdrant search)
  |
  v
filter    (score threshold)
  |
  v
prompt    (build system + user prompt)
  |
  v
generate  (Ollama LLM)
  |
  v
sources   (collect metadata from chunks)
  |
  v
END
```

### 8.2 Streaming vs Non-Streaming

The non-streaming path uses the compiled LangGraph:

```python
result = RAG_GRAPH.invoke(initial_state)
```

The streaming path bypasses the graph and calls nodes manually:

```python
def stream_rag(...):
    state = create_initial_state(...)
    state.update(retrieve_context(state))
    state.update(filter_context(state))
    state.update(collect_sources(state))
    yield {"type": "sources", "sources": state["sources"]}

    state.update(create_prompt(state))
    for token in get_llm_service().stream_generate(...):
        yield {"type": "token", "token": token}
    yield {"type": "done"}
```

**Why bypass the graph for streaming?** LangGraph `invoke()` waits for all
nodes to complete before returning. Streaming requires yielding tokens
as they arrive from Ollama. So we run the non-streaming nodes through
the graph manually, then directly call the LLM's stream_generate iterator.

### 8.3 LLMProvider Protocol

```python
class LLMProvider(Protocol):
    def generate(self, prompt: str, system_prompt: str | None = None) -> str: ...
    def stream_generate(self, prompt: str, ...) -> Iterator[str]: ...
```

`OllamaLLM` implements this protocol. To replace with OpenAI:

```python
class OpenAILLM:
    def generate(self, prompt, system_prompt=None) -> str:
        response = openai.chat.completions.create(...)
        return response.choices[0].message.content

    def stream_generate(self, prompt, system_prompt=None) -> Iterator[str]:
        for chunk in openai.chat.completions.create(..., stream=True):
            yield chunk.choices[0].delta.content or ""
```

Then update `get_llm_service()` to return `OpenAILLM(...)`.
The chain code (rag_chain.py) requires zero changes.

---

## 9. Authentication Architecture

### 9.1 JWT Structure

```json
{
  "sub": "42",       <- user ID as string
  "exp": 1234567890, <- Unix timestamp of expiry
  "type": "access"   <- prevents refresh tokens from being used as access tokens
}
```

Signed with: HMAC-SHA256 (HS256) using JWT_SECRET_KEY.

Verification checks:
1. Signature valid (tamper detection)
2. `exp` not in the past (expiry)
3. `type` == "access" (token type mismatch prevention)
4. `sub` is a numeric string (user ID format)
5. User with that ID exists and is active

### 9.2 Password Security

```
Registration:
  user_input "password123"
      -> bcrypt.hashpw(b"password123", bcrypt.gensalt())
      -> "$2b$12$randomsalt+hash"  (stored in DB)

Login:
  user_input "password123"
  stored_hash "$2b$12$randomsalt+hash"
      -> bcrypt.checkpw(b"password123", b"$2b$12$...")
      -> True / False
```

bcrypt properties:
- Adaptive cost factor (work factor rounds in hash): currently 12, can be raised
- Salt is embedded in the hash string (no separate salt column needed)
- Timing-safe comparison (not susceptible to timing attacks)
- Intentionally slow: ~100ms per check prevents brute force

### 9.3 Request Authentication Flow

```
Every protected endpoint:
    1. FastAPI extracts Bearer token from Authorization header
       (OAuth2PasswordBearer dependency)
    2. decode_access_token() validates and returns user_id
    3. DB query: does user exist and is_active?
    4. User object injected into the endpoint function

If any step fails: HTTP 401 Unauthorized
```

---

## 10. Configuration Architecture

### 10.1 Settings Class

```python
class Settings(BaseSettings):
    # Required (must be in .env or environment)
    database_url: SecretStr
    jwt_secret_key: SecretStr

    # Optional with defaults
    ollama_model: str = "gemma3:4b"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    retrieval_top_k: int = 5
    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 75
    ...
```

`SecretStr` fields are never accidentally logged (they display as `**********`
in stack traces and logs).

### 10.2 Singleton Pattern

```python
@lru_cache
def get_settings() -> Settings:
    return Settings()
```

`@lru_cache` with no arguments caches the first call result forever. The `.env`
file is read only once when the process starts. This prevents repeated disk I/O
and ensures all modules share the same configuration object.

The same pattern is used for:
- `get_llm_service()` — one Ollama client per process
- `get_qdrant_client()` — one Qdrant client per process
- `load_model()` — one embedding model per process

### 10.3 Environment Variable Precedence

1. Actual environment variables (highest priority — Docker/CI/CD)
2. .env file values
3. Class defaults (lowest priority)

---

## 11. Module Dependency Map

```
app/main.py
  <- app/config.py
  <- app/api/routes/auth.py
       <- app/api/dependencies.py
            <- app/database/connection.py
            <- app/models/user.py
            <- app/security/authentication.py
       <- app/models/user.py
       <- app/schemas/auth.py, user.py
  <- app/api/routes/documents.py
       <- app/api/dependencies.py
       <- app/ingestion/pipeline.py
            <- app/ingestion/parsers.py
                 <- app/ingestion/types.py
            <- app/ingestion/loaders.py
            <- app/ingestion/cleaners.py
            <- app/ingestion/chunkers.py
            <- app/embeddings/embedding_service.py
            <- app/vector_store/qdrant_store.py
       <- app/models/documents.py
       <- app/schemas/document.py
       <- app/utils/file_utils.py, validators.py
  <- app/api/routes/chat.py
       <- app/chains/rag_chain.py
            <- app/retrieval/retriever.py
                 <- app/embeddings/embedding_service.py
                 <- app/vector_store/qdrant_store.py
            <- app/generation/llm_service.py
            <- app/generation/prompt_builder.py
                 <- app/chains/conversational_rag.py
                      <- app/models/conversation.py
                      <- app/models/message.py
       <- app/chains/conversational_rag.py
       <- app/models/conversation.py, message.py
       <- app/schemas/chat.py, conversation.py
```

---

## 12. Technology Decisions

| Decision | Choice | Why |
|---|---|---|
| Web framework | FastAPI | Auto docs, async support, Pydantic integration, type safety |
| ORM | SQLAlchemy 2.0 | Mature, type-annotated API, works with any SQL database |
| Database | PostgreSQL | ACID transactions, robust constraints, production-proven |
| Vector DB | Qdrant | Payload filtering for multi-tenant isolation, cosine distance, REST API |
| Embedding model | BAAI/bge-small-en-v1.5 | Good quality, small (384 dim), fast on CPU, free |
| LLM | Ollama (gemma3:4b) | Local, free, no API key, swappable via LLMProvider protocol |
| Orchestration | LangGraph | Typed state passing, easy to inspect/debug, not LangChain abstraction |
| PDF parsing | PyMuPDF | Fastest Python PDF library, good text extraction quality |
| Chunking | tiktoken + LangChain splitter | Token-aware splitting prevents embedding model truncation |
| Auth | JWT + bcrypt | Stateless (no server-side session), industry standard, scalable |
| Frontend | Vanilla JS | No build step, complete transparency, easy to understand |
| SSE streaming | FastAPI StreamingResponse | Native Python generator, no WebSocket complexity |

---

## 13. Extension Points

### Adding a new document type (e.g., DOCX)

1. Add `.docx` to `ALLOWED_TYPES` in `app/utils/validators.py`
2. Create `app/ingestion/docx_loader.py` with `extract_docx_pages()`
3. Add `elif file_type == "docx": pages = extract_docx_pages(...)` in `pipeline.py`
4. No other files need changes.

### Replacing the LLM provider (e.g., OpenAI)

1. Create a class implementing `LLMProvider` protocol in `llm_service.py`
2. Update `get_llm_service()` to return the new class
3. No other files need changes.

### Adding a reranker

1. Create `app/retrieval/reranker.py` with `rerank(chunks, question)` function
2. Add a new `rerank` node in `rag_chain.py`
3. Insert `graph.add_node("rerank", rerank_context)` between filter and prompt
4. Update the edges.

### Changing the embedding model (e.g., text-embedding-3-small)

1. Update `embedding_service.py` to use the OpenAI client
2. Update `EMBEDDING_DIMENSION` in `.env` and `config.py`
3. Delete and recreate the Qdrant collection (dimension change requires recreation)
4. Re-process all documents.

### Adding hybrid search (BM25 + dense)

1. Create `app/retrieval/hybrid_search.py`
2. Store document text in PostgreSQL for BM25 (or use Qdrant sparse vectors)
3. Modify `retrieve_chunks` to combine dense + BM25 scores (Reciprocal Rank Fusion)

---

*Document version: Phase 28 complete*
*Last updated: 2026-09-24*
