"""Run a disposable real-service verification of Phase 28 document management."""

from contextlib import suppress
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.vector_store.qdrant_store import get_qdrant_client, user_filter
from scripts.verify_phase23 import bearer_headers, remove_test_users, require_success

DOCUMENT_TEXT = """Phase 28 document management verification.
The library record should become ready, searchable, and fully deletable.
The verification marker is LIBRARY-928.
"""


def count_user_points(user_id: int) -> int:
    """Count only the disposable user's Qdrant points."""
    settings = get_settings()
    return get_qdrant_client().count(
        collection_name=settings.qdrant_collection,
        count_filter=user_filter(user_id),
        exact=True,
    ).count


def main() -> None:
    """Verify validation, upload processing, listing, and complete deletion."""
    suffix = uuid4().hex
    email = f"phase28-{suffix}@example.com"
    headers: dict[str, str] | None = None
    document_id: int | None = None

    try:
        with TestClient(app) as client:
            require_success(
                client.post(
                    "/auth/register",
                    json={
                        "name": "Phase 28 Documents",
                        "email": email,
                        "password": "Documents-Verify-928",
                    },
                ),
                201,
            )
            login = require_success(
                client.post(
                    "/auth/login",
                    json={"email": email, "password": "Documents-Verify-928"},
                ),
                200,
            )
            headers = bearer_headers(login["access_token"])
            user = require_success(client.get("/auth/me", headers=headers), 200)

            rejected = client.post(
                "/documents/upload",
                headers=headers,
                files={"file": ("unsupported.docx", b"not supported", "application/octet-stream")},
            )
            if rejected.status_code != 400:
                raise RuntimeError(f"Unsupported upload was not rejected: {rejected.status_code}")

            upload = require_success(
                client.post(
                    "/documents/upload",
                    headers=headers,
                    files={
                        "file": (
                            "phase28-library.txt",
                            DOCUMENT_TEXT.encode("utf-8"),
                            "text/plain",
                        )
                    },
                ),
                201,
            )
            document_id = int(upload["id"])
            document = require_success(
                client.get(f"/documents/{document_id}", headers=headers),
                200,
            )
            if document["status"] != "ready" or document["chunk_count"] < 1:
                raise RuntimeError(f"Document did not become ready: {document}")

            documents = require_success(client.get("/documents", headers=headers), 200)
            if [item["id"] for item in documents] != [document_id]:
                raise RuntimeError(f"Document library listing is incorrect: {documents}")
            points_before_delete = count_user_points(int(user["id"]))
            if points_before_delete < 1:
                raise RuntimeError("Ready document has no searchable Qdrant points")

            require_success(
                client.delete(f"/documents/{document_id}", headers=headers),
                204,
            )
            document_id = None
            if require_success(client.get("/documents", headers=headers), 200):
                raise RuntimeError("Deleted document remains in the library")
            if count_user_points(int(user["id"])) != 0:
                raise RuntimeError("Deleted document remains in Qdrant")

            print("phase28_documents=passed")
            print("unsupported_upload_rejection=passed")
            print("upload_to_ready=passed")
            print(f"qdrant_points_before_delete={points_before_delete}")
            print("postgres_qdrant_file_delete=passed")
    finally:
        if document_id is not None and headers is not None:
            with suppress(Exception):
                with TestClient(app) as cleanup_client:
                    cleanup_client.delete(f"/documents/{document_id}", headers=headers)
        remove_test_users([email])


if __name__ == "__main__":
    main()
