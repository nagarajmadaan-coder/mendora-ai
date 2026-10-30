"""
Consistent error responses.

Every error the API returns looks like this, so the frontend only has to handle one shape:

    {
      "error": {
        "code": "validation_error",
        "message": "The request is invalid. See 'details' for each problem.",
        "details": [{"field": "trade_id", "message": "Unsupported trade_id 'roofing'. ..."}]
      }
    }
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    """Raise this from a route to return a clean, documented error."""

    def __init__(self, status_code: int, code: str, message: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers or {}


def _error_json(status_code: int, code: str, message: str, details: list[dict] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details or []}},
    )


def _field_name(location: tuple) -> str | None:
    # Pydantic locations look like ("body", "trade_id") or ("path", "request_id").
    parts = [str(part) for part in location if part not in ("body", "query", "path", "header")]
    return ".".join(parts) or None


def _clean_message(message: str) -> str:
    # Pydantic prefixes messages from our own validators with "Value error, ".
    return message.removeprefix("Value error, ")


async def handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
    response = _error_json(exc.status_code, exc.code, exc.message)
    response.headers.update(exc.headers)
    return response


async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    details = []
    for err in exc.errors():
        if err.get("type") == "json_invalid":
            details.append({"field": None, "message": "The request body is not valid JSON."})
        elif err.get("type") == "extra_forbidden":
            details.append({"field": _field_name(err["loc"]), "message": "This field is not allowed."})
        else:
            details.append({"field": _field_name(err["loc"]), "message": _clean_message(err["msg"])})
    return _error_json(
        422,
        "validation_error",
        "The request is invalid. See 'details' for each problem.",
        details,
    )


async def handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    codes = {404: "not_found", 405: "method_not_allowed"}
    message = "The requested URL was not found." if exc.status_code == 404 else str(exc.detail)
    response = _error_json(exc.status_code, codes.get(exc.status_code, "http_error"), message)
    if exc.headers:
        response.headers.update(exc.headers)
    return response


async def handle_unexpected_error(_: Request, __: Exception) -> JSONResponse:
    # Never leak internal details (stack traces, file paths) to the client.
    return _error_json(500, "internal_error", "Something went wrong on the server. Please try again.")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, handle_api_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, handle_validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, handle_http_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, handle_unexpected_error)
