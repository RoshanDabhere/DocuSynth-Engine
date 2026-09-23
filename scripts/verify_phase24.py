"""Run a disposable real-service verification of the Phase 24 SSE stream."""

import json
from contextlib import suppress
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from scripts.verify_phase23 import (
    VERIFICATION_TEXT,
    bearer_headers,
    remove_test_users,
    require_success,
)


def main() -> None:
    """Verify real ingestion followed by retrieval-backed Ollama token streaming."""
    email = f"phase24-stream-{uuid4().hex}@example.com"
    document_id: int | None = None
    headers: dict[str, str] | None = None

    try:
        with TestClient(app) as client:
            require_success(
                client.post(
                    "/auth/register",
                    json={
                        "name": "Phase 24 Stream",
                        "email": email,
                        "password": "Verify-Stream-742",
                    },
                ),
                201,
            )
            login = require_success(
                client.post(
                    "/auth/login",
                    json={"email": email, "password": "Verify-Stream-742"},
                ),
                200,
            )
            headers = bearer_headers(login["access_token"])
            upload = require_success(
                client.post(
                    "/documents/upload",
                    headers=headers,
                    files={
                        "file": (
                            "phase24-stream.txt",
                            VERIFICATION_TEXT.encode("utf-8"),
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
            if document["status"] != "ready":
                raise RuntimeError(f"Document ingestion did not complete: {document}")

            events: list[tuple[str, dict]] = []
            current_event = "message"
            with client.stream(
                "POST",
                "/chat/query/stream",
                headers=headers,
                json={
                    "question": "What is the launch verification code?",
                    "selected_document_ids": [document_id],
                },
            ) as response:
                if response.status_code != 200:
                    raise RuntimeError(
                        f"Streaming endpoint returned HTTP {response.status_code}: "
                        f"{response.read().decode('utf-8')}"
                    )
                if not response.headers["content-type"].startswith("text/event-stream"):
                    raise RuntimeError("Streaming endpoint did not return an SSE content type")

                for line in response.iter_lines():
                    if line.startswith("event:"):
                        current_event = line.removeprefix("event:").strip()
                    elif line.startswith("data:"):
                        events.append(
                            (
                                current_event,
                                json.loads(line.removeprefix("data:").strip()),
                            )
                        )

            token_events = [data["token"] for event, data in events if event == "token"]
            source_events = [data["sources"] for event, data in events if event == "sources"]
            answer = "".join(token_events)
            if "ORBIT-742" not in answer:
                raise RuntimeError(f"Streamed answer was not grounded as expected: {answer}")
            if not source_events or source_events[0][0]["document_id"] != document_id:
                raise RuntimeError("Streamed sources did not match the selected document")
            if not any(event == "done" for event, _data in events):
                raise RuntimeError("The stream did not send its terminal done event")
            if len(token_events) < 2:
                raise RuntimeError("The answer was not delivered progressively")

            require_success(
                client.delete(f"/documents/{document_id}", headers=headers),
                204,
            )
            document_id = None
            print("phase24_streaming=passed")
            print(f"token_event_count={len(token_events)}")
            print(f"answer_preview={answer[:200]}")
            print(f"source_count={len(source_events[0])}")
    finally:
        if document_id is not None and headers is not None:
            with suppress(Exception):
                with TestClient(app) as cleanup_client:
                    cleanup_client.delete(f"/documents/{document_id}", headers=headers)
        remove_test_users([email])


if __name__ == "__main__":
    main()
