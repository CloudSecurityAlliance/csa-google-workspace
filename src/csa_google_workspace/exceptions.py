"""Typed error hierarchy. Callers never touch raw googleapiclient HttpError."""


class CsaWorkspaceError(Exception):
    """Base for every library error."""


class AuthError(CsaWorkspaceError):
    """Bad/expired credentials, or consent needed."""


class ServiceDisabledError(CsaWorkspaceError):
    """A Google API is not enabled in the Cloud project (403 SERVICE_DISABLED)."""

    def __init__(self, service: str, activation_url: str):
        self.service = service
        self.activation_url = activation_url
        super().__init__(
            f"The API '{service}' is not enabled for this Google Cloud project. "
            f"Enable it at {activation_url} and retry (allow a few minutes to propagate)."
        )


class ReadOnlyError(CsaWorkspaceError):
    """A mutating call was made while the workspace is read_only=True."""


class NotFoundError(CsaWorkspaceError):
    """A file, comment, or reply id does not exist (404)."""


class AccessError(CsaWorkspaceError):
    """Insufficient permission (403) — not shared, wrong scope, or editing another's comment."""


class RateLimitError(CsaWorkspaceError):
    """Rate limit hit (429). `retry_after` is seconds, if the server provided it."""

    def __init__(self, retry_after: int | None = None):
        self.retry_after = retry_after
        super().__init__(f"Rate limited; retry after {retry_after}s" if retry_after else "Rate limited")


class UnsupportedOperation(CsaWorkspaceError):
    """The operation is impossible on this backend (e.g. accept a suggestion via the API)."""


class ApiError(CsaWorkspaceError):
    """Catch-all wrapper for an unclassified googleapiclient HttpError."""

    def __init__(self, status: int, reason: str, message: str):
        self.status = status
        self.reason = reason
        super().__init__(f"[{status} {reason}] {message}")
