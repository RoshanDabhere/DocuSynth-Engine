"""Run a disposable end-to-end verification of the Phase 23 RAG API."""

from contextlib import suppress
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database.connection import SessionLocal
from app.main import app
from app.models.user import User

VERIFICATION_TEXT = (
    "DocuSynth end-to-end verification document. "
    "The launch verification code is ORBIT-742. "
    "The project codename is Aurora."
)


def require_success(response, expected_status: int) -> dict:
    """Require an HTTP status and return a JSON object when present."""
    if response.status_code != expected_status:
        raise RuntimeError(
            f"Expected HTTP {expected_status}, received {response.status_code}: "
            f"{response.text}"
        )
    if not response.content:
        return {}
    return response.json()


def bearer_headers(token: str) -> dict[str, str]:
    """Build an authenticated API header without logging the token."""
    return {"Authorization": f"Bearer {token}"}


def remove_test_users(emails: list[str]) -> None:
    """Remove only the disposable users created by this verification run."""
    with SessionLocal() as database:
        users = database.scalars(select(User).where(User.email.in_(emails))).all()
        for user in users:
            database.delete(user)
        database.commit()


def main() -> None:
    """Verify authentication, ingestion, retrieval, generation, and isolation."""
    unique_suffix = uuid4().hex
    owner_email = f"phase23-owner-{unique_suffix}@example.com"
    outsider_email = f"phase23-outsider-{unique_suffix}@example.com"
    test_emails = [owner_email, outsider_email]
    document_id: int | None = None
    owner_headers: dict[str, str] | None = None

    try:
        with TestClient(app) as client:
            for name, email in (
                ("Phase 23 Owner", owner_email),
                ("Phase 23 Outsider", outsider_email),
            ):
                require_success(
                    client.post(
                        "/auth/register",
                        json={"name": name, "email": email, "password": "Verify-Only-742"},
                    ),
                    201,
                )

            owner_login = require_success(
                client.post(
                    "/auth/login",
                    json={"email": owner_email, "password": "Verify-Only-742"},
                ),
                200,
            )
            outsider_login = require_success(
                client.post(
                    "/auth/login",
                    json={"email": outsider_email, "password": "Verify-Only-742"},
                ),
                200,
            )
            owner_headers = bearer_headers(owner_login["access_token"])
            outsider_headers = bearer_headers(outsider_login["access_token"])

            upload = require_success(
                client.post(
                    "/documents/upload",
                    headers=owner_headers,
                    files={
                        "file": (
                            "phase23-verification.txt",
                            VERIFICATION_TEXT.encode("utf-8"),
                            "text/plain",
                        )
                    },
                ),
                201,
            )
            document_id = int(upload["id"])

            document = require_success(
                client.get(f"/documents/{document_id}", headers=owner_headers),
                200,
            )
            if document["status"] != "ready" or document["chunk_count"] < 1:
                raise RuntimeError(f"Document ingestion did not complete: {document}")

            chat = require_success(
                client.post(
                    "/chat/query",
                    headers=owner_headers,
                    json={
                        "question": "What is the launch verification code?",
                        "selected_document_ids": [document_id],
                    },
                ),
                200,
            )
            if not chat["sources"]:
                raise RuntimeError("The RAG answer did not include retrieval-backed sources")
            if any(source["document_id"] != document_id for source in chat["sources"]):
                raise RuntimeError("The RAG answer returned a source from another document")

            outsider_query = client.post(
                "/chat/query",
                headers=outsider_headers,
                json={
                    "question": "What is the launch verification code?",
                    "selected_document_ids": [document_id],
                },
            )
            if outsider_query.status_code != 404:
                raise RuntimeError(
                    "Document ownership isolation failed: "
                    f"HTTP {outsider_query.status_code} {outsider_query.text}"
                )

            require_success(
                client.delete(f"/documents/{document_id}", headers=owner_headers),
                204,
            )
            document_id = None

            print("phase23_end_to_end=passed")
            print(f"answer_preview={chat['answer'][:200]}")
            print(f"source_count={len(chat['sources'])}")
            print("ownership_isolation=passed")
    finally:
        if document_id is not None and owner_headers is not None:
            with suppress(Exception):
                with TestClient(app) as cleanup_client:
                    cleanup_client.delete(
                        f"/documents/{document_id}",
                        headers=owner_headers,
                    )
        remove_test_users(test_emails)


if __name__ == "__main__":
    main()
