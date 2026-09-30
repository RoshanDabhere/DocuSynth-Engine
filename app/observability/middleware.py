"""Request-scoped context and middleware for traceability."""

import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

REQUEST_ID_HEADER = "X-Request-ID"


def get_request_id() -> str | None:
    """Return the current request's correlation ID, or None outside a request."""
    return _request_id.get()


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID to every request/response cycle.

    If the client sends an ``X-Request-ID`` header, it is reused
    (useful for frontend→backend tracing). Otherwise a UUID4 is
    generated. The ID is:

    1. Stored in a ``ContextVar`` so all loggers in the call chain
       can include it automatically.
    2. Returned to the client as an ``X-Request-ID`` response header.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:16]
        token = _request_id.set(request_id)
        try:
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            _request_id.reset(token)
