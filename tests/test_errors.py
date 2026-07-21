import pytest
from csa_google_workspace import _errors, exceptions as exc


class FakeResp:
    def __init__(self, status):
        self.status = status
        self.reason = "x"


def _http_error(status, reason, message):
    from googleapiclient.errors import HttpError
    import json
    content = json.dumps({"error": {"errors": [{"reason": reason}], "message": message}}).encode()
    return HttpError(FakeResp(status), content)


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
