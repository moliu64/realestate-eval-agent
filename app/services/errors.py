"""Small domain error hierarchy.

Services raise these instead of ``fastapi.HTTPException`` so the business layer
does not depend on the web framework. ``app.main`` maps them to HTTP responses.
"""


class ServiceError(Exception):
    """Base class for recoverable, user-facing service errors."""

    status_code = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidInputError(ServiceError):
    status_code = 400


class UnauthorizedError(ServiceError):
    status_code = 401


class ForbiddenError(ServiceError):
    status_code = 403


class NotFoundError(ServiceError):
    status_code = 404


class ConflictError(ServiceError):
    status_code = 409


class PayloadTooLargeError(ServiceError):
    status_code = 413


class UnavailableError(ServiceError):
    status_code = 503
