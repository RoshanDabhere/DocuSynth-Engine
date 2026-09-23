"""Run a disposable real-service verification of Phase 25 conversation history."""

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


def read_sse_events(response) -> list[tuple[str, dict]]:
    """Parse the named JSON events returned by the streaming endpoint."""
    events: list[tuple[str, dict]] = []
    current_event = "message"
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
    return events


def main() -> None:
    """Verify owned multi-turn history for normal and streamed chat requests."""
    suffix = uuid4().hex
    owner_email = f"phase25-owner-{suffix}@example.com"
    outsider_email = f"phase25-outsider-{suffix}@example.com"
    emails = [owner_email, outsider_email]
    document_id: int | None = None
    owner_headers: dict[str, str] | None = None

    try:
        with TestClient(app) as client:
            for name, email in (
                ("Phase 25 Owner", owner_email),
                ("Phase 25 Outsider", outsider_email),
            ):
                require_success(
                    client.post(
                        "/auth/register",
                        json={"name": name, "email": email, "password": "History-Verify-742"},
                    ),
                    201,
                )

            owner_login = require_success(
                client.post(
                    "/auth/login",
                    json={"email": owner_email, "password": "History-Verify-742"},
                ),
                200,
            )
            outsider_login = require_success(
                client.post(
                    "/auth/login",
                    json={"email": outsider_email, "password": "History-Verify-742"},
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
                            "phase25-history.txt",
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
            if document["status"] != "ready":
                raise RuntimeError(f"Document ingestion did not complete: {document}")

            first_answer = require_success(
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
            conversation_id = int(first_answer["conversation_id"])

            second_answer = require_success(
                client.post(
                    "/chat/query",
                    headers=owner_headers,
                    json={
                        "question": "What is the project codename?",
                        "selected_document_ids": [document_id],
                        "conversation_id": conversation_id,
                    },
                ),
                200,
            )
            if second_answer["conversation_id"] != conversation_id:
                raise RuntimeError("A follow-up query created a different conversation")

            with client.stream(
                "POST",
                "/chat/query/stream",
                headers=owner_headers,
                json={
                    "question": "Repeat the launch verification code.",
                    "selected_document_ids": [document_id],
                    "conversation_id": conversation_id,
                },
            ) as response:
                if response.status_code != 200:
                    raise RuntimeError(
                        f"Streaming history request failed: HTTP {response.status_code}"
                    )
                stream_events = read_sse_events(response)

            done_events = [data for event, data in stream_events if event == "done"]
            if not done_events or done_events[-1]["conversation_id"] != conversation_id:
                raise RuntimeError("The stream did not return the persisted conversation ID")

            conversations = require_success(
                client.get("/chat/conversations", headers=owner_headers),
                200,
            )
            if len(conversations) != 1 or conversations[0]["id"] != conversation_id:
                raise RuntimeError(f"Conversation list was incorrect: {conversations}")

            history = require_success(
                client.get(
                    f"/chat/conversations/{conversation_id}",
                    headers=owner_headers,
                ),
                200,
            )
            expected_roles = ["user", "assistant", "user", "assistant", "user", "assistant"]
            actual_roles = [message["role"] for message in history["messages"]]
            if actual_roles != expected_roles:
                raise RuntimeError(f"Message order was incorrect: {actual_roles}")
            if "ORBIT-742" not in history["messages"][-1]["content"]:
                raise RuntimeError("The streamed assistant answer was not persisted")

            outsider_history = client.get(
                f"/chat/conversations/{conversation_id}",
                headers=outsider_headers,
            )
            if outsider_history.status_code != 404:
                raise RuntimeError(
                    "Conversation ownership isolation failed: "
                    f"HTTP {outsider_history.status_code}"
                )

            require_success(
                client.delete(f"/documents/{document_id}", headers=owner_headers),
                204,
            )
            document_id = None
            print("phase25_history=passed")
            print(f"conversation_id={conversation_id}")
            print(f"message_count={len(history['messages'])}")
            print("roles=user,assistant,user,assistant,user,assistant")
            print("conversation_isolation=passed")
    finally:
        if document_id is not None and owner_headers is not None:
            with suppress(Exception):
                with TestClient(app) as cleanup_client:
                    cleanup_client.delete(f"/documents/{document_id}", headers=owner_headers)
        remove_test_users(emails)


if __name__ == "__main__":
    main()
