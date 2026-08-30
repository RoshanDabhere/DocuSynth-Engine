"""Authenticated document upload and management endpoints."""

from pathlib import Path

import aiofiles
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status
from sqlalchemy import select

from app.api.dependencies import CurrentUser, DatabaseSession
from app.config import get_settings
from app.ingestion.pipeline import process_document
from app.models.documents import Document
from app.schemas.document import DocumentResponse
from app.utils.file_utils import create_stored_filename, remove_file
from app.utils.validators import validate_file_header, validate_upload_metadata
from app.vector_store.qdrant_store import delete_document_points

router = APIRouter(prefix="/documents", tags=["Documents"])
READ_CHUNK_SIZE = 1024 * 1024


def get_owned_document(document_id: int, user_id: int, database: DatabaseSession) -> Document:
    """Return a document only when it belongs to the authenticated user."""
    document = database.scalar(
        select(Document).where(Document.id == document_id, Document.user_id == user_id)
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    database: DatabaseSession,
    file: UploadFile = File(...),
) -> Document:
    """Validate, store, and record one PDF or TXT upload."""
    settings = get_settings()
    try:
        original_filename, extension = validate_upload_metadata(file.filename, file.content_type)
        first_chunk = await file.read(READ_CHUNK_SIZE)
        validate_file_header(extension, first_chunk)
    except ValueError as error:
        await file.close()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error

    upload_directory = settings.upload_directory.resolve()
    upload_directory.mkdir(parents=True, exist_ok=True)
    stored_filename = create_stored_filename(extension)
    stored_path = upload_directory / stored_filename
    file_size = 0

    try:
        async with aiofiles.open(stored_path, "wb") as destination:
            chunk = first_chunk
            while chunk:
                file_size += len(chunk)
                if file_size > settings.max_upload_size_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="File exceeds the upload size limit",
                    )
                await destination.write(chunk)
                chunk = await file.read(READ_CHUNK_SIZE)
    except Exception:
        remove_file(stored_path)
        raise
    finally:
        await file.close()

    document = Document(
        user_id=current_user.id,
        original_filename=original_filename,
        stored_filename=stored_filename,
        file_type=extension.removeprefix("."),
        file_size=file_size,
        status="uploaded",
    )
    try:
        database.add(document)
        database.commit()
        database.refresh(document)
    except Exception:
        database.rollback()
        remove_file(stored_path)
        raise
    background_tasks.add_task(process_document, document.id)
    return document


@router.get("", response_model=list[DocumentResponse])
def list_documents(current_user: CurrentUser, database: DatabaseSession) -> list[Document]:
    """List documents owned by the authenticated user."""
    return list(
        database.scalars(
            select(Document)
            .where(Document.user_id == current_user.id)
            .order_by(Document.created_at.desc())
        )
    )


@router.get("/{document_id}", response_model=DocumentResponse)
def read_document(
    document_id: int,
    current_user: CurrentUser,
    database: DatabaseSession,
) -> Document:
    """Return one user-owned document."""
    return get_owned_document(document_id, current_user.id, database)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    current_user: CurrentUser,
    database: DatabaseSession,
) -> None:
    """Delete a user-owned document record and its stored file."""
    document = get_owned_document(document_id, current_user.id, database)
    stored_path = Path(get_settings().upload_directory).resolve() / document.stored_filename
    delete_document_points(current_user.id, document.id)
    database.delete(document)
    database.commit()
    remove_file(stored_path)
