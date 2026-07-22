"""Error-translation edge cases (audit findings #8, #9)."""
import json

from googleapiclient.errors import HttpError

from csa_google_workspace import _errors
from csa_google_workspace import exceptions as exc


class _Resp(dict):
    """httplib2.Response stand-in: dict of headers plus a .status/.reason."""
    def __init__(self, status, headers=None):
        super().__init__(headers or {})
        self.status = status
        self.reason = "x"


def _err(status, headers=None, reason="", message="m"):
    content = json.dumps({"error": {"errors": [{"reason": reason}], "message": message}}).encode()
    return HttpError(_Resp(status, headers), content)


# --- #9: 401 must map to AuthError, not the generic ApiError -------------------

def test_401_maps_to_auth_error():
    assert isinstance(_errors.translate_http_error(_err(401, reason="authError", message="bad creds")),
                      exc.AuthError)


# --- #8: a negative/garbage Retry-After must not crash the retry loop ----------

def test_retry_after_negative_is_ignored():
    assert _errors._retry_after(_err(429, {"retry-after": "-5"})) is None


def test_retry_after_positive_is_parsed():
    assert _errors._retry_after(_err(429, {"retry-after": "10"})) == 10


def test_retry_after_http_date_is_ignored():
    assert _errors._retry_after(_err(429, {"retry-after": "Mon, 01 Jan 2030 00:00:00 GMT"})) is None


def test_call_survives_negative_retry_after_and_retries():
    attempts = {"n": 0}

    def fn():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise _err(429, {"retry-after": "-5"}, reason="rateLimitExceeded")
        return "ok"

    slept = []
    result = _errors.call(fn, _sleep=slept.append)
    assert result == "ok"
    assert attempts["n"] == 2
    assert all(s >= 0 for s in slept)   # never a negative sleep, which time.sleep rejects
