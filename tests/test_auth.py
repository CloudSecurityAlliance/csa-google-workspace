from csa_google_workspace import auth


def test_scopes_readwrite_include_all_four_services():
    s = auth.scopes_for(read_only=False)
    assert any(x.endswith("/auth/drive") for x in s)
    assert any(x.endswith("/auth/documents") for x in s)
    assert any(x.endswith("/auth/spreadsheets") for x in s)
    assert any(x.endswith("/auth/presentations") for x in s)
    assert not any(".readonly" in x for x in s)


def test_scopes_readonly_are_all_readonly_variants():
    s = auth.scopes_for(read_only=True)
    assert all(x.endswith(".readonly") for x in s)
    assert len(s) == 4


def test_needs_reconsent_true_when_scope_missing():
    granted = ["https://www.googleapis.com/auth/drive.readonly"]
    required = auth.scopes_for(read_only=False)
    assert auth.needs_reconsent(granted, required) is True


def test_needs_reconsent_false_when_all_present():
    required = auth.scopes_for(read_only=False)
    assert auth.needs_reconsent(granted=required, required=required) is False
