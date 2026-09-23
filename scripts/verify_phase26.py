"""Run a disposable real-service verification of Phase 26 conversation memory."""

import json
from contextlib import suppress
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from scripts.verify_phase23 import bearer_headers, remove_test_users, require_success

MEMORY_DOCUMENT = """Project Aurora was founded by Dr. Mira Sen in Jaipur.
The verification code associated with Project Aurora is ORBIT-742.
These facts are used to verify follow-up questions with conversational references.
"""


def read_sse_events(response) -> list[tuple[str, dict]]:
    """Parse named JSON events from a streaming response."""
    events: list[tuple[str, dict]] = []
    current_event = "message"
    for line in response.iter_lines():
        if line.startswith("event:"):
            current_event = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            events.append(
                (current_event, json.loads(line.removeprefix("data:").strip()))
            )
    return events


def main() -> None:
    """Verify pronoun-aware synchronous and streaming follow-up answers."""
    suffix = uuid4().hex
    email = f"phase26-{suffix}@example.com"
    document_id: int | None = None
    headers: dict[str, str] | None = None

    try:
        with TestClient(app) as client:
            require_success(
                client.post(
                    "/auth/register",
                    json={
                        "name": "Phase 26 Memory",
                        "email": email,
                        "password": "Memory-Verify-742",
                    },
                ),
                201,
            )
            login = require_success(
                client.post(
                    "/auth/login",
                    json={"email": email, "password": "Memory-Verify-742"},
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
                            "phase26-memory.txt",
                            MEMORY_DOCUMENT.encode("utf-8"),
                            "text/plain",
                        )
                    },
                ),
                201,
            )
            document_id = int(upload["id"])

            first = require_success(
                client.post(
                    "/chat/query",
                    headers=headers,
                    json={
                        "question": "Who founded Project Aurora?",
                        "selected_document_ids": [document_id],
                    },
                ),
                200,
            )
            if "Mira" not in first["answer"]:
                raise RuntimeError(f"First answer did not identify Mira: {first['answer']}")
            conversation_id = int(first["conversation_id"])

            second = require_success(
                client.post(
                    "/chat/query",
                    headers=headers,
                    json={
                        "question": "In which city did she found it?",
                        "selected_document_ids": [document_id],
                        "conversation_id": conversation_id,
                    },
                ),
                200,
            )
            if "Jaipur" not in second["answer"]:
                raise RuntimeError(
                    f"Synchronous follow-up did not resolve the reference: {second['answer']}"
                )

            with client.stream(
                "POST",
                "/chat/query/stream",
                headers=headers,
                json={
                    "question": "What verification code is associated with that project?",
                    "selected_document_ids": [document_id],
                    "conversation_id": conversation_id,
                },
            ) as response:
                if response.status_code != 200:
                    raise RuntimeError(f"Streaming follow-up failed: {response.status_code}")
                events = read_sse_events(response)

            streamed_answer = "".join(
                data["token"] for event, data in events if event == "token"
            )
            if "ORBIT-742" not in streamed_answer:
                raise RuntimeError(
                    "Streaming follow-up did not use conversation memory: "
                    f"{streamed_answer}"
                )

            history = require_success(
                client.get(
                    f"/chat/conversations/{conversation_id}",
                    headers=headers,
                ),
                200,
            )
            if len(history["messages"]) != 6:
                raise RuntimeError(f"Expected six persisted messages: {history}")

            require_success(
                client.delete(f"/documents/{document_id}", headers=headers),
                204,
            )
            document_id = None
            print("phase26_memory=passed")
            print(f"conversation_id={conversation_id}")
            print("sync_reference_resolution=Mira->Jaipur")
            print("stream_reference_resolution=Project Aurora->ORBIT-742")
            print("bounded_memory_configuration=passed")
    finally:
        if document_id is not None and headers is not None:
            with suppress(Exception):
                with TestClient(app) as cleanup_client:
                    cleanup_client.delete(f"/documents/{document_id}", headers=headers)
        remove_test_users([email])


if __name__ == "__main__":
    main()
