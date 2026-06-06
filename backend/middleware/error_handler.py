import json
import logging
import traceback


class AppError(Exception):
    def __init__(self, code: int, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _json_response(status_code: int, body: dict) -> tuple[dict, dict]:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    start_message = {
        "type": "http.response.start",
        "status": status_code,
        "headers": [
            (b"content-type", b"application/json; charset=utf-8"),
            (b"content-length", str(len(payload)).encode("ascii")),
        ],
    }
    body_message = {"type": "http.response.body", "body": payload, "more_body": False}
    return start_message, body_message


class ErrorHandlerMiddleware:
    """Pure ASGI error handler.

    Implemented at the ASGI layer (not as BaseHTTPMiddleware) because
    BaseHTTPMiddleware buffers streaming responses, which breaks SSE.
    Exceptions raised BEFORE the response starts get converted to a JSON
    envelope; exceptions during a streaming response are re-raised (cannot
    rewrite headers once they've been sent).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_wrapper(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except AppError as exc:
            if response_started:
                raise
            start, body = _json_response(
                exc.status_code,
                {"code": exc.code, "data": None, "message": exc.message},
            )
            await send(start)
            await send(body)
        except Exception as exc:  # noqa: BLE001
            logging.error(f"Unhandled exception: {exc}\n{traceback.format_exc()}")
            if response_started:
                raise
            start, body = _json_response(
                500,
                {"code": 50000, "data": None, "message": "内部服务错误"},
            )
            await send(start)
            await send(body)
