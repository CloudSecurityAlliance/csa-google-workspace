"""ApiBackend error-translation seam.

FakeBackend raises the *typed* exceptions directly, so no FakeBackend-based test can
prove that ApiBackend actually routes Google's raw HttpError through the translator.
These tests feed ApiBackend a stub service whose .execute() raises HttpError and assert
the caller sees a typed CsaWorkspaceError. Guards against the class of regression where
a new ApiBackend method forgets `_errors.call(...)` (as get_file_metadata once did).
"""
import json

import pytest
from googleapiclient.errors import HttpError

from csa_google_workspace import exceptions as exc
from csa_google_workspace.backend import ApiBackend


class _Resp:
    def __init__(self, status):
        self.status = status
        self.reason = "x"


def _http_error(status, reason, message):
    content = json.dumps({"error": {"errors": [{"reason": reason}], "message": message}}).encode()
    return HttpError(_Resp(status), content)


class _Request:
    """A built googleapiclient request whose .execute() either raises or returns."""
    def __init__(self, err=None, result=None):
        self._err = err
        self._result = result

    def execute(self):
        if self._err is not None:
            raise self._err
        return self._result


class _Files:
    def __init__(self, err=None, result=None):
        self._err, self._result = err, result

    def get(self, **kwargs):
        return _Request(self._err, self._result)


class _Drive:
    def __init__(self, err=None, result=None):
        self._files = _Files(err, result)

    def files(self):
        return self._files


class _Services:
    def __init__(self, err=None, result=None):
        self.drive = _Drive(err, result)


# Non-retryable statuses only — these translate synchronously (no backoff sleep).
# Retry/backoff for 429/5xx is exercised at the _errors.call level in test_errors.py;
# what matters here is that get_file_metadata routes raw HttpError through the translator
# at all — the exact 404/403/service-disabled cases the first open() call hits.
@pytest.mark.parametrize("status,reason,expected", [
    (404, "notFound", exc.NotFoundError),
    (403, "insufficientPermissions", exc.AccessError),
    (403, "SERVICE_DISABLED", exc.ServiceDisabledError),
])
def test_get_file_metadata_translates_http_error(status, reason, expected):
    backend = ApiBackend(_Services(err=_http_error(status, reason, "boom")))
    with pytest.raises(expected):
        backend.get_file_metadata("any-id")


def test_get_file_metadata_returns_metadata_on_success():
    meta = {"id": "abc", "name": "Doc", "mimeType": "application/vnd.google-apps.document"}
    backend = ApiBackend(_Services(result=meta))
    assert backend.get_file_metadata("abc") == meta
