from csa_google_workspace import exceptions as exc


def test_all_errors_subclass_base():
    for cls in (exc.AuthError, exc.ServiceDisabledError, exc.ReadOnlyError,
                exc.NotFoundError, exc.AccessError, exc.RateLimitError,
                exc.UnsupportedOperation, exc.ApiError):
        assert issubclass(cls, exc.CsaWorkspaceError)


def test_service_disabled_carries_service_and_url():
    e = exc.ServiceDisabledError("docs.googleapis.com", "https://console/enable")
    assert e.service == "docs.googleapis.com"
    assert "console" in e.activation_url
    assert e.service in str(e)


def test_api_error_carries_status_reason():
    e = exc.ApiError(status=404, reason="notFound", message="missing")
    assert e.status == 404 and e.reason == "notFound"


def test_rate_limit_carries_retry_after():
    assert exc.RateLimitError(retry_after=30).retry_after == 30
