"""Translate googleapiclient HttpError into the typed hierarchy, with retry for transient errors."""
import json
import time

from googleapiclient.errors import HttpError

from . import exceptions as exc

_RETRYABLE = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 4


def _reason_and_message(err: HttpError):
    try:
        body = json.loads(err.content.decode() if isinstance(err.content, bytes) else err.content)
        e = body.get("error", {})
        errors = e.get("errors") or []
        reason = (errors[0].get("reason") if errors else None) or ""
        return reason, e.get("message", "")
    except (ValueError, AttributeError, KeyError, IndexError):
        return "", ""


def _service_disabled_details(err: HttpError):
    """Modern 403 body: error.details[] holds an ErrorInfo with reason SERVICE_DISABLED
    and metadata.service / metadata.activationUrl. Returns (service, activation_url) or None."""
    try:
        body = json.loads(err.content.decode() if isinstance(err.content, bytes) else err.content)
        for detail in body.get("error", {}).get("details") or []:
            if detail.get("reason") == "SERVICE_DISABLED":
                metadata = detail.get("metadata") or {}
                return metadata.get("service", "(unknown)"), metadata.get("activationUrl", "(unknown)")
    except (ValueError, AttributeError, KeyError, IndexError):
        pass
    return None


def translate_http_error(err: HttpError) -> exc.CsaWorkspaceError:
    status = int(getattr(err.resp, "status", 0) or 0)
    reason, message = _reason_and_message(err)
    if status == 404:
        return exc.NotFoundError(message or "not found")
    if status == 403:
        details = _service_disabled_details(err)
        if details:
            service, activation_url = details
            return exc.ServiceDisabledError(service=service, activation_url=activation_url)
        if reason == "SERVICE_DISABLED":
            # legacy format: message contains an activation URL; surface it whole.
            return exc.ServiceDisabledError(service="(see message)", activation_url=message)
        return exc.AccessError(message or "insufficient permission")
    if status == 429:
        return exc.RateLimitError()
    return exc.ApiError(status=status, reason=reason, message=message or str(err))


def call(fn, *args, idempotent: bool = True, _sleep=time.sleep, **kwargs):
    """Call fn(*args, **kwargs), translating HttpError. Always retries 429; retries 5xx
    with backoff only when `idempotent` is True (non-idempotent writes must not be retried
    on 5xx, since the mutation may have already succeeded server-side)."""
    attempt = 0
    while True:
        attempt += 1
        try:
            return fn(*args, **kwargs)
        except HttpError as err:
            status = int(getattr(err.resp, "status", 0) or 0)
            retryable = status == 429 or (idempotent and status in _RETRYABLE)
            if retryable and attempt < _MAX_ATTEMPTS:
                _sleep(0.5 * (2 ** (attempt - 1)))
                continue
            raise translate_http_error(err) from err
