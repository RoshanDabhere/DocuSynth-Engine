# DocuSynth Engine — Recovery and Continuation Guide

Last updated: 2026-08-31

## Current position

- Repository: `https://github.com/RoshanDabhere/DocuSynth-Engine.git`
- Current branch: `testing`
- Completed phases: 0 through 22
- Next phase: 23 — Chat API
- Phase 21 and 22 currently have uncommitted local changes.
- Resume instruction for Codex: `Read PROJECT_HANDOFF.md, analyze the current project with GitNexus, and continue Phase 23.`

## What is complete

- FastAPI application and environment configuration
- PostgreSQL connection, users, documents, JWT authentication, and upload API
- PDF and TXT extraction
- Text cleaning and token-aware chunking
- CUDA-enabled BGE embeddings (`BAAI/bge-small-en-v1.5`, 384 dimensions)
- Qdrant collection, payloads, user isolation, storage, and deletion
- LangGraph document-ingestion workflow
- User-filtered semantic retrieval with configurable Top-K
- Replaceable Ollama LLM service using `gemma3:4b`
- Grounded RAG prompt with trusted source labels
- Complete LangGraph RAG chain with score filtering, answers, and sources

## What remains

- Phase 23: Chat API
- Phase 24: Streaming API responses
- Phase 25: Conversation and message database models
- Phase 26: Conversation memory
- Phase 27: Chat frontend
- Phase 28: Document frontend
- Phase 29: Source citation UI
- Phases 30–36: quality, performance, security, errors, logging, testing, evaluation
- Phases 37–39: Docker deployment, README, and presentation preparation

## Before formatting Windows

### 1. Save code to GitHub

Run these commands from the project directory:

```powershell
git status
git add .
git status
git commit -m "Complete RAG pipeline through phase 22"
git push -u origin testing
```

Before committing, confirm `.env` is **not** listed under staged files. Never push `.env`.

### 2. Back up local-only files securely

Copy these outside the computer or into encrypted storage:

- `.env` — contains database and JWT secrets
- `uploads/` — uploaded documents, if needed
- PostgreSQL database backup, if it contains useful data

Do not upload `.env` to GitHub or public cloud storage.

### 3. Understand data that will be lost

- The current Qdrant container has no persistent host mount. Its vectors will be erased when Docker data is removed.
- This is recoverable: after reinstalling, upload/process the documents again to regenerate embeddings.
- Ollama models are local and must be downloaded again.
- The Python `.venv` should not be backed up; recreate it from `requirements.txt`.

## Restore after formatting

Install Git, Python 3.12, PostgreSQL, Node.js, Docker Desktop, Ollama, and VS Code. Then run:

```powershell
git clone https://github.com/RoshanDabhere/DocuSynth-Engine.git
cd DocuSynth-Engine
git switch testing
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Restore the secret values in `.env` from the secure backup.

Start Qdrant:

```powershell
docker run -d --name qdrant -p 6333:6333 -p 6334:6334 -v qdrant_storage:/qdrant/storage qdrant/qdrant
```

The named volume makes future Qdrant data persistent.

Restore Ollama:

```powershell
ollama pull gemma3:4b
ollama serve
```

Run the backend:

```powershell
uvicorn app.main:app --reload
```

Verify:

- API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- Qdrant: `http://localhost:6333/dashboard`

## GitNexus after restore

Reinstall/run GitNexus and index the repository before editing:

```powershell
corepack pnpm --allow-build=@ladybugdb/core --allow-build=gitnexus --allow-build=tree-sitter dlx gitnexus@latest analyze
```

Then continue with Phase 23.
