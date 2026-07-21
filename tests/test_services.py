from csa_google_workspace._services import ServiceRegistry


def test_lazy_build_only_on_access_and_cached():
    calls = []

    def fake_builder(name, version, credentials=None):
        calls.append((name, version))
        return f"{name}-{version}-client"

    reg = ServiceRegistry(credentials="creds", builder=fake_builder)
    assert calls == []                      # nothing built yet
    assert reg.drive == "drive-v3-client"   # builds on first access
    assert reg.drive == "drive-v3-client"   # cached
    assert calls == [("drive", "v3")]       # built exactly once
    assert reg.docs == "docs-v1-client"
    assert ("docs", "v1") in calls and len(calls) == 2
