from fastapi import FastAPI
from fastapi.testclient import TestClient

from middleware.error_handler import AppError, ErrorHandlerMiddleware


def test_app_error_is_serialized():
    app = FastAPI()
    app.add_middleware(ErrorHandlerMiddleware)

    @app.get("/boom")
    async def boom():
        raise AppError(40001, "bad request", status_code=422)

    client = TestClient(app)

    response = client.get("/boom")

    assert response.status_code == 422
    assert response.json() == {"code": 40001, "data": None, "message": "bad request"}
