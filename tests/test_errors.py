import pytest

from csa_google_workspace import _errors
from csa_google_workspace import exceptions as exc


class FakeResp:
    def __init__(self, status):
        self.status = status
        self.reason = "x"


class FakeRespWithHeaders(dict):
    """Mimics httplib2.Response: dict-like (case-insensitive in practice, but plain dict
    suffices here) plus a `.status` attribute."""
    def __init__(self, status, headers=None):
        super().__init__(headers or {})
        self.status = status
        self.reason = "x"


def _http_error(status, reason, message):
    import json

    from googleapiclient.errors import HttpError
    content = json.dumps({"error": {"errors": [{"reason": reason}], "message": message}}).encode()
    return HttpError(FakeResp(status), content)


def _http_error_with_headers(status, reason, message, headers=None):
    import json

    from googleapiclient.errors import HttpError
    content = json.dumps({"error": {"errors": [{"reason": reason}], "message": message}}).encode()
    return HttpError(FakeRespWithHeaders(status, headers), content)


@pytest.mark.parametrize("status,reason,expected", [
    (404, "notFound", exc.NotFoundError),
    (403, "insufficientPermissions", exc.AccessError),
    (429, "rateLimitExceeded", exc.RateLimitError),
    (500, "backendError", exc.ApiError),
])
def test_translate_maps_status_to_typed(status, reason, expected):
    assert isinstance(_errors.translate_http_error(_http_error(status, reason, "m")), expected)


def test_translate_service_disabled():
    e = _errors.translate_http_error(_http_error(403, "SERVICE_DISABLED", "Docs API not enabled; enable at https://console/x"))
    assert isinstance(e, exc.ServiceDisabledError)


def _modern_details_http_error(reason, message, details_reason=None, metadata=None):
    import json

    from googleapiclient.errors import HttpError
    body = {"error": {"code": 403, "status": "PERMISSION_DENIED", "message": message,
                       "errors": [{"reason": reason}]}}
    if details_reason:
        body["error"]["details"] = [{
            "@type": "type.googleapis.com/google.rpc.ErrorInfo",
            "reason": details_reason,
            "metadata": metadata or {},
        }]
    content = json.dumps(body).encode()
    return HttpError(FakeResp(403), content)


def test_translate_service_disabled_modern_details_format():
    err = _modern_details_http_error(
        reason="insufficientPermissions",
        message="The caller does not have permission",
        details_reason="SERVICE_DISABLED",
        metadata={"service": "docs.googleapis.com", "activationUrl": "https://console/enable"},
    )
    e = _errors.translate_http_error(err)
    assert isinstance(e, exc.ServiceDisabledError)
    assert e.service == "docs.googleapis.com"
    assert e.activation_url == "https://console/enable"


def test_translate_plain_403_is_access_error():
    err = _modern_details_http_error(reason="insufficientPermissions", message="nope")
    e = _errors.translate_http_error(err)
    assert isinstance(e, exc.AccessError)


def test_call_retries_then_succeeds():
    calls = {"n": 0}
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _http_error(503, "backendError", "temporary")
        return {"ok": True}
    assert _errors.call(flaky, _sleep=lambda s: None) == {"ok": True}
    assert calls["n"] == 3


def test_call_raises_typed_after_nonretryable():
    def boom():
        raise _http_error(404, "notFound", "gone")
    with pytest.raises(exc.NotFoundError):
        _errors.call(boom, _sleep=lambda s: None)


def test_call_non_idempotent_does_not_retry_5xx():
    calls = {"n": 0}
    def flaky_503():
        calls["n"] += 1
        raise _http_error(503, "backendError", "temporary")
    with pytest.raises(exc.ApiError):
        _errors.call(flaky_503, idempotent=False, _sleep=lambda s: None)
    assert calls["n"] == 1


def test_call_idempotent_still_retries_5xx():
    calls = {"n": 0}
    def flaky_503():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _http_error(503, "backendError", "temporary")
        return {"ok": True}
    assert _errors.call(flaky_503, _sleep=lambda s: None) == {"ok": True}
    assert calls["n"] == 3


def test_translate_429_with_retry_after_header():
    err = _http_error_with_headers(429, "rateLimitExceeded", "slow down",
                                    headers={"status": "429", "retry-after": "30"})
    e = _errors.translate_http_error(err)
    assert isinstance(e, exc.RateLimitError)
    assert e.retry_after == 30


def test_translate_429_without_retry_after_header():
    e = _errors.translate_http_error(_http_error(429, "rateLimitExceeded", "slow down"))
    assert isinstance(e, exc.RateLimitError)
    assert e.retry_after is None


def test_call_sleeps_retry_after_seconds_on_429():
    calls = {"n": 0}
    sleeps = []
    def flaky_429():
        calls["n"] += 1
        if calls["n"] < 2:
            raise _http_error_with_headers(429, "rateLimitExceeded", "slow down",
                                            headers={"status": "429", "retry-after": "7"})
        return {"ok": True}
    assert _errors.call(flaky_429, _sleep=lambda s: sleeps.append(s)) == {"ok": True}
    assert sleeps == [7]


def test_call_non_idempotent_still_retries_429():
    calls = {"n": 0}
    def flaky_429():
        calls["n"] += 1
        if calls["n"] < 2:
            raise _http_error(429, "rateLimitExceeded", "slow down")
        return {"ok": True}
    assert _errors.call(flaky_429, idempotent=False, _sleep=lambda s: None) == {"ok": True}
    assert calls["n"] == 2


def test_call_clamps_retry_after_to_60_seconds():
    """Retry-After header value is clamped to max 60 seconds to prevent excessive sleep."""
    calls = {"n": 0}
    sleeps = []
    def flaky_429_large_retry_after():
        calls["n"] += 1
        if calls["n"] < 2:
            raise _http_error_with_headers(429, "rateLimitExceeded", "slow down",
                                            headers={"status": "429", "retry-after": "999"})
        return {"ok": True}
    assert _errors.call(flaky_429_large_retry_after, _sleep=lambda s: sleeps.append(s)) == {"ok": True}
    assert sleeps == [60]  # Should be clamped to 60, not 999
