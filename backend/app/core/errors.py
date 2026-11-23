from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class ApiError(HTTPException):
    def __init__(self, status: int, code: str, message: str, details: object = None):
        super().__init__(status_code=status, detail=message)
        self.code = code
        self.details = details


def not_found(message: str = "Resource not found") -> ApiError:
    return ApiError(404, "NOT_FOUND", message)


def conflict(message: str, details: object = None) -> ApiError:
    return ApiError(409, "CONFLICT", message, details)


def forbidden(message: str = "Forbidden") -> ApiError:
    return ApiError(403, "FORBIDDEN", message)


def bad_request(message: str, details: object = None) -> ApiError:
    return ApiError(400, "BAD_REQUEST", message, details)


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.detail, "details": exc.details}},
    )
