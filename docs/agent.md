# DocuSynth Engine — Agent & Orchestration Reference

> **Purpose**: Explains the LangGraph-based agentic architecture used in DocuSynth
> Engine. Covers what an "agent" means in this context, how LangGraph state machines
> work, the two compiled graphs (Ingestion and RAG), and how to extend them.

---

## Table of Contents

1. [What "Agent" Means Here](#1-what-agent-means-here)
2. [LangGraph Fundamentals](#2-langgraph-fundamentals)
3. [Ingestion Agent](#3-ingestion-agent)
4. [RAG Agent](#4-rag-agent)
5. [Streaming Agent (Manual Node Execution)](#5-streaming-agent-manual-node-execution)
6. [Conversational Memory Agent](#6-conversational-memory-agent)
7. [State TypedDicts Reference](#7-state-typeddicts-reference)
8. [Node Reference](#8-node-reference)
9. [Adding New Nodes](#9-adding-new-nodes)
10. [Replacing Nodes](#10-replacing-nodes)
11. [Why LangGraph and Not Plain Functions](#11-why-langgraph-and-not-plain-functions)
12. [Future Agent Capabilities](#12-future-agent-capabilities)

---

## 1. What "Agent" Means Here

In AI engineering, "agent" can mean many things. In DocuSynth Engine, it refers
specifically to **LangGraph-compiled state machines** that:

1. Receive an initial typed state
2. Route that state through a deterministic sequence of processing nodes
3. Each node reads from and writes to the shared state
4. The final state contains the complete result

This is a **reactive pipeline agent**, not an autonomous agent. There is no
dynamic tool selection, no self-directed planning, and no iterative decision
making. Every execution follows the same graph topology.

```
Traditional autonomous agent (NOT what we use):
    User question -> LLM decides which tools to call
               -> LLM calls tool A
               -> LLM decides to call tool B based on A's output
               -> LLM generates final answer

DocuSynth pipeline agent (what we use):
    User question -> embed -> search -> filter -> prompt -> generate -> sources
                     fixed linear sequence, no LLM in the loop until step 5
```

**Why pipeline agents?**
- Deterministic: same inputs produce same execution path
- Debuggable: every state transition is inspectable
- Secure: LLM cannot decide to skip the user isolation filter
- Fast: no LLM call is wasted on planning

---

## 2. LangGraph Fundamentals

### StateGraph

```python
from langgraph.graph import START, END, StateGraph

graph = StateGraph(MyState)  # MyState is a TypedDict
graph.add_node("step_a", function_a)
graph.add_node("step_b", function_b)
graph.add_edge(START, "step_a")
graph.add_edge("step_a", "step_b")
graph.add_edge("step_b", END)
compiled = graph.compile()
```

### Node Functions

Every node is a plain Python function:

```python
def my_node(state: MyState) -> MyState:
    # Read from state
    value = state["input_key"]

    # Do work
    result = process(value)

    # Return ONLY the keys this node sets
    # LangGraph merges this with the existing state
    return {"output_key": result}
```

Important: nodes return a PARTIAL state (only the keys they modify).
LangGraph merges the returned dict into the current state automatically.
This prevents one node from accidentally clearing keys set by previous nodes.

### invoke() vs streaming

```python
# Synchronous: waits for all nodes to complete
final_state = compiled.invoke(initial_state)

# Streaming: yields state after each node
for state_update in compiled.stream(initial_state):
    print(state_update)  # {node_name: partial_state}
```

DocuSynth uses `invoke()` for the ingestion pipeline (no streaming needed)
and manual node execution for the RAG streaming path (see Section 5).

---

## 3. Ingestion Agent

### File: `app/ingestion/pipeline.py`

### Graph Topology

```
START
  |
  v
load_document        <- parsers.py or loaders.py
  |
  v
clean_document       <- cleaners.py
  |
  v
split_document       <- chunkers.py
  |
  v
embed_document       <- embedding_service.py
  |
  v
store_document       <- qdrant_store.py
  |
  v
END
```

### Build and Compile (called once at module import)

```python
def build_ingestion_graph():
    graph = StateGraph(IngestionState)
    graph.add_node("load",  load_document)
    graph.add_node("clean", clean_document)
    graph.add_node("split", split_document)
    graph.add_node("embed", embed_document)
    graph.add_node("store", store_document)
    graph.add_edge(START, "load")
    graph.add_edge("load",  "clean")
    graph.add_edge("clean", "split")
    graph.add_edge("split", "embed")
    graph.add_edge("embed", "store")
    graph.add_edge("store", END)
    return graph.compile()

INGESTION_GRAPH = build_ingestion_graph()  # module-level singleton
```

### Execution

```python
def process_document(document_id: int) -> None:
    with SessionLocal() as database:
        document = database.get(Document, document_id)
        document.status = "processing"
        database.commit()

        initial_state: IngestionState = {
            "document_id": document.id,
            "user_id":     document.user_id,
            "filename":    document.original_filename,
            "file_path":   settings.upload_directory / document.stored_filename,
            "file_type":   document.file_type,
        }
        try:
            result = INGESTION_GRAPH.invoke(initial_state)
            document.status = "ready"
            document.chunk_count = result["stored_count"]
        except Exception:
            document.status = "failed"
            delete_document_points(document.user_id, document.id)
```

### State Lifecycle During Ingestion

```
Initial state:
{
  document_id: 7,
  user_id: 42,
  filename: "research.pdf",
  file_path: Path("uploads/uuid.pdf"),
  file_type: "pdf"
}

After load_document:
{
  document_id: 7, user_id: 42, filename: ..., file_path: ..., file_type: ...,
  pages: [
    { page_number: 1, text: "Chapter 1..." },
    { page_number: 2, text: "Chapter 2..." },
    ...
  ]
}

After clean_document:
{
  ...,
  pages: [
    { page_number: 1, text: "Chapter 1..." },  <- normalized whitespace, no ctrl chars
    ...
  ]
}

After split_document:
{
  ...,
  chunks: [
    { chunk_id: "uuid5-...", document_id: 7, user_id: 42,
      page_number: 1, chunk_index: 0, text: "Chapter 1 text..." },
    { chunk_id: "uuid5-...", document_id: 7, user_id: 42,
      page_number: 1, chunk_index: 1, text: "...continued" },
    ...
  ]
}

After embed_document:
{
  ...,
  embeddings: [
    [0.023, -0.152, ..., 0.044],  <- 384 floats for chunk 0
    [0.011, 0.234, ..., -0.022],  <- 384 floats for chunk 1
    ...
  ]
}

After store_document:
{
  ...,
  stored_count: 47  <- number of points upserted to Qdrant
}
```

---

## 4. RAG Agent

### File: `app/chains/rag_chain.py`

### Graph Topology

```
START
  |
  v
retrieve     <- retriever.py (embed question + Qdrant search)
  |
  v
filter       <- score threshold removal
  |
  v
prompt       <- prompt_builder.py (build system + user prompt)
  |
  v
generate     <- llm_service.py (Ollama generation)
  |
  v
sources      <- collect metadata from retrieved chunks
  |
  v
END
```

### Build and Compile (module-level singleton)

```python
def build_rag_graph():
    graph = StateGraph(RAGState)
    graph.add_node("retrieve", retrieve_context)
    graph.add_node("filter",   filter_context)
    graph.add_node("prompt",   create_prompt)
    graph.add_node("generate", generate_answer)
    graph.add_node("sources",  collect_sources)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "filter")
    graph.add_edge("filter",   "prompt")
    graph.add_edge("prompt",   "generate")
    graph.add_edge("generate", "sources")
    graph.add_edge("sources",  END)
    return graph.compile()

RAG_GRAPH = build_rag_graph()
```

### State Lifecycle During RAG

```
Initial state:
{
  question:             "What are the main themes in chapter 3?",
  conversation_history: [{ role: "user", content: "..." }, ...],
  user_id:              42,
  document_ids:         [7, 12],
  top_k:                None,     <- uses config default (5)
  score_threshold:      0.0,
}

After retrieve:
{
  ...,
  chunks: [
    { chunk_id: "uuid", score: 0.892, user_id: 42, document_id: 7,
      filename: "book.pdf", page_number: 31, chunk_index: 14,
      text: "Chapter 3 explores themes of..." },
    ...  (up to 5 chunks)
  ]
}

After filter:
{
  ...,
  chunks: [...]  <- same or fewer chunks (those above threshold)
}

After prompt:
{
  ...,
  prompt: RAGPrompt(
    system="You are DocuSynth...",
    user="CONVERSATION HISTORY\n...\nDOCUMENT CONTEXT\n...\nCURRENT QUESTION\n..."
  )
}

After generate:
{
  ...,
  answer: "Chapter 3 primarily explores themes of identity [Source 1]..."
}

After sources:
{
  ...,
  sources: [
    { source_number: 1, document_id: 7, filename: "book.pdf",
      page_number: 31, chunk_index: 14, score: 0.892 },
    ...
  ]
}
```

### Conditional Logic in generate Node

```python
def generate_answer(state: RAGState) -> RAGState:
    if not state["chunks"]:
        # Skip LLM call entirely if no relevant chunks found
        return {"answer": NO_CONTEXT_ANSWER}
    prompt = state["prompt"]
    answer = get_llm_service().generate(prompt.user, system_prompt=prompt.system)
    return {"answer": answer}
```

When no chunks are retrieved (or all filtered out), the LLM is never called.
The answer is a deterministic constant string. This prevents:
- Hallucination (LLM cannot invent context it was not given)
- Wasted Ollama inference time
- Confusing responses that mix invented and real content

---

## 5. Streaming Agent (Manual Node Execution)

### File: `app/chains/rag_chain.py` — `stream_rag()` function

For streaming, we cannot use `RAG_GRAPH.invoke()` because it blocks until
the entire generation is complete. Instead, we manually call the non-streaming
nodes, then directly use the LLM's streaming iterator.

```python
def stream_rag(...) -> Iterator[RAGStreamEvent]:
    state = create_initial_state(...)

    # Run non-streaming nodes manually (same as graph would do)
    state.update(retrieve_context(state))
    state.update(filter_context(state))
    state.update(collect_sources(state))

    # Yield sources BEFORE generation starts
    yield {"type": "sources", "sources": state["sources"]}

    # Short-circuit if no context
    if not state["chunks"]:
        yield {"type": "token", "token": NO_CONTEXT_ANSWER}
        yield {"type": "done"}
        return

    # Build prompt (also non-streaming)
    state.update(create_prompt(state))
    prompt = state["prompt"]

    # Stream directly from LLM
    for token in get_llm_service().stream_generate(
        prompt.user,
        system_prompt=prompt.system,
    ):
        yield {"type": "token", "token": token}

    yield {"type": "done"}
```

### Why sources come before tokens

The browser receives sources before any text arrives:

```
SSE events received by browser in order:
  event: sources    <- rendered immediately (sidebar/citation area)
  event: token      <- "Based"  (answer starts appearing)
  event: token      <- " on"
  event: token      <- " the"
  ...
  event: done
```

This is a better UX: users can see which documents were searched before
the answer even starts generating.

### Thread isolation for streaming

The streaming endpoint uses a sync route (not async) because:
1. `ollama.Client.generate(..., stream=True)` is a synchronous iterator
2. FastAPI's `StreamingResponse` with a sync generator runs in a thread pool
3. We cannot share the request-scoped database session with the background thread

Solution: open a new `SessionLocal()` session for saving the assistant message
after streaming completes:

```python
# Inside event_stream() generator, after all tokens are received:
with SessionLocal() as history_database:
    stored_conversation = get_owned_conversation(
        conversation_id, current_user.id, history_database
    )
    save_messages(
        stored_conversation,
        [("assistant", "".join(answer_parts))],
        history_database,
    )
```

---

## 6. Conversational Memory Agent

### File: `app/chains/conversational_rag.py`

This is not a LangGraph agent — it is a stateless helper that prepares the
conversation history for injection into the RAG agent's state.

```
PostgreSQL messages
    |
    v  (load_conversation_memory)
Recent N messages (DB query, user-isolated)
    |
    v  (trim_conversation_history)
Bounded list of ConversationMemoryMessage dicts
    |
    v  (inject into RAGState.conversation_history)
RAG agent initial state
    |
    v  (build_conversation_history in prompt_builder.py)
Formatted string in user prompt
```

The memory agent is called BEFORE the RAG graph runs, enriching the initial
state with history before the graph starts.

---

## 7. State TypedDicts Reference

### IngestionState

```python
class IngestionState(TypedDict, total=False):
    document_id  : int          # set by caller
    user_id      : int          # set by caller
    filename     : str          # set by caller (original filename)
    file_path    : Path         # set by caller
    file_type    : str          # set by caller ("pdf" or "txt")
    pages        : list[ExtractedPage]    # set by load_document
    chunks       : list[DocumentChunk]   # set by split_document
    embeddings   : list[list[float]]     # set by embed_document
    stored_count : int                   # set by store_document
```

### RAGState

```python
class RAGState(TypedDict, total=False):
    question              : str                          # set by caller
    conversation_history  : Sequence[ConversationMemoryMessage]  # set by caller
    user_id               : int                          # set by caller
    document_ids          : Sequence[int] | None         # set by caller
    top_k                 : int | None                   # set by caller
    score_threshold       : float                        # set by caller
    chunks                : list[RetrievedChunk]         # set by retrieve node
    prompt                : RAGPrompt                    # set by prompt node
    answer                : str                          # set by generate node
    sources               : list[RAGSource]              # set by sources node
```

### ExtractedPage

```python
class ExtractedPage(TypedDict):
    page_number : int
    text        : str
```

### DocumentChunk

```python
class DocumentChunk(TypedDict):
    chunk_id    : str   # uuid5 deterministic ID
    document_id : int
    user_id     : int
    page_number : int
    chunk_index : int
    text        : str
```

### RetrievedChunk

```python
class RetrievedChunk(TypedDict):
    chunk_id    : str
    score       : float   # cosine similarity score
    user_id     : int
    document_id : int
    filename    : str
    page_number : int
    chunk_index : int
    text        : str
```

### RAGSource (API-facing)

```python
class RAGSource(TypedDict):
    source_number : int
    document_id   : int
    filename      : str
    page_number   : int
    chunk_index   : int
    score         : float
```

### ConversationMemoryMessage

```python
class ConversationMemoryMessage(TypedDict):
    role    : Literal["user", "assistant"]
    content : str
```

---

## 8. Node Reference

### Ingestion Nodes

| Node | Function | Input Keys | Output Keys | External Service |
|---|---|---|---|---|
| load | load_document | document_id, file_path, file_type | pages | PyMuPDF or LangChain TextLoader |
| clean | clean_document | pages | pages | (regex/string operations) |
| split | split_document | pages, document_id, user_id | chunks | tiktoken, LangChain splitter |
| embed | embed_document | chunks | embeddings | HuggingFace BGE model |
| store | store_document | chunks, embeddings, filename | stored_count | Qdrant HTTP API |

### RAG Nodes

| Node | Function | Input Keys | Output Keys | External Service |
|---|---|---|---|---|
| retrieve | retrieve_context | question, user_id, document_ids, top_k | chunks | BGE model + Qdrant |
| filter | filter_context | chunks, score_threshold | chunks | (none) |
| prompt | create_prompt | question, chunks, conversation_history | prompt | (none) |
| generate | generate_answer | chunks, prompt | answer | Ollama HTTP API |
| sources | collect_sources | chunks | sources | (none) |

---

## 9. Adding New Nodes

### Example: Add a reranker node between filter and prompt

**Step 1: Create the node function**

```python
# app/retrieval/reranker.py
from sentence_transformers import CrossEncoder

def rerank_chunks(state: RAGState) -> RAGState:
    """Rerank retrieved chunks using a cross-encoder for better precision."""
    if not state["chunks"]:
        return {"chunks": []}

    model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    question = state["question"]
    chunks = state["chunks"]

    pairs = [[question, chunk["text"]] for chunk in chunks]
    scores = model.predict(pairs)

    # Sort by cross-encoder score (descending)
    reranked = sorted(
        zip(scores, chunks),
        key=lambda x: x[0],
        reverse=True
    )
    return {"chunks": [chunk for _, chunk in reranked]}
```

**Step 2: Register the node and update edges**

```python
# app/chains/rag_chain.py
from app.retrieval.reranker import rerank_chunks

def build_rag_graph():
    graph = StateGraph(RAGState)
    graph.add_node("retrieve", retrieve_context)
    graph.add_node("filter",   filter_context)
    graph.add_node("rerank",   rerank_chunks)      # NEW NODE
    graph.add_node("prompt",   create_prompt)
    graph.add_node("generate", generate_answer)
    graph.add_node("sources",  collect_sources)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "filter")
    graph.add_edge("filter",   "rerank")            # NEW EDGE
    graph.add_edge("rerank",   "prompt")            # CHANGED EDGE
    graph.add_edge("prompt",   "generate")
    graph.add_edge("generate", "sources")
    graph.add_edge("sources",  END)
    return graph.compile()
```

**Step 3: Update stream_rag() for manual execution**

```python
def stream_rag(...):
    state.update(retrieve_context(state))
    state.update(filter_context(state))
    state.update(rerank_chunks(state))     # NEW LINE
    state.update(collect_sources(state))
    ...
```

No other code changes needed.

---

## 10. Replacing Nodes

### Replace the embedding model (e.g., OpenAI text-embedding-3-small)

```python
# app/embeddings/embedding_service.py

import openai

@lru_cache(maxsize=1)
def load_model():
    # Return a wrapper that implements the same interface
    return OpenAIEmbedder()

class OpenAIEmbedder:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        response = openai.embeddings.create(
            model="text-embedding-3-small",
            input=texts
        )
        return [item.embedding for item in response.data]

    def embed_query(self, question: str) -> list[float]:
        response = openai.embeddings.create(
            model="text-embedding-3-small",
            input=question
        )
        return response.data[0].embedding
```

Update `EMBEDDING_DIMENSION=1536` in `.env`.
Recreate Qdrant collection (dimension change requires recreation).
Re-process all documents.

The `embed_text`, `embed_texts`, and `embed_query` functions in `embedding_service.py`
remain the same interface — only the model backend changes.

### Replace the LLM (e.g., Anthropic Claude)

```python
# app/generation/llm_service.py

import anthropic

class AnthropicLLM:
    def __init__(self, model: str, max_tokens: int, temperature: float):
        self.client = anthropic.Anthropic()
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        message = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_prompt or "",
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text.strip()

    def stream_generate(self, prompt: str, system_prompt: str | None = None):
        with self.client.messages.stream(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_prompt or "",
            messages=[{"role": "user", "content": prompt}]
        ) as stream:
            for text in stream.text_stream:
                yield text

@lru_cache(maxsize=1)
def get_llm_service() -> LLMProvider:
    settings = get_settings()
    return AnthropicLLM(
        model="claude-3-5-haiku-20241022",
        max_tokens=settings.llm_max_tokens,
        temperature=settings.llm_temperature,
    )
```

No changes to rag_chain.py, chat.py, or any other file.

---

## 11. Why LangGraph and Not Plain Functions

### Option A: Plain function chain

```python
def process_document(document_id):
    document = load_db(document_id)
    pages = extract_pages(document.file_path, document.file_type)
    clean_pages = clean_text(pages)
    chunks = split_into_chunks(clean_pages, document_id)
    embeddings = embed_chunks(chunks)
    count = store_in_qdrant(chunks, embeddings)
    update_db(document_id, status="ready", chunk_count=count)
```

### Option B: LangGraph graph

```python
INGESTION_GRAPH = build_ingestion_graph()

def process_document(document_id):
    state = create_initial_state(document_id)
    result = INGESTION_GRAPH.invoke(state)
    update_db(document_id, status="ready", chunk_count=result["stored_count"])
```

### Why Option B is better for this project

| Property | Plain functions | LangGraph |
|---|---|---|
| Explicit state passing | No (variables in scope) | Yes (TypedDict) |
| Type safety | Partial | Full (TypedDict keys) |
| Inspectable at runtime | Hard | graph.get_graph().print_ascii() |
| Add conditional routing | Refactor needed | add_conditional_edges() |
| Visualize workflow | Manual diagram | Built-in mermaid export |
| Consistent pattern | No | Same pattern for ingestion + RAG |
| Educational value | Less | Shows how production pipelines work |

For a learning project that will be presented, the explicit graph structure
makes the architecture visible and self-documenting.

---

## 12. Future Agent Capabilities

### Multi-query Retrieval

Instead of one embedding for the question, generate multiple query variations
and merge their results:

```python
def multi_query_retrieve(state: RAGState) -> RAGState:
    """Generate N query variations and retrieve chunks for each."""
    queries = generate_query_variations(state["question"], n=3)
    all_chunks = []
    seen_ids = set()
    for query in queries:
        chunks = retrieve_chunks(query, state["user_id"], state["document_ids"])
        for chunk in chunks:
            if chunk["chunk_id"] not in seen_ids:
                all_chunks.append(chunk)
                seen_ids.add(chunk["chunk_id"])
    return {"chunks": all_chunks}
```

### Self-Correction Agent

Add a verification node that checks the generated answer against the sources:

```python
def verify_answer(state: RAGState) -> RAGState:
    """Ask the LLM to verify that the answer is grounded in the retrieved context."""
    verification_prompt = build_verification_prompt(state["answer"], state["chunks"])
    verdict = get_llm_service().generate(verification_prompt)
    if "UNGROUNDED" in verdict:
        # Regenerate with a more conservative prompt
        state["prompt"] = build_conservative_prompt(state["question"], state["chunks"])
        return generate_answer(state)
    return {}  # No change to state
```

### Adaptive Retrieval

Use a conditional edge to retrieve more chunks if the initial results are low quality:

```python
def should_retrieve_more(state: RAGState) -> str:
    max_score = max((c["score"] for c in state["chunks"]), default=0)
    if max_score < 0.5:
        return "retrieve_more"
    return "prompt"

graph.add_conditional_edges(
    "filter",
    should_retrieve_more,
    {"retrieve_more": "retrieve", "prompt": "prompt"}
)
```

---

*Document version: Phase 28 complete*
*Last updated: 2026-09-24*
