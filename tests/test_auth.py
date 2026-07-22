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


def test_needs_reconsent_false_when_granted_rw_satisfies_required_readonly():
    # A user who already authorized full RW scopes shouldn't be forced to re-consent
    # just because a later call opens with read_only=True.
    assert auth.needs_reconsent(granted=auth.scopes_for(False), required=auth.scopes_for(True)) is False


def test_needs_reconsent_false_when_readonly_satisfies_readonly():
    assert auth.needs_reconsent(granted=auth.scopes_for(True), required=auth.scopes_for(True)) is False


def test_needs_reconsent_true_when_scope_truly_missing():
    # granted lacks both the readonly variant and the RW base for "presentations" ->
    # still must reconsent even with the readonly-satisfied-by-RW fallback in place.
    granted = [s for s in auth.scopes_for(False) if "presentations" not in s]
    required = auth.scopes_for(read_only=True)
    assert auth.needs_reconsent(granted, required) is True
