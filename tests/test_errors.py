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


class TestABodyThatIsNotWhatGoogleUsuallySends:
    """The three parsers all swallow malformed input and return "nothing known".

    That is the right posture and it is worth saying why: these run while an error is ALREADY
    being raised. A parser that threw here would replace a 403 the caller could act on with a
    JSONDecodeError from inside the error handler - the original status, reason and message
    all lost, and the traceback pointing at this file rather than at the call that failed.

    So every one of them degrades to a less specific error, never to a different one.
    """

    @pytest.mark.parametrize("content", [
        pytest.param(b"<html>502 Bad Gateway</html>", id="html-from-a-proxy"),
        pytest.param(b"", id="empty"),
        pytest.param(b"{", id="truncated-json"),
        pytest.param(b'{"error": "a string, not an object"}', id="right-json-wrong-shape"),
        pytest.param(b'{"error": {"errors": []}}', id="no-errors-entries"),
    ])
    def test_an_unparseable_body_yields_no_reason_and_no_message(self, content):
        from googleapiclient.errors import HttpError

        reason, message = _errors._reason_and_message(HttpError(FakeResp(403), content))
        assert (reason, message) == ("", "")

    def test_it_still_translates_into_an_actionable_error(self):
        """The point of the above. An HTML error page from a proxy still becomes a typed
        exception carrying the STATUS, which is the part that tells a caller whether to
        retry, re-authorize, or stop."""
        from googleapiclient.errors import HttpError

        with pytest.raises(exc.CsaWorkspaceError) as ei:
            _errors.call(lambda: (_ for _ in ()).throw(
                HttpError(FakeResp(503), b"<html>Service Unavailable</html>")))
        assert "503" in str(ei.value)

    @pytest.mark.parametrize("content", [
        pytest.param(b"not json at all", id="not-json"),
        pytest.param(b'{"error": {"details": [{"reason": "SOMETHING_ELSE"}]}}',
                     id="details-without-service-disabled"),
        pytest.param(b'{"error": {"details": "a string"}}', id="details-wrong-type"),
    ])
    def test_service_disabled_details_are_absent_rather_than_guessed(self, content):
        """`None` means "this is not a disabled-API 403". Returning a placeholder would make
        every 403 render as "enable the Drive API", which is the wrong instruction for the
        far commoner case of the file simply not being shared with this account."""
        from googleapiclient.errors import HttpError

        assert _errors._service_disabled_details(HttpError(FakeResp(403), content)) is None

    def test_a_response_with_no_retry_after_header_is_none(self):
        """Absent, not zero. Zero means "retry immediately", and telling a caller to retry a
        429 immediately is how a rate limit becomes a ban."""
        from googleapiclient.errors import HttpError

        no_header = HttpError(FakeRespWithHeaders(429, {}), b"{}")
        assert _errors._retry_after(no_header) is None

    def test_a_response_object_without_headers_at_all_is_none(self):
        """`FakeResp` has no `.get`. Some transports hand back an object that is not
        dict-like, and reaching for a header on it raises AttributeError."""
        from googleapiclient.errors import HttpError

        assert _errors._retry_after(HttpError(FakeResp(429), b"{}")) is None
